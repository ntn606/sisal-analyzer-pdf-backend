"""Synthetic edge cases. All match IDs/scores in this file are test fixtures."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from history_provider_v2 import Dataset, InputError, Snapshot, build_history, load_snapshots
from history_provider_v2.cli import main

TEAM = 'football-data.org:team:57'
NOW = '2026-10-10T18:05:00Z'


def row(key=1, *, team=57, name='Arsenal FC', when='2026-10-09T12:00:00Z', home=True, goals=(2, 1)):
    target, opponent = {'id': team, 'name': name}, {'id': 900, 'name': 'Synthetic Opponent'}
    return {'match_id': key, 'utc_date': when, 'status': 'FINISHED',
            'competition_code': 'PL', 'competition_id': 2021,
            'season_id': 2502, 'season_start': '2026-08-21', 'season_end': '2027-05-30',
            'requested_season': 2026, 'stage': 'REGULAR_SEASON',
            'home': target if home else opponent, 'away': opponent if home else target,
            'duration': 'REGULAR', 'score': {'fullTime': dict(zip(('home', 'away'), goals))},
            'provider': 'football-data.org', 'provider_updated_at': None}


def five():
    return [row(i, when=f'2026-10-0{i}T12:00:00Z') for i in range(1, 6)]


def snapshot(records=(), pending=(), *, fetched='2026-10-10T17:00:00Z', name='synthetic.json'):
    return Snapshot('PL', 2026, datetime.fromisoformat(fetched.replace('Z', '+00:00')),
                    tuple(records), tuple(pending), name)


def history(records=(), pending=(), *, snapshots=None, **overrides):
    options = dict(team_id=TEAM, competitions=['PL'], event_kickoff=NOW, verified_at=NOW)
    options.update(overrides)
    return build_history(Dataset(tuple(snapshots) if snapshots is not None else (snapshot(records, pending),)), **options)


class SyntheticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden in offline tests'))
        cls.guard.start()
        cls.addClassCleanup(cls.guard.stop)

    def test_statistics_overall_home_away_and_means(self):
        records = [row(1, goals=(3, 1)), row(2, goals=(2, 2)),
                   row(3, home=False, goals=(2, 0)), row(4, home=False, goals=(1, 4)), row(5, goals=(0, 0))]
        result = history(records)
        self.assertEqual(result['status'], 'verified_sample')
        stats = result['statistics']
        self.assertEqual(stats['overall']['played'], 5)
        self.assertEqual((stats['overall']['wins'], stats['overall']['draws'], stats['overall']['losses']), (2, 2, 1))
        self.assertEqual((stats['overall']['goals_for'], stats['overall']['goals_against']), (9, 6))
        self.assertEqual(stats['overall']['average_goals_for'], 1.8)
        self.assertEqual(stats['overall']['average_goals_against'], 1.2)
        self.assertEqual(stats['home']['played'], 3)
        self.assertEqual(stats['away']['played'], 2)
        self.assertEqual(stats['away']['wins'], 1)
        self.assertEqual(stats['overall']['points_90_minutes_3_1_0'], 8)

    def test_postponed_cancelled_and_nonfinal_never_become_results(self):
        pending = []
        for i, status in enumerate(['POSTPONED', 'CANCELLED', 'IN_PLAY', 'TIMED', 'AWARDED'], 20):
            r = row(i); r['status'] = status
            pending.append(r)
        result = history(five()[:4], pending)
        self.assertEqual(result['status'], 'insufficient_history')
        self.assertEqual(result['counts']['selected_results'], 4)
        self.assertEqual(set(result['diagnostics']['nonfinal_status_counts']), {'POSTPONED', 'CANCELLED', 'IN_PLAY', 'TIMED', 'AWARDED'})

    def test_identical_duplicates_merge_provenance_and_do_not_fill_five(self):
        result = history(snapshots=[snapshot(five()[:4], name='a.json'), snapshot([deepcopy(five()[0])], name='b.json')])
        self.assertEqual(result['counts']['selected_results'], 4)
        self.assertEqual(result['diagnostics']['duplicate_records'], 1)
        game = next(r for r in result['matches'] if r['match_id'] == 1)
        self.assertEqual(len(game['provenance']), 2)

    def test_partial_statistics_use_actual_sample_size(self):
        result = history(five()[:4])
        self.assertEqual(result['status'], 'insufficient_history')
        self.assertFalse(result['statistics']['sample_complete'])
        self.assertEqual(result['statistics']['overall']['played'], 4)
        self.assertEqual(result['statistics']['overall']['goals_for'], 8)
        self.assertEqual(result['statistics']['overall']['average_goals_for'], 2.0)

    def test_score_conflict_quarantines_all_variants(self):
        bad = deepcopy(five()[0]); bad['score']['fullTime']['home'] = 7
        result = history(five() + [bad])
        self.assertEqual(result['counts']['selected_results'], 4)
        self.assertEqual(result['diagnostics']['conflicts'][0]['match_id'], 1)
        self.assertNotIn(1, [r['match_id'] for r in result['matches']])

    def test_conflict_detected_even_if_other_variant_removes_target_team(self):
        changed = deepcopy(five()[0]); changed['home'] = {'id': 58, 'name': 'Another Team'}
        result = history(five() + [changed])
        self.assertEqual(result['counts']['selected_results'], 4)
        self.assertEqual(result['diagnostics']['conflicts'][0]['match_id'], 1)

    def test_incomplete_duplicate_cannot_hide_behind_complete_record(self):
        bad = deepcopy(five()[0]); bad['score']['fullTime']['home'] = None
        result = history(five() + [bad])
        self.assertEqual(result['counts']['selected_results'], 4)
        self.assertEqual(result['diagnostics']['duplicate_records'], 1)
        self.assertTrue(result['diagnostics']['incomplete'])
        self.assertTrue(result['diagnostics']['conflicts'])

    def test_finished_fixture_after_event_is_excluded(self):
        result = history([row(1, when='2026-10-10T17:30:00Z')], event_kickoff='2026-10-10T17:15:00Z')
        self.assertEqual(result['counts']['selected_results'], 0)
        self.assertEqual(result['diagnostics']['exclusions']['at_or_after_event_kickoff'], 1)

    def test_finished_fixture_future_to_verification_is_excluded(self):
        result = history([row(1, when='2026-10-10T19:00:00Z')], event_kickoff='2026-10-10T20:00:00Z')
        self.assertEqual(result['counts']['selected_results'], 0)
        self.assertEqual(result['diagnostics']['exclusions']['at_or_after_verification'], 1)

    def test_exact_upper_boundary_is_exclusive(self):
        result = history([row(1, when=NOW)])
        self.assertEqual(result['counts']['selected_results'], 0)
        self.assertEqual(result['diagnostics']['exclusions']['at_or_after_event_kickoff'], 1)
        self.assertEqual(result['diagnostics']['exclusions']['at_or_after_verification'], 1)

    def test_180_day_lower_boundary_inclusive_older_results_excluded(self):
        anchor = datetime(2026, 10, 10, 18, 5, tzinfo=timezone.utc)
        boundary = anchor - timedelta(days=180)
        result = history([row(1, when=boundary.isoformat()), row(2, when=(boundary-timedelta(microseconds=1)).isoformat())])
        self.assertEqual(result['counts']['valid_results_before_freshness'], 2)
        self.assertEqual(result['counts']['valid_results_within_180_days'], 1)
        self.assertEqual(result['diagnostics']['exclusions']['older_than_180_days'], 1)

    def test_five_old_results_are_insufficient_recent_history(self):
        result = history([row(i, when=f'2026-03-0{i}T12:00:00Z') for i in range(1, 6)])
        self.assertEqual(result['status'], 'insufficient_history')
        self.assertEqual(result['counts']['valid_results_before_freshness'], 5)
        self.assertEqual(result['counts']['selected_results'], 0)

    def test_timezone_offsets_are_compared_as_instants(self):
        a = history([row(1, when='2026-10-10T17:00:00Z')], event_kickoff='2026-10-10T19:00:00+02:00')
        b = history([row(1, when='2026-10-10T19:00:00+02:00')], event_kickoff='2026-10-10T17:00:00Z')
        self.assertEqual(a['counts'], b['counts'])
        self.assertEqual(a['counts']['selected_results'], 0)

    def test_dst_repeated_hour_has_distinct_offsets_and_correct_order(self):
        records = [row(1, when='2026-10-25T00:30:00Z'), row(2, when='2026-10-25T01:30:00Z')]
        result = history(snapshots=[snapshot(records, fetched='2026-10-26T10:00:00Z')],
                         event_kickoff='2026-10-26T12:00:00Z', verified_at='2026-10-26T12:00:00Z', display_timezone='Europe/Rome')
        self.assertEqual([r['match_id'] for r in result['matches']], [2, 1])
        self.assertTrue(result['matches'][0]['date_local'].endswith('+01:00'))
        self.assertTrue(result['matches'][1]['date_local'].endswith('+02:00'))

    def test_naive_timestamps_are_rejected(self):
        with self.assertRaisesRegex(InputError, 'invalid_or_naive_timestamp'):
            history(event_kickoff='2026-10-10T18:05:00')
        result = history([row(1, when='2026-10-09T12:00:00')])
        self.assertEqual(result['counts']['selected_results'], 0)
        self.assertTrue(result['diagnostics']['incomplete'])

    def test_penalty_shootout_uses_explicit_90_minutes_and_counts_draw(self):
        r = row(); r.update(duration='PENALTY_SHOOTOUT', score={'fullTime': {'home': 5, 'away': 4},
                            'regularTime': {'home': 1, 'away': 1}, 'extraTime': {'home': 0, 'away': 0},
                            'penalties': {'home': 4, 'away': 3}})
        result = history([r])
        self.assertEqual(result['statistics']['overall']['draws'], 1)
        self.assertEqual(result['statistics']['overall']['goals_for'], 1)
        self.assertEqual(result['matches'][0]['score_periods']['fullTime'], {'home': 5, 'away': 4})

    def test_extra_time_does_not_replace_90_minute_goals(self):
        r = row(); r.update(duration='EXTRA_TIME', score={'fullTime': {'home': 3, 'away': 2},
                            'regularTime': {'home': 2, 'away': 2}, 'extraTime': {'home': 1, 'away': 0}})
        result = history([r])
        self.assertEqual(result['statistics']['overall']['goals_for'], 2)
        self.assertEqual(result['statistics']['overall']['draws'], 1)

    def test_missing_regular_time_never_falls_back_to_penalty_score(self):
        r = row(); r['duration'] = 'PENALTY_SHOOTOUT'
        result = history([r])
        self.assertEqual(result['counts']['selected_results'], 0)
        self.assertTrue(result['diagnostics']['incomplete'])

    def test_similar_names_with_different_ids_never_merge(self):
        result = history([row(1)] + [row(i, team=58, name='Arsenal FC II') for i in range(2, 6)])
        self.assertEqual(result['counts']['selected_results'], 1)
        self.assertEqual(result['team']['observed_names'], ['Arsenal FC'])
        with self.assertRaisesRegex(InputError, 'invalid_canonical_team_id'):
            history(team_id='Arsenal FC')

    def test_same_id_name_alias_does_not_create_another_team(self):
        records = five(); records[0]['home']['name'] = 'Arsenal Football Club'
        result = history(records)
        self.assertEqual(result['counts']['selected_results'], 5)
        self.assertEqual(result['status'], 'verified_sample')
        self.assertEqual(len(result['diagnostics']['name_aliases']), 2)

    def test_absence_has_zero_count_and_unresolved_identity(self):
        result = history([])
        self.assertEqual(result['status'], 'identity_unresolved')
        self.assertEqual(result['history_status'], 'insufficient_history')
        self.assertEqual(result['counts']['selected_results'], 0)
        self.assertIsNone(result['statistics']['overall']['average_goals_for'])
        self.assertEqual(result['matches'], [])

    def test_known_team_without_finished_games_is_insufficient(self):
        pending = row(); pending['status'] = 'TIMED'
        result = history([], [pending])
        self.assertEqual(result['status'], 'insufficient_history')
        self.assertEqual(result['team']['identity_status'], 'exact_provider_id')

    def test_invalid_competition_and_identity_are_separate_from_incomplete(self):
        r = row(); r['competition_id'] = 2015
        result = history([r])
        self.assertTrue(result['diagnostics']['identity'])
        self.assertFalse(result['diagnostics']['incomplete'])

    def test_season_identity_cannot_be_coerced_from_float(self):
        r = row(); r['requested_season'] = 2026.0
        result = history([r])
        self.assertEqual(result['counts']['selected_results'], 0)
        self.assertEqual(result['diagnostics']['identity'][0]['code'], 'invalid_season_identity')

    def test_scope_and_provenance_cannot_be_reinterpreted(self):
        with self.assertRaisesRegex(InputError, 'invalid_competition_scope'):
            history(competitions=[{'code': 'PL'}])
        r = row(); r['source_url'] = 'https://example.invalid/untrusted'
        result = history([r])
        self.assertEqual(result['counts']['selected_results'], 0)
        self.assertNotIn('https://example.invalid/untrusted', json.dumps(result))
        self.assertEqual(result['diagnostics']['incomplete'][0]['code'], 'record_provenance_mismatch')

    def test_stale_sources_are_not_hidden_by_five_recent_results(self):
        result = history(five(), event_kickoff='2026-10-12T18:05:00Z', verified_at='2026-10-12T18:05:00Z')
        self.assertEqual(result['counts']['selected_results'], 5)
        self.assertEqual(result['status'], 'stale_source')
        self.assertIn('stale_source', {i['code'] for i in result['diagnostics']['sources']})

    def test_future_acquisition_cannot_be_used_at_verification_time(self):
        result = history(snapshots=[snapshot(five(), fetched='2026-10-10T19:00:00Z')])
        self.assertEqual(result['counts']['selected_results'], 0)
        self.assertIn('source_after_verification', {i['code'] for i in result['diagnostics']['sources']})

    def test_post_event_snapshot_requires_review_of_historical_availability(self):
        result = history(five(), event_kickoff='2026-10-10T16:00:00Z')
        self.assertEqual(result['status'], 'review_required')
        self.assertFalse(result['temporal_policy']['historical_publication_time_certified'])
        self.assertIn('post_event_acquisition', {i['code'] for i in result['diagnostics']['sources']})

    def test_unknown_or_malformed_status_is_rejected_safely(self):
        r = row(); r['status'] = {'unexpected': 'object'}
        result = history([r])
        self.assertEqual(result['counts']['selected_results'], 0)
        self.assertEqual(result['diagnostics']['incomplete'][0]['code'], 'unknown_match_status')

    def test_missing_scope_source_is_explicit(self):
        result = history(five(), competitions=['PL', 'CL'])
        self.assertEqual(result['status'], 'review_required')
        self.assertIn('missing_competition_snapshot', {i['code'] for i in result['diagnostics']['sources']})
        self.assertFalse(result['scope']['all_competitions_complete'])

    def test_loader_does_not_echo_errors_auth_headers_or_untrusted_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = {'schema_version': 2, 'competition': 'PL', 'requested_season': 2026,
                    'url': 'https://api.football-data.org/v4/competitions/PL/matches?season=2026',
                    'state': 'error', 'http_status': 403, 'errors': 'sensitive_provider_error_marker',
                    'headers': {'X-Auth-Token': 'synthetic_sensitive_marker'}}
            (Path(tmp)/'PL-2026.json').write_text(json.dumps(body))
            result = build_history(load_snapshots(tmp), team_id=TEAM, competitions=['PL'], event_kickoff=NOW, verified_at=NOW)
            serialized = json.dumps(result)
            self.assertNotIn('sensitive_provider_error_marker', serialized)
            self.assertNotIn('synthetic_sensitive_marker', serialized)
            self.assertEqual(result['diagnostics']['load'][0]['code'], 'source_unavailable')

    def test_invalid_cli_arguments_are_json_without_reflection(self):
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as error:
            main(['--unknown', 'synthetic_sensitive_marker'])
        self.assertEqual(error.exception.code, 2)
        self.assertNotIn('synthetic_sensitive_marker', output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['status'], 'input_error')

    def test_nonexistent_snapshot_directory_is_safe_json_error(self):
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(['--snapshots', '/not/a/real/snapshot/directory', '--team-id', TEAM,
                           '--competitions', 'PL', '--event-kickoff', NOW, '--verified-at', NOW])
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(output.getvalue())['error'], 'snapshot_directory_unavailable')


if __name__ == '__main__':
    unittest.main()
