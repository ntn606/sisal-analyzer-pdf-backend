"""Offline regressions over an archived official Sisal PDF, not live odds."""

import ast
import hashlib
import io
import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from pypdf import PdfReader

import server

FIXTURES = Path(__file__).parent / "fixtures"
RAW = (FIXTURES / "sisal-base-20261011.pdf").read_bytes()
PROVENANCE = json.loads((FIXTURES / "sisal-base-20261011-provenance.json").read_text())
TEXT = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(RAW)).pages)


class MatchSearchTests(unittest.TestCase):
    data_origin = "real_archived_official_sisal_pdf_20261011"

    def setUp(self):
        self.cache = patch.object(server, "CACHE", {})
        self.cache.start()
        self.addCleanup(self.cache.stop)
        self.http = patch.object(
            server.requests, "get", side_effect=AssertionError("offline")
        )
        self.http.start()
        self.addCleanup(self.http.stop)
        server.save_cache("base", TEXT, RAW)

    def test_official_pdf_hash(self):
        self.assertEqual(hashlib.sha256(RAW).hexdigest(), PROVENANCE["pdf_sha256"])

    def test_champions_alias_finds_all_senior_events(self):
        result = server.get_matches("Champions")
        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 18)
        self.assertEqual({v["manifestazione"] for v in result["matches"]}, {"EUCHL"})
        self.assertEqual(
            {v["competition"] for v in result["matches"]}, {"UEFA Champions League"}
        )

    def test_three_reported_events_have_exact_printed_identity(self):
        cases = [
            ("Roma Real Madrid", "7213", "21:00", "Roma", "Real Madrid"),
            (
                "Manchester City Paris",
                "7210",
                "21:00",
                "Manchester City",
                "Paris Saint-germain",
            ),
            ("Feyenoord Como", "7214", "18:45", "Feyenoord", "Como"),
        ]
        for query, avv, hour, home, away in cases:
            with self.subTest(query=query):
                result = server.get_matches(query)
                self.assertEqual(result["count"], 1)
                event = result["matches"][0]
                self.assertEqual(
                    (event["palinsesto"], event["avvenimento"]), ("36421", avv)
                )
                self.assertEqual(event["manifestazione"], "EUCHL")
                self.assertEqual(
                    (event["time"], event["home_printed"], event["away_printed"]),
                    (hour, home, away),
                )
                self.assertEqual(event["match"], home + " " + away)
                self.assertGreaterEqual(event["page"], 1)

    def test_search_odds_and_get_matches_find_same_real_events(self):
        for query in ("Roma Real Madrid", "Manchester City Paris", "Feyenoord Como"):
            self.assertEqual(len(server.search_odds(query, sheet="base")), 1)
            self.assertEqual(server.get_matches(query)["count"], 1)

    def test_roma_query_keeps_senior_roma(self):
        keys = {
            (v["palinsesto"], v["avvenimento"])
            for v in server.get_matches("Roma")["matches"]
        }
        self.assertIn(("36421", "7213"), keys)

    def test_pagination_keeps_every_real_row_without_duplicates(self):
        # 472 independent rows in the previously saved spatial text transcript.
        rows = []
        offset = 0
        while True:
            result = server.get_matches(limit=300, offset=offset)
            self.assertTrue(result["ok"])
            self.assertEqual(result["count"], 472)
            self.assertEqual(result["returned_count"], len(result["matches"]))
            rows.extend(result["matches"])
            if result["next_offset"] is None:
                break
            offset = result["next_offset"]
        self.assertEqual(len(rows), 472)
        self.assertEqual(
            {(v["palinsesto"], v["avvenimento"]) for v in rows},
            {
                tuple(v)
                for v in PROVENANCE["expected_event_keys_from_saved_spatial_transcript"]
            },
        )
        self.assertEqual(len({(v["palinsesto"], v["avvenimento"]) for v in rows}), 472)
        self.assertTrue(server.get_matches(limit=100)["truncated"])

    def test_competition_code_and_ids_are_searchable(self):
        self.assertEqual(server.get_matches("EUCHL")["count"], 18)
        self.assertEqual(server.get_matches("  UEFA Champions   League ")["count"], 18)
        self.assertEqual(
            server.get_matches("7213")["matches"][0]["match"], "Roma Real Madrid"
        )

    def test_real_under20_and_womens_rows_keep_printed_names_and_codes(self):
        all_rows = server._match_events_from_pdf(RAW)
        under20 = [e for e in all_rows if "Cagliari Calcio U20" in e["match"]]
        self.assertEqual(len(under20), 1)
        self.assertEqual(under20[0]["home_printed"], "Cagliari Calcio U20")
        self.assertEqual(under20[0]["away_printed"], "Ac Monza U20")
        self.assertEqual(under20[0]["manifestazione"], "ITAPR")
        women = [e for e in all_rows if e["manifestazione"] == "VNM1F"]
        self.assertEqual(len(women), 1)
        self.assertNotIn(women[0], server.get_matches("Champions")["matches"])

    def test_numeric_competition_code_is_not_discarded(self):
        self.assertTrue(
            any(
                e["manifestazione"] == "2779"
                for e in server._match_events_from_pdf(RAW)
            )
        )

    def test_cached_index_does_not_mutate_through_returned_matches(self):
        result = server.get_matches("7213")
        result["matches"][0]["match"] = "caller mutation"
        self.assertEqual(
            server.get_matches("7213")["matches"][0]["match"], "Roma Real Madrid"
        )

    def test_pdf_missing_or_corrupt_is_explicitly_blocked(self):
        for pdf in (None, b"not a PDF"):
            with self.subTest(pdf_present=pdf is not None):
                server.CACHE["base"]["pdf_bytes"] = pdf
                result = server.get_matches("Champions")
                self.assertFalse(result["ok"])
                self.assertEqual(result["matches"], [])
                self.assertIn(
                    result["state"], ("source_not_ready", "source_parse_error")
                )

    def test_base_quote_parsers_return_unchanged_archived_prices(self):
        for avv, expected in PROVENANCE["base_quotes"].items():
            actual = server.get_base_market_quotes("36421", avv)
            # Wall-clock cache age is not an odds cell and naturally changes.
            comparable = {k: v for k, v in actual.items() if k != "cache_age_seconds"}
            before = {k: v for k, v in expected.items() if k != "cache_age_seconds"}
            self.assertEqual(comparable, before)
        self.assertEqual(
            server.get_extra_market_quotes("36421", "7213")["state"], "source_not_ready"
        )
        self.assertEqual(
            server.get_combinate_market_quotes("36421", "7213")["state"],
            "source_not_ready",
        )

    def test_scout_archived_replay_and_actual_stale_guard(self):
        aggregate = server.get_all_event_quotes("36421", "7213")
        # Explicit historical policy replay, never presented as current ready.
        replay = server._scout_evaluate_aggregate(
            aggregate,
            now=datetime(2026, 10, 11, 21, 20, tzinfo=ZoneInfo("Europe/Rome")),
        )
        self.assertEqual(replay["state"], "blocked")
        self.assertEqual(
            {b["sheet"] for b in replay["blockers"] if b["type"] == "sheet_not_ok"},
            {"extra", "combinate"},
        )
        current = server.scout_event("36421", "7213")
        self.assertFalse(current["ready_for_analysis"])
        self.assertTrue(any(b["type"] == "pdf_too_old" for b in current["blockers"]))

    def test_mcp_existing_query_and_limit_arguments_remain_valid(self):
        import asyncio

        async def check():
            tools = await server.mcp.list_tools()
            tool = next(t for t in tools if t.name == "get_matches")
            self.assertEqual(tool.inputSchema["properties"]["offset"]["default"], 0)
            result = await server.mcp.call_tool(
                "get_matches", {"query": "Champions", "limit": 100}
            )
            content = result[0] if isinstance(result, tuple) else result
            output = json.loads(content[0].text)
            self.assertEqual(output["count"], 18)
            self.assertEqual(output["offset"], 0)

        asyncio.run(check())

    def test_offline_guard_blocks_native_socket_and_dns(self):
        import os
        import socket

        if os.environ.get("SISAL_MATCHES_OFFLINE_TESTS") != "1":
            self.skipTest("Use research/champions-event-search/run_offline.py")
        with self.assertRaises(RuntimeError):
            socket.getaddrinfo("landing.sisal.it", 443)
        with self.assertRaises(PermissionError):
            socket.socket(socket.AF_INET, socket.SOCK_STREAM)


