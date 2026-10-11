"""Actual saved replays and explicitly synthetic negative mutations. No HTTP."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import hashlib,json,shutil,socket,tempfile,unittest
from unittest.mock import patch
from history_v2_probe import ProbeService
ROOT=Path(__file__).resolve().parents[1]
STAMP=max(datetime.fromisoformat(json.loads(p.read_text())['verified_at']) for p in (ROOT/'cases').glob('*/request-asof-observation.json'))+timedelta(seconds=1)

def read(path):return json.loads(path.read_text())
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def reanchor(root):
 catalog=read(root/'catalog.json')
 for entry in catalog['events']:
  for name in entry['files']:entry['files'][name]=hashlib.sha256((root/name).read_bytes()).hexdigest()
 write(root/'catalog.json',catalog)

class RealSavedReplayTests(unittest.TestCase):
 data_origin='real_saved_official_evidence_local_review_offline_replay'
 def setUp(self):
  guard=patch.object(socket.socket,'connect',side_effect=AssertionError('Offline test forbids network'));guard.start();self.addCleanup(guard.stop)
  self.service=ProbeService(ROOT,clock=lambda:STAMP)
 def invoke(self,avv='1885',service=None):return (service or self.service).football_history_v2_probe('36411',avv,'2026-10-12')
 def safe(self,result):
  self.assertTrue(result['diagnostic_only']);self.assertFalse(result['ready_for_analysis']);self.assertFalse(result['ready_for_quant']);self.assertFalse(result['statistics_usable_in_production'])
  self.assertEqual(result['provenance']['new_api_requests'],0)
 def test_real_premier_league_both_verified_and_five_results(self):
  result=self.invoke();self.safe(result);self.assertEqual(result['status'],'diagnostic_available')
  for side in ('home','away'):
   self.assertTrue(result['checks']['teams'][side]['identity_verified']);self.assertEqual(result['histories'][side]['counts']['selected_results'],5)
   self.assertEqual(result['histories'][side]['scope']['observed_competitions'],['PL'])
 def test_real_laliga_distinct_competition_preserved(self):
  result=self.invoke('2282');self.safe(result);self.assertEqual(result['status'],'diagnostic_available')
  self.assertEqual(result['checks']['teams']['home']['provider_ids'],{'api_football':539,'football_data':88})
  self.assertTrue(all(m['competition']['code']=='PD' for h in result['histories'].values() for m in h['matches']))
 def test_real_availability_observed_not_first_publication(self):
  result=self.invoke();self.assertEqual(result['temporal']['state'],'verified_as_of_observation');self.assertFalse(result['temporal']['first_publication_time_verified'])
  for h in result['histories'].values():
   for m in h['matches']:
    self.assertTrue(m['availability']['verified_by_analysis_time']);self.assertIsNone(m['availability']['first_published_at'])
 def test_real_repeated_probe_reuses_dataset_without_network(self):
  first=self.invoke();second=self.invoke('2282');self.assertFalse(first['provenance']['dataset_reused']);self.assertTrue(second['provenance']['dataset_reused']);self.safe(second)

class SyntheticMutationTests(RealSavedReplayTests):
 data_origin='synthetic_mutation_of_real_saved_inputs_not_live_validation'
 def setUp(self):
  super().setUp();self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  for name in ('cases','live'):
   shutil.copytree(ROOT/name,self.root/name)
  shutil.copyfile(ROOT/'catalog.json',self.root/'catalog.json')
  self.service=ProbeService(self.root,clock=lambda:STAMP)
 def alter(self,relative,mutator):
  path=self.root/relative;body=read(path);mutator(body);write(path,body);reanchor(self.root)
 def test_invalid_or_sensitive_input_is_not_echoed(self):
  result=self.service.football_history_v2_probe('fake-secret-never-echo','1885','2026-10-12')
  self.assertNotIn('fake-secret-never-echo',json.dumps(result));self.assertEqual(result['status'],'identity_unverified');self.safe(result)
 def test_missing_mapping_blocks_both_histories(self):
  self.alter('cases/coventry-newcastle/registry.json',lambda x:x.update(teams=[]))
  result=self.invoke();self.assertEqual(result['status'],'identity_unverified');self.assertEqual(result['histories'],{})
 def test_wrong_team_identifier_is_blocked(self):
  self.alter('cases/coventry-newcastle/request-diagnostic.json',lambda x:x['api_football']['home'].update(team_id=34))
  result=self.invoke();self.assertEqual(result['status'],'identity_unverified');self.assertFalse(result['diagnostic_statistics_allowed'])
 def test_wrong_competition_is_blocked(self):
  self.alter('cases/coventry-newcastle/request-diagnostic.json',lambda x:x['api_football'].update(competition_id=140))
  self.assertEqual(self.invoke()['status'],'identity_unverified')
 def test_provider_unavailable_is_explicit(self):
  self.alter('cases/coventry-newcastle/request-diagnostic.json',lambda x:x['football_data'].update(state='unavailable'))
  self.assertEqual(self.invoke()['status'],'provider_unavailable')
 def test_four_results_are_insufficient(self):
  self.alter('live/snapshots/PL-2026.json',lambda x:x.update(records=[m for m in x['records'] if m['match_id']!=560542]))
  result=self.invoke();self.assertEqual(result['status'],'insufficient_history');self.assertEqual(result['histories']['home']['counts']['selected_results'],4)
  self.assertTrue(all(h['statistics'] is None for h in result['histories'].values()))
 def test_identical_duplicate_does_not_inflate_count(self):
  def duplicate(x):x['records'].append(deepcopy(next(m for m in x['records'] if m['match_id']==560542)))
  self.alter('live/snapshots/PL-2026.json',duplicate)
  result=self.invoke();self.assertEqual(result['status'],'diagnostic_available');self.assertEqual(result['histories']['home']['counts']['selected_results'],5)
  self.assertEqual(result['histories']['home']['diagnostics']['duplicate_records'],1)
 def test_conflicting_duplicate_blocks_statistics(self):
  def duplicate(x):
   row=deepcopy(next(m for m in x['records'] if m['match_id']==560542));row['score']['fullTime']['home']+=1;x['records'].append(row)
  self.alter('live/snapshots/PL-2026.json',duplicate)
  result=self.invoke();self.assertNotEqual(result['status'],'diagnostic_available');self.assertFalse(result['diagnostic_statistics_allowed'])
  self.assertTrue(result['histories']['home']['diagnostics']['conflicts'])
 def test_missing_availability_proof_is_temporal_unverified(self):
  self.alter('cases/coventry-newcastle/registry.json',lambda x:x.update(availability={}))
  self.assertEqual(self.invoke()['status'],'temporal_unverified')
 def test_call_at_kickoff_blocks_cached_statistics(self):
  self.invoke();self.service.clock=lambda:datetime(2026,10,12,19,tzinfo=timezone.utc)
  result=self.invoke();self.assertEqual(result['status'],'temporal_unverified');self.assertIn('event_already_started',result['blockers']);self.assertEqual(result['histories'],{});self.safe(result)
 def test_call_after_kickoff_is_blocked(self):
  self.service.clock=lambda:datetime(2026,10,12,19,1,tzinfo=timezone.utc)
  self.assertEqual(self.invoke()['status'],'temporal_unverified')
 def test_old_event_evidence_is_stale(self):
  self.service.clock=lambda:STAMP+timedelta(hours=2)
  self.assertEqual(self.invoke()['status'],'source_stale')
 def test_duplicate_binding_is_ambiguous(self):
  catalog=read(self.root/'catalog.json');catalog['events'].append(deepcopy(catalog['events'][0]));write(self.root/'catalog.json',catalog)
  self.assertEqual(self.invoke()['status'],'identity_unverified')
 def test_unreviewed_synthetic_evidence_is_rejected(self):
  self.alter('cases/coventry-newcastle/evidence/proof-review.json',lambda x:x.update(origin='synthetic'))
  result=self.invoke();self.assertEqual(result['status'],'identity_unverified');self.assertIn('synthetic_evidence_not_accepted',result['blockers'])
 def test_path_traversal_is_rejected(self):
  catalog=read(self.root/'catalog.json');catalog['events'][0]['files']['../outside.json']='0'*64;write(self.root/'catalog.json',catalog)
  self.assertEqual(self.invoke()['status'],'identity_unverified')
 def test_tampered_snapshot_cannot_use_old_dataset(self):
  self.invoke();path=self.root/'live/snapshots/PL-2026.json';path.write_text(path.read_text()+' ')
  result=self.invoke();self.assertEqual(result['status'],'data_conflict');self.assertFalse(result['diagnostic_statistics_allowed'])
 def test_future_finished_match_is_not_selected(self):
  def add(x):
   row=deepcopy(x['records'][0]);row.update(match_id=999999999,utc_date='2026-10-13T19:00:00Z',home={'id':1076,'name':'Coventry City FC'},away={'id':67,'name':'Newcastle United FC'});x['records'].append(row)
  self.alter('live/snapshots/PL-2026.json',add)
  result=self.invoke();self.assertEqual(result['status'],'diagnostic_available')
  self.assertNotIn(999999999,[m['match_id'] for h in result['histories'].values() for m in h['matches']])
 def test_missing_snapshot_is_provider_unavailable(self):
  (self.root/'live/snapshots/PL-2026.json').unlink();self.assertEqual(self.invoke()['status'],'provider_unavailable')


 def test_no_history_preserves_zero_count(self):
  self.alter('live/snapshots/PL-2026.json',lambda x:x.update(records=[m for m in x['records'] if 1076 not in (m['home']['id'],m['away']['id'])]))
  result=self.invoke();self.assertEqual(result['status'],'insufficient_history');self.assertEqual(result['histories']['home']['counts']['selected_results'],0)
 def test_wrong_event_date_is_not_matched(self):
  result=self.service.football_history_v2_probe('36411','1885','2026-10-13');self.assertEqual(result['status'],'identity_unverified')
 def test_no_odds_or_prediction_keys_in_response(self):
  result=self.invoke()
  def check(value):
   if isinstance(value,dict):
    for key,item in value.items():
     self.assertNotIn(key.lower(),{'odds','quotes','predictions','probabilities','value_bet','authorization','x-auth-token','x-apisports-key'});check(item)
   elif isinstance(value,list):
    for item in value:check(item)
  check(result)
 def test_future_observation_is_temporal_unverified(self):
  self.alter('cases/coventry-newcastle/evidence/proof-observation-560589.json',lambda x:x.update(acquired_at=(STAMP+timedelta(minutes=1)).isoformat()))
  result=self.invoke();self.assertEqual(result['status'],'temporal_unverified');self.assertEqual(result['histories'],{})

# Prevent inherited positive methods from being mislabeled as synthetic tests.
def load_tests(loader,standard,pattern):
 suite=unittest.TestSuite()
 for cls in (RealSavedReplayTests,SyntheticMutationTests):suite.addTests(cls(name) for name in cls.__dict__ if name.startswith('test_'))
 return suite
