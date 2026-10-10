"""Offline regression tests: every provider request is mocked."""
import json
import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import server


SECRET = "secret-sentinel-never-return"
RAW_MESSAGE = "original-provider-message-never-return"


def response(body, status=200):
    return Mock(status_code=status, headers={}, json=Mock(return_value=body))


class APIErrorTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"API_FOOTBALL_KEY": SECRET})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.http = patch.object(server.requests, "get")
        self.get = self.http.start()
        self.get.side_effect = AssertionError("Unconfigured provider mock")
        self.addCleanup(self.http.stop)
        self.cache = patch.object(server, "AF_CACHE", {})
        self.cache.start()
        self.addCleanup(self.cache.stop)
        self.rate = patch.object(server, "AF_RATE", {
            "day": None, "day_count": 0, "minute": None, "minute_count": 0,
            "day_remaining": None, "minute_remaining": None, "day_limit": None,
        })
        self.rate.start()
        self.addCleanup(self.rate.stop)

    def mock_responses(self, *responses):
        self.get.side_effect = list(responses)

    def assert_safe(self, value):
        text = json.dumps(value)
        for sensitive in (SECRET, RAW_MESSAGE, "x-apisports-key", "Authorization"):
            self.assertNotIn(sensitive, text)

    def request_error(self, expected, params=None):
        with self.assertRaises(server._AFError) as caught:
            server._af_request("/fixtures", params or {"team": SECRET, "last": 10})
        error = caught.exception
        self.assertEqual(str(error), expected)
        self.assert_safe({"code": str(error), "diagnostic": error.diagnostic})
        self.assertEqual(server.AF_CACHE, {})
        return error

    def test_disallowed_endpoint_precedes_credentials_and_network(self):
        with patch.dict(os.environ, {"API_FOOTBALL_KEY": ""}):
            with self.assertRaisesRegex(server._AFError, "^endpoint_not_allowed$") as caught:
                server._af_request("/odds?token=" + SECRET)
        self.assertIsNone(caught.exception.diagnostic["endpoint"])
        self.assert_safe(caught.exception.diagnostic)
        self.get.assert_not_called()

    def test_provider_errors_are_classified_and_sanitized(self):
        cases = [
            ({"last": "Free plans do not have access to the Last parameter."},
             "provider_plan_restricted", "plan_restriction"),
            ({"plan": "Upgrade your plan"}, "provider_plan_restricted", "plan_restriction"),
            ({"last": "The Free plan cannot use this parameter"},
             "provider_plan_restricted", "plan_restriction"),
            ({"team": "Invalid parameter"}, "provider_parameters_rejected", "invalid_parameters"),
            ({"requests": "You have reached the request limit for the day"},
             "provider_quota_restricted", "api_limit"),
            ({"rateLimit": "Too many requests"}, "provider_quota_restricted", "api_limit"),
            ({"token": "Invalid API key"}, "provider_authentication_failed", "authentication"),
            ({"unknown": "Something unrecognized"}, "provider_reported_error", "other"),
            (["Invalid parameter"], "provider_parameters_rejected", "invalid_parameters"),
        ]
        for errors, code, category in cases:
            with self.subTest(code=code, errors=errors):
                if isinstance(errors, dict):
                    errors = {k: v + " " + RAW_MESSAGE + " " + SECRET for k, v in errors.items()}
                    errors[SECRET] = RAW_MESSAGE
                self.mock_responses(response({"errors": errors, "response": []}))
                error = self.request_error(code, {"team": SECRET, "last": 10, SECRET: SECRET})
                self.assertEqual(error.diagnostic["category"], category)
                self.assertEqual(error.diagnostic["endpoint"], "/fixtures")
                self.assertEqual(error.diagnostic["http_status"], 200)
                self.assertEqual(error.diagnostic["request_parameter_names"], ["last", "team"])
                if isinstance(errors, dict):
                    self.assertEqual(error.diagnostic["error_parameter_names"],
                                     sorted({"last", "team"}.intersection(errors)))
                if category == "plan_restriction":
                    self.assertEqual(error.diagnostic["free_plan_restriction"], "last" in errors)
                server.AF_RATE["minute_count"] = 0

    def test_http_errors_do_not_expose_body_or_headers(self):
        for status, code in [(401, "provider_authentication_failed"),
                             (403, "provider_authentication_failed"),
                             (429, "provider_rate_limited"),
                             (500, "provider_http_failure")]:
            with self.subTest(status=status):
                reply = response({"errors": {SECRET: RAW_MESSAGE}}, status)
                reply.headers = {"Authorization": SECRET, "x-apisports-key": SECRET}
                self.mock_responses(reply)
                error = self.request_error(code)
                self.assertEqual(error.diagnostic["http_status"], status)
                reply.json.assert_not_called()

    def test_transport_and_json_exceptions_are_sanitized(self):
        self.get.side_effect = RuntimeError(SECRET + RAW_MESSAGE)
        error = self.request_error("provider_transport_failure")
        self.assertTrue(error.__suppress_context__)
        reply = response(None)
        reply.json.side_effect = ValueError(SECRET + RAW_MESSAGE)
        self.mock_responses(reply)
        error = self.request_error("provider_invalid_json")
        self.assertTrue(error.__suppress_context__)

    def test_invalid_response_and_pagination_stay_blocked(self):
        for body, code in [(None, "provider_invalid_response"),
                           ({"errors": [], "paging": {"total": 2}},
                            "provider_pagination_not_handled")]:
            with self.subTest(code=code):
                self.mock_responses(response(body))
                self.request_error(code)

    def test_missing_key_and_local_budget_never_call_provider(self):
        with patch.dict(os.environ, {"API_FOOTBALL_KEY": ""}):
            self.request_error("provider_not_configured")
        # Initialize current day/minute using a successful request.
        self.mock_responses(response({"errors": [], "response": []}))
        server._af_request("/status")
        self.get.reset_mock()
        server.AF_CACHE.clear()
        for field, limit, code in [
            ("day_count", server.AF_LOCAL_DAY_LIMIT, "local_daily_budget_exhausted"),
            ("minute_count", server.AF_LOCAL_MINUTE_LIMIT, "local_minute_budget_exhausted"),
            ("day_remaining", 10, "provider_daily_quota_reserve"),
            ("minute_remaining", 1, "provider_minute_quota_reserve"),
        ]:
            with self.subTest(code=code):
                old = server.AF_RATE[field]
                server.AF_RATE[field] = limit
                self.request_error(code)
                server.AF_RATE[field] = old
        self.get.assert_not_called()

    def test_success_is_cached_but_errors_are_not(self):
        body = {"errors": [], "response": [{"fixture": {"id": 1}}]}
        self.mock_responses(response(body))
        self.assertEqual(server._af_request("/fixtures", {"id": 1}), (body, False))
        self.assertEqual(server._af_request("/fixtures", {"id": 1}), (body, True))
        self.get.assert_called_once()
        server.AF_CACHE.clear()
        self.mock_responses(response({"errors": {"last": "Invalid parameter"}}), response(body))
        self.request_error("provider_parameters_rejected", {"id": 1})
        self.assertEqual(server._af_request("/fixtures", {"id": 1}), (body, False))

    def fixture(self):
        self.kickoff = (datetime.now(server.AF_TIMEZONE) + timedelta(days=1)).replace(
            hour=12, minute=0, second=0, microsecond=0)
        return {"fixture": {"id": 123, "timestamp": int(self.kickoff.timestamp()),
                            "date": self.kickoff.isoformat(), "status": {"short": "NS"}},
                "teams": {"home": {"id": 10, "name": "Boluspor"},
                          "away": {"id": 20, "name": "Antalyaspor"}},
                "league": {"name": "Test league"}}

    def history(self, team_id):
        return {"errors": [], "response": [
            {"fixture": {"id": 1000 + team_id + i,
                         "timestamp": int((self.kickoff - timedelta(days=i + 2)).timestamp()),
                         "status": {"short": "FT"}},
             "teams": {"home": {"id": team_id, "name": "Test team"},
                       "away": {"id": 999, "name": "Opponent"}},
             "goals": {"home": 1, "away": 0}, "league": {"name": "Test league"}}
            for i in range(5)]}

    def test_history_probe_propagates_free_plan_error_for_either_team(self):
        fixture = self.fixture()
        for failed_side in ("home", "away"):
            with self.subTest(side=failed_side):
                server.AF_CACHE.clear()
                server.AF_RATE["minute_count"] = 0
                replies = [response({"errors": [], "response": [fixture]})]
                if failed_side == "away":
                    replies.append(response(self.history(10)))
                replies.append(response({"errors": {"last":
                    "Free plans do not have access to the Last parameter. " + SECRET + RAW_MESSAGE}}))
                self.mock_responses(*replies)
                result = server.football_history_probe(
                    123, "Boluspor", "Antalyaspor", self.kickoff.date().isoformat())
                self.assertEqual(result["state"], "provider_unavailable")
                self.assertFalse(result["ready_for_quant"])
                self.assertFalse(result["ready_for_analysis"])
                blocker = result["blockers"][0]
                self.assertEqual(blocker["type"], "provider_plan_restricted")
                self.assertTrue(blocker["diagnostic"]["free_plan_restriction"])
                self.assertEqual(blocker["diagnostic"]["request_parameter_names"], ["last", "team"])
                self.assert_safe(result)

    def test_history_probe_success_is_unchanged(self):
        fixture = self.fixture()
        self.mock_responses(response({"errors": [], "response": [fixture]}),
                            response(self.history(10)), response(self.history(20)))
        result = server.football_history_probe(
            123, "Boluspor", "Antalyaspor", self.kickoff.date().isoformat())
        self.assertEqual(result["state"], "history_available")
        self.assertTrue(result["ok"])
        self.assertFalse(result["ready_for_quant"])
        self.assertEqual(result["teams_form"]["home"]["sample_size"], 5)
        self.assertEqual(result["teams_form"]["away"]["sample_size"], 5)
        self.assertEqual(self.get.call_count, 3)

    def test_evidence_propagates_diagnostic_without_bypassing_scout(self):
        self.fixture()
        scout = {"ok": True, "state": "ready", "ready_for_analysis": True,
                 "palinsesto": "123", "avvenimento": "456",
                 "event": {"home": "Boluspor", "away": "Antalyaspor"}}
        self.mock_responses(response({"errors": {"team": "Invalid parameter " + SECRET + RAW_MESSAGE}}))
        with patch.object(server, "scout_event", return_value=scout), \
                patch.object(server, "_af_sisal_kickoff_time", return_value="12:00"):
            result = server.football_evidence_event("123", "456", 123, self.kickoff.date().isoformat())
        self.assertEqual(result["state"], "provider_unavailable")
        self.assertEqual(result["blockers"][0]["diagnostic"]["category"], "invalid_parameters")
        self.assertFalse(result["ready_for_quant"])
        self.assert_safe(result)
        self.get.reset_mock()
        with patch.object(server, "scout_event", return_value={"ok": False, "state": "blocked"}):
            result = server.football_evidence_event("123", "456")
        self.assertEqual(result["state"], "blocked_by_scout")
        self.get.assert_not_called()

    def test_provider_status_propagates_safe_diagnostic(self):
        self.mock_responses(response({"errors": {"requests": RAW_MESSAGE + SECRET}}))
        result = server.football_provider_status(check_remote=True)
        self.assertEqual(result["state"], "provider_quota_restricted")
        self.assertEqual(result["provider_diagnostic"]["category"], "api_limit")
        self.assertFalse(result["authenticated"])
        self.assert_safe(result)

    def test_fixture_probe_propagates_safe_diagnostic(self):
        self.fixture()
        aggregate = {"state": "ok", "sheets": {
            sheet: {"state": "ok", "home_printed": "Boluspor", "away_printed": "Antalyaspor"}
            for sheet in server.SHEETS}}
        self.mock_responses(response({"errors": {SECRET: RAW_MESSAGE}}))
        result = server._af_fixture_probe_review(aggregate, "12:00", self.kickoff.date().isoformat())
        self.assertEqual(result["state"], "provider_unavailable")
        self.assertEqual(result["blockers"][0]["diagnostic"]["category"], "other")
        self.assert_safe(result)

    def test_internal_errors_keep_existing_blocker_shape(self):
        self.assertEqual(server._af_error_blocker(server._AFError("history_invalid_response")),
                         {"type": "history_invalid_response"})


if __name__ == "__main__":
    unittest.main()