class CompetitionSeparationTests(unittest.TestCase):
    data_origin = "code_classification_only_no_fabricated_event_ids_teams_or_odds"

    def test_champions_alias_never_includes_youth_or_womens_codes(self):
        for code in ("EUUYL", "EUCHLF", "EUCHL2"):
            # Only a competition label is supplied: no fictitious match record.
            event = {
                "manifestazione": code,
                "match": "",
                "palinsesto": "",
                "avvenimento": "",
            }
            self.assertFalse(server._match_query(event, "Champions"))
            self.assertFalse(server._match_query(event, "EUCHL"))

    def test_youth_alias_is_separate(self):
        event = {
            "manifestazione": "EUUYL",
            "match": "",
            "palinsesto": "",
            "avvenimento": "",
        }
        self.assertTrue(server._match_query(event, "Youth League"))
        self.assertTrue(server._match_query(event, "EUUYL"))
        event["manifestazione"] = "EUCHL"
        self.assertFalse(server._match_query(event, "Youth League"))

    def test_original_function_asts_are_unchanged_except_get_matches(self):
        tree = ast.parse(Path(server.__file__).read_text())
        current = {
            node.name: hashlib.sha256(
                ast.dump(node, include_attributes=False).encode()
            ).hexdigest()
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for name, expected in PROVENANCE["original_function_ast_sha256"].items():
            self.assertEqual(current[name], expected, name)
