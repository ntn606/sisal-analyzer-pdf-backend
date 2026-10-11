"""Integration tests against existing real snapshots, never synthetic scores."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

from history_provider_v2 import build_history, load_snapshots
from history_provider_v2.cli import main

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT/'fixtures/real'
NOW = '2026-10-10T18:05:00Z'


class RealSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        guard = patch.object(socket.socket, 'connect', side_effect=AssertionError('No network allowed'))
        guard.start(); cls.addClassCleanup(guard.stop)
        cls.dataset = load_snapshots(FIXTURES)

    def history(self, team, scope):
        return build_history(self.dataset, team_id=f'football-data.org:team:{team}',
                             competitions=scope, event_kickoff=NOW, verified_at=NOW, display_timezone='Europe/Rome')

    def test_all_ten_snapshots_load_without_modification(self):
        self.assertEqual(len(self.dataset.snapshots), 10)
        self.assertEqual(self.dataset.load_issues, ())
        for snap in self.dataset.snapshots:
            self.assertEqual(snap.retained_sha256, hashlib.sha256((FIXTURES/snap.snapshot_id).read_bytes()).hexdigest())

    def test_arsenal_aggregates_pl_and_champions_and_statistics(self):
        result = self.history(57, ['PL', 'CL'])
        self.assertEqual(result['status'], 'verified_sample')
        self.assertEqual([r['match_id'] for r in result['matches']], [560593, 560586, 560577, 575333, 560570])
        self.assertEqual({r['competition']['code'] for r in result['matches']}, {'PL', 'CL'})
        stats = result['statistics']['overall']
        self.assertEqual((stats['wins'], stats['draws'], stats['losses']), (4, 0, 1))
        self.assertEqual((stats['goals_for'], stats['goals_against']), (7, 5))
        self.assertEqual(result['statistics']['home']['played'], 2)
        self.assertEqual(result['statistics']['away']['played'], 3)

    def test_psg_aggregates_ligue1_and_champions(self):
        result = self.history(524, ['FL1', 'CL'])
        self.assertEqual(result['status'], 'verified_sample')
        self.assertEqual([r['match_id'] for r in result['matches']], [559675, 559691, 575332, 559697, 559702])
        self.assertEqual({r['competition']['code'] for r in result['matches']}, {'FL1', 'CL'})
        self.assertEqual(result['counts']['selected_results'], 5)

    def test_champions_five_requires_two_seasons(self):
        for team in (57, 524):
            result = self.history(team, ['CL'])
            self.assertEqual(result['status'], 'verified_sample')
            self.assertEqual(result['counts']['selected_results'], 5)
            self.assertEqual([r['season']['start_year'] for r in result['matches']].count(2026), 1)
            self.assertEqual([r['season']['start_year'] for r in result['matches']].count(2025), 4)

    def test_roma_champions_stays_insufficient(self):
        result = self.history(100, ['CL'])
        self.assertEqual(result['status'], 'insufficient_history')
        self.assertEqual(result['counts']['selected_results'], 1)

    def test_leipzig_has_four_final_results_and_inplay_excluded(self):
        result = self.history(721, ['BL1'])
        self.assertEqual(result['status'], 'insufficient_history')
        self.assertEqual(result['counts']['selected_results'], 4)
        self.assertEqual(result['diagnostics']['nonfinal_status_counts']['IN_PLAY'], 1)

    def test_actual_final_penalty_scores_are_separate(self):
        result = self.history(524, ['CL'])
        final = next(r for r in result['matches'] if r['match_id'] == 552096)
        self.assertEqual(final['score_periods']['fullTime'], {'home': 5, 'away': 4})
        self.assertEqual(final['score_90_minutes'], {'home': 1, 'away': 1})
        self.assertEqual(final['result_90_minutes'], 'D')
        self.assertEqual(final['goals_for_90_minutes'], 1)
        self.assertEqual(final['score_periods']['penalties'], {'home': 4, 'away': 3})

    def test_actual_cancelled_laliga_match_is_never_a_result(self):
        result = self.history(87, ['PD'])
        self.assertNotIn(564698, [r['match_id'] for r in result['matches']])
        self.assertEqual(result['diagnostics']['nonfinal_status_counts']['CANCELLED'], 1)

    def test_cli_real_json_contains_provenance_without_credentials(self):
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(['--team-id', 'football-data.org:team:57', '--competitions', 'PL,CL',
                              '--event-kickoff', NOW, '--verified-at', NOW])
        self.assertEqual(exit_code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result['status'], 'verified_sample')
        for r in result['matches']:
            self.assertTrue(r['provenance'])
            for source in r['provenance']:
                self.assertTrue(source['source_url'].startswith('https://api.football-data.org/v4/competitions/'))
                self.assertIsNotNone(source['retained_sha256'])
                self.assertNotIn('X-Auth-Token', source)
        self.assertNotIn('FOOTBALL_DATA_TOKEN', output.getvalue())
        self.assertFalse(result['scope']['all_competitions_complete'])


if __name__ == '__main__':
    unittest.main()
