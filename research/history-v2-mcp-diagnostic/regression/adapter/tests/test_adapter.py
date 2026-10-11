"""SYNTHETIC: all IDs, scores, links and publication observations are invented fixtures."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from scenarios import scenario,refresh_review,write_evidence
from identity_adapter import probe
from identity_adapter.cli import main
from identity_adapter.core import sisal_kickoff
from history_provider_v2 import Dataset
from history_provider_v2.provider import InputError


class SyntheticTests(unittest.TestCase):
    """Every case uses only synthetic data; no official mapping is certified."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.request,self.registry,self.dataset=scenario(self.root,synthetic=True)
        guard=patch.object(socket.socket,'connect',side_effect=AssertionError('Network forbidden'))
        guard.start(); self.addCleanup(guard.stop)

    def result(self):
        return probe(self.request,self.registry,self.dataset,self.root)

    def test_synthetic_positive_chain_checks_both_teams(self):
        result=self.result()
        self.assertEqual(result['status'],'diagnostic_available')
        self.assertTrue(all(t['identity_verified'] for t in result['checks']['teams'].values()))
        self.assertEqual(result['verification_scope'],'synthetic_only')
        self.assertTrue(result['diagnostic_statistics_allowed'])
        self.assertFalse(result['statistics_usable_in_production'])
        self.assertFalse(result['ready_for_quant'])
        self.assertEqual(result['histories']['home']['counts']['selected_results'],5)

    def test_synthetic_missing_mapping_blocks_all_statistics(self):
        self.registry['teams']=[]
        result=self.result()
        self.assertEqual(result['status'],'identity_unverified')
        self.assertEqual(result['histories'],{})
        self.assertFalse(result['diagnostic_statistics_allowed'])

    def test_synthetic_verified_boolean_without_review_is_not_proof(self):
        self.registry['teams'][0]['verification']['evidence_id']='not-present'
        result=self.result()
        self.assertFalse(result['checks']['teams']['home']['identity_verified'])
        self.assertTrue(result['checks']['teams']['away']['identity_verified'])
        self.assertEqual(result['histories'],{})

    def test_synthetic_similar_names_different_ids_remain_distinct(self):
        other=deepcopy(self.registry['teams'][0]);other['canonical_id']='local:team:other'
        other['provider_ids']={'api_football':901999,'football_data':1999}
        other['aliases'][0]['label']='Test club 57 B'
        self.registry['teams'].append(other);refresh_review(self.root,self.registry)
        result=self.result()
        self.assertEqual(result['status'],'diagnostic_available')
        self.assertEqual(result['checks']['teams']['home']['provider_ids']['football_data'],57)

    def test_synthetic_ambiguous_provider_id_mapping_is_distinct_state(self):
        other=deepcopy(self.registry['teams'][0]);other['canonical_id']='local:team:other'
        self.registry['teams'].append(other);refresh_review(self.root,self.registry)
        result=self.result()
        self.assertEqual(result['status'],'identity_unverified')
        self.assertEqual(result['checks']['teams']['home']['state'],'identity_ambiguous')
        self.assertEqual(result['histories'],{})

    def test_synthetic_correct_fixture_id_with_wrong_away_team(self):
        self.request['api_football']['away']['team_id']=901999
        result=self.result()
        self.assertTrue(result['checks']['teams']['home']['identity_verified'])
        self.assertFalse(result['checks']['teams']['away']['identity_verified'])
        self.assertIn('team_id_mismatch',result['checks']['teams']['away']['reasons'])
        self.assertEqual(result['status'],'identity_unverified')

    def test_synthetic_home_and_away_swap_is_blocked(self):
        af=self.request['api_football'];af['home'],af['away']=af['away'],af['home']
        result=self.result()
        self.assertFalse(any(t['identity_verified'] for t in result['checks']['teams'].values()))
        self.assertEqual(result['histories'],{})

    def test_synthetic_competition_mismatch(self):
        self.request['api_football']['competition_id']=123456789
        result=self.result()
        self.assertFalse(result['checks']['event']['verified'])
        self.assertEqual(result['histories'],{})

    def test_synthetic_season_mismatch(self):
        self.request['sisal_event']['season_start_year']=2025
        result=self.result()
        self.assertFalse(result['checks']['event']['verified'])

    def test_synthetic_kickoff_mismatch_not_tolerated(self):
        self.request['api_football']['kickoff']='2026-10-18T15:31:00Z'
        result=self.result()
        self.assertEqual(result['status'],'identity_unverified')
        self.assertEqual(result['histories'],{})

    def test_synthetic_equivalent_timezone_offsets_pass(self):
        self.request['api_football']['kickoff']='2026-10-18T17:30:00+02:00'
        record={k:v for k,v in self.request['api_football'].items() if k not in ('state','evidence_id','history_evidence_ids')}
        write_evidence(self.root,self.registry,'af-fixture','api_football_fixture',record)
        result=self.result()
        self.assertEqual(result['status'],'diagnostic_available')
        self.assertEqual(result['checks']['event']['kickoff_utc'],'2026-10-18T15:30:00+00:00')

    def test_synthetic_dst_ambiguous_local_time_needs_offset(self):
        event={'date':'2026-10-25','time':'02:30:00','timezone':'Europe/Rome'}
        with self.assertRaisesRegex(InputError,'ambiguous_or_inconsistent_local_time'):
            sisal_kickoff(event)
        event['utc_offset']='+01:00'
        self.assertEqual(sisal_kickoff(event).isoformat(),'2026-10-25T01:30:00+00:00')

    def test_synthetic_dst_nonexistent_time_is_blocked(self):
        with self.assertRaisesRegex(InputError,'nonexistent_local_time'):
            sisal_kickoff({'date':'2026-03-29','time':'02:30:00','timezone':'Europe/Rome'})

    def test_synthetic_unreviewed_abbreviation_is_not_identity(self):
        self.request['sisal_event']['home']='T57'
        result=self.result()
        self.assertIn('unreviewed_team_label',result['checks']['teams']['home']['reasons'])
        self.assertEqual(result['histories'],{})

    def test_synthetic_explicit_reviewed_abbreviation_passes(self):
        self.request['sisal_event']['home']='T57'
        self.registry['teams'][0]['aliases'].append({'provider':'sisal','label':'T57','valid_from':'2025-01-01','valid_until':'2027-12-31'})
        write_evidence(self.root,self.registry,'sisal','sisal_event',{k:v for k,v in self.request['sisal_event'].items() if k!='evidence_id'})
        refresh_review(self.root,self.registry)
        self.assertEqual(self.result()['status'],'diagnostic_available')

    def test_synthetic_expired_historical_name_is_blocked(self):
        self.registry['teams'][0]['aliases'][0]['valid_until']='2026-01-01'
        refresh_review(self.root,self.registry)
        result=self.result()
        self.assertIn('unreviewed_team_label',result['checks']['teams']['home']['reasons'])

    def test_synthetic_reserve_and_youth_profiles_do_not_merge(self):
        for kind,age in [('reserve','senior'),('youth','U19')]:
            with self.subTest(kind=kind):
                self.request['api_football']['home']['profile']['squad_kind']=kind
                self.request['api_football']['home']['profile']['age_group']=age
                result=self.result()
                self.assertIn('team_profile_mismatch',result['checks']['teams']['home']['reasons'])
                self.assertEqual(result['histories'],{})

    def test_synthetic_missing_event_binding_is_not_guessed(self):
        self.registry['bindings']=[]
        result=self.result()
        self.assertEqual(result['status'],'identity_unverified')
        self.assertEqual(result['histories'],{})

    def test_synthetic_provider_unavailable_distinct_from_identity(self):
        self.request['api_football']['state']='unavailable'
        result=self.result()
        self.assertEqual(result['status'],'provider_unavailable')
        self.assertEqual(result['histories'],{})

    def test_synthetic_missing_fd_snapshot_is_provider_unavailable(self):
        self.dataset=Dataset(())
        self.assertEqual(self.result()['status'],'provider_unavailable')

    def test_synthetic_real_mode_rejects_test_identity_evidence(self):
        self.request['evidence_mode']='real_only'
        result=self.result()
        self.assertEqual(result['status'],'identity_unverified')
        self.assertIn('synthetic_evidence_not_accepted',result['blockers'])
        self.assertEqual(result['histories'],{})

    def test_synthetic_modified_evidence_hash_blocks_identity(self):
        (self.root/'review.json').write_text('{}')
        result=self.result()
        self.assertIn('evidence_hash_mismatch',result['blockers'])
        self.assertFalse(result['diagnostic_statistics_allowed'])

    def test_synthetic_evidence_path_traversal_is_blocked(self):
        self.registry['evidence']['review']['file']='../review.json'
        self.assertIn('evidence_path_outside_root',self.result()['blockers'])

    def test_synthetic_cross_provider_duplicate_counted_once_with_provenance(self):
        row=self.dataset.snapshots[0].records[-1]
        af={'fixture_id':800000005,'home_team_id':900057,'away_team_id':900351,'competition_id':700000001,
            'season_start_year':2026,'kickoff':row['utc_date'],'status':'FINISHED','score_90_minutes':{'home':2,'away':1}}
        write_evidence(self.root,self.registry,'af-history','api_football_history',af)
        self.registry['match_links']=[{'canonical_match_id':'local:match:m5','api_football_fixture_id':800000005,
            'football_data_match_id':5,'validity':deepcopy(self.registry['bindings'][0]['validity'])}]
        refresh_review(self.root,self.registry)
        self.request['api_football']['history_evidence_ids']=['af-history','af-history']
        result=self.result()
        self.assertEqual(result['status'],'diagnostic_available')
        self.assertEqual(result['cross_provider_duplicate_matches'],1)
        self.assertEqual(result['histories']['home']['counts']['selected_results'],5)
        self.assertEqual(result['histories']['home']['statistics']['overall']['goals_for'],10)
        self.assertIn('cross_provider_provenance',result['histories']['home']['matches'][0])

    def test_synthetic_unmapped_cross_provider_history_not_joined_by_names(self):
        write_evidence(self.root,self.registry,'af-history','api_football_history',{
            'fixture_id':800000005,'home_team_id':900057,'away_team_id':900351,'competition_id':700000001,
            'season_start_year':2026,'kickoff':'2026-10-05T12:00:00Z','status':'FINISHED','score_90_minutes':{'home':2,'away':1}})
        self.request['api_football']['history_evidence_ids']=['af-history']
        result=self.result()
        self.assertIn('history_match_link_missing_or_ambiguous',result['blockers'])
        self.assertFalse(result['diagnostic_statistics_allowed'])
        self.assertEqual(result['histories'],{})

    def test_synthetic_cross_provider_score_conflict_blocks_all_statistics(self):
        af={'fixture_id':800000005,'home_team_id':900057,'away_team_id':900351,'competition_id':700000001,
            'season_start_year':2026,'kickoff':'2026-10-05T12:00:00Z','status':'FINISHED','score_90_minutes':{'home':9,'away':1}}
        write_evidence(self.root,self.registry,'af-history','api_football_history',af)
        self.registry['match_links']=[{'canonical_match_id':'local:match:m5','api_football_fixture_id':800000005,
            'football_data_match_id':5,'validity':deepcopy(self.registry['bindings'][0]['validity'])}]
        refresh_review(self.root,self.registry)
        self.request['api_football']['history_evidence_ids']=['af-history']
        result=self.result()
        self.assertEqual(result['status'],'data_conflict')
        self.assertEqual(result['histories'],{})
        self.assertFalse(result['diagnostic_statistics_allowed'])

    def test_synthetic_numeric_identity_is_not_coerced_from_float(self):
        self.request['api_football']['home']['team_id']=900057.0
        result=self.result()
        self.assertIn('invalid_api_football_fixture_identity',result['blockers'])
        self.assertEqual(result['histories'],{})

    def observations(self,late=False):
        for row in self.dataset.snapshots[0].records:
            key=f'observed-{row["match_id"]}'
            record={'football_data_match_id':row['match_id'],'status':'FINISHED','home_team_id':57,'away_team_id':351,
                    'score_90_minutes':{'home':2,'away':1},'observed_at':'2026-10-10T17:45:00Z' if late else '2026-10-10T17:00:00Z'}
            write_evidence(self.root,self.registry,key,'result_observation',record)
            self.registry['availability'][str(row['match_id'])]=key
        self.request.update(purpose='historical_backtest',analysis_at='2026-10-10T17:30:00Z')

    def test_synthetic_unknown_publication_time_blocks_backtest_statistics(self):
        self.request.update(purpose='historical_backtest',analysis_at='2026-10-10T17:30:00Z')
        result=self.result()
        self.assertEqual(result['status'],'temporal_unverified')
        self.assertFalse(result['temporal']['backtest_availability_verified'])
        self.assertIsNone(result['histories']['home']['statistics'])

    def test_synthetic_observed_result_after_simulated_analysis_is_blocked(self):
        self.observations(late=True)
        result=self.result()
        self.assertEqual(result['status'],'temporal_unverified')
        self.assertTrue(all(r['code']=='availability_not_proven_by_analysis' for r in result['temporal']['reasons']))
        self.assertIsNone(result['histories']['away']['statistics'])

    def test_synthetic_results_explicitly_published_after_analysis_are_blocked(self):
        self.observations(late=True)
        for ref in self.registry['availability'].values():
            payload=json.loads((self.root/f'{ref}.json').read_text())
            payload['record'].update(published_at='2026-10-10T17:40:00Z',publication_timestamp_basis='explicit_source_publication')
            write_evidence(self.root,self.registry,ref,'result_observation',payload['record'])
        result=self.result()
        self.assertEqual(result['status'],'temporal_unverified')
        self.assertTrue(all(r['code']=='result_published_after_analysis' for r in result['temporal']['reasons']))
        self.assertIsNone(result['histories']['home']['statistics'])

    def test_synthetic_identity_valid_today_is_not_assumed_valid_for_old_results(self):
        self.registry['teams'][0]['validity']['from']='2026-10-03T00:00:00Z'
        refresh_review(self.root,self.registry)
        result=self.result()
        self.assertTrue(result['checks']['teams']['home']['identity_verified'])
        self.assertIn('mapping_outside_validity',result['blockers'])
        self.assertEqual(result['histories'],{})

    def test_synthetic_archived_observation_before_analysis_verifies_only_test_availability(self):
        self.observations()
        result=self.result()
        self.assertEqual(result['status'],'diagnostic_available')
        self.assertTrue(result['temporal']['backtest_availability_verified'])
        self.assertFalse(result['temporal']['first_publication_time_verified'])
        self.assertEqual(result['verification_scope'],'synthetic_only')
        self.assertFalse(result['ready_for_quant'])

    def test_synthetic_unknown_arguments_not_reflected_in_cli(self):
        output=io.StringIO()
        with redirect_stdout(output),self.assertRaises(SystemExit):
            main(['--not-supported','synthetic-sensitive-marker'])
        self.assertNotIn('synthetic-sensitive-marker',output.getvalue())
        self.assertFalse(json.loads(output.getvalue())['ready_for_quant'])


if __name__=='__main__':unittest.main()
