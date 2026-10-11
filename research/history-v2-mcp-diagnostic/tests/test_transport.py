"""Provider transport simulation only: every HTTP response/clock is mocked."""
from datetime import datetime,timezone
from email.message import Message
import io,json,os,unittest,urllib.error
from unittest.mock import Mock,patch
from history_v2_probe.transport import ProviderTransport,route
FAKE='synthetic-credential-sentinel';RAW='synthetic-original-provider-error'

def response(body,headers=None,status=200):
 value=Mock();value.status=status;value.headers=Message();value.headers['Content-Type']='application/json'
 for k,v in (headers or {}).items():value.headers[k]=str(v)
 value.read.return_value=json.dumps(body).encode();value.__enter__=Mock(return_value=value);value.__exit__=Mock(return_value=False);return value

class SimulatedTransportTests(unittest.TestCase):
 data_origin='synthetic_mocked_provider_responses_no_live_calls'
 def setUp(self):
  guard=patch.dict(os.environ,{'FOOTBALL_DATA_TOKEN':FAKE,'API_FOOTBALL_KEY':FAKE});guard.start();self.addCleanup(guard.stop)
  self.now=[0.0];self.opener=Mock();self.opener.open.side_effect=AssertionError('Unexpected simulated call')
  self.shared=Mock(return_value=True)
  self.client=ProviderTransport(self.shared,self.opener,clock=lambda:self.now[0],utc_clock=lambda:datetime(2026,10,11,21,tzinfo=timezone.utc))
 def safe(self,value):
  text=json.dumps(value)
  for forbidden in (FAKE,RAW,'X-Auth-Token','x-apisports-key','Authorization'):self.assertNotIn(forbidden,text)
 def test_https_and_documented_auth_header_are_used(self):
  self.opener.open.side_effect=None;self.opener.open.return_value=response({'id':77,'utcDate':'2026-10-10T12:00:00Z','status':'FINISHED'})
  result=self.client.get('football_data','match',identifier=77);self.assertEqual(result['state'],'retrieved');self.safe(result)
  request=self.opener.open.call_args.args[0];self.assertEqual(request.full_url,'https://api.football-data.org/v4/matches/77');self.assertEqual(request.get_header('X-auth-token'),FAKE);self.assertEqual(self.opener.open.call_args.kwargs['timeout'],20)
 def test_cached_success_does_not_repeat_request(self):
  self.opener.open.side_effect=None;self.opener.open.return_value=response({'id':77})
  self.client.get('football_data','match',identifier=77);result=self.client.get('football_data','match',identifier=77)
  self.assertTrue(result['cache_reused']);self.assertEqual(self.opener.open.call_count,1);self.assertEqual(self.shared.call_count,1)
 def test_no_live_request_without_shared_budget(self):
  result=ProviderTransport(opener=self.opener).get('football_data','match',identifier=77)
  self.assertEqual(result['code'],'shared_budget_unconfigured');self.opener.open.assert_not_called()
 def test_missing_credential_is_explicit(self):
  with patch.dict(os.environ,{'FOOTBALL_DATA_TOKEN':''}):result=self.client.get('football_data','match',identifier=77)
  self.assertEqual(result['code'],'credential_missing');self.opener.open.assert_not_called()
 def test_free_plan_error_with_http_200_is_not_success(self):
  self.client.af_remaining=80;self.opener.open.side_effect=None;self.opener.open.return_value=response({'errors':{'plan':'Free plan '+RAW+' '+FAKE}})
  result=self.client.get('api_football','fixture',identifier=77);self.assertEqual(result['http_status'],200);self.assertEqual(result['state'],'provider_plan_restricted');self.safe(result);self.assertEqual(self.client.cache,{})
 def test_authentication_failure_does_not_return_provider_body(self):
  self.opener.open.side_effect=urllib.error.HTTPError('https://api.football-data.org/v4/matches/77',401,RAW,{},io.BytesIO((RAW+FAKE).encode()))
  result=self.client.get('football_data','match',identifier=77);self.assertEqual(result['state'],'provider_authentication_failed');self.safe(result)
 def test_429_honors_retry_after_without_automatic_retry(self):
  headers=Message();headers['Retry-After']='120'
  self.opener.open.side_effect=urllib.error.HTTPError('https://api.football-data.org/v4/matches/77',429,RAW,headers,io.BytesIO())
  first=self.client.get('football_data','match',identifier=77);second=self.client.get('football_data','match',identifier=78)
  self.assertEqual(first['state'],'provider_rate_limited');self.assertEqual(second['state'],'provider_rate_limited');self.assertGreaterEqual(second['retry_after_seconds'],120);self.assertEqual(self.opener.open.call_count,1)
 def test_quota_reset_waits_when_one_request_remains(self):
  self.opener.open.side_effect=None;self.opener.open.return_value=response({'id':77},{'x-requests-available-minute':1,'x-requestcounter-reset':60})
  self.client.get('football_data','match',identifier=77);result=self.client.get('football_data','match',identifier=78)
  self.assertGreaterEqual(result['retry_after_seconds'],60);self.assertEqual(self.opener.open.call_count,1)
 def test_daily_reserve_protects_railway_budget(self):
  self.client.af_remaining=20;result=self.client.get('api_football','fixture',identifier=77)
  self.assertEqual(result['code'],'shared_daily_reserve_or_unknown_quota');self.opener.open.assert_not_called()
 def test_nonmonotonic_quota_never_increases_balance(self):
  self.client.af_remaining=50;self.opener.open.side_effect=None;self.opener.open.return_value=response({'response':[]},{'x-ratelimit-requests-remaining':90})
  self.client.get('api_football','fixture',identifier=77);self.assertEqual(self.client.af_remaining,49)
 def test_timeout_returns_safe_error(self):
  self.opener.open.side_effect=TimeoutError(RAW+FAKE);result=self.client.get('football_data','match',identifier=77)
  self.assertEqual(result['code'],'provider_timeout_or_transport_error');self.safe(result)
 def test_redirect_response_is_not_followed(self):
  self.opener.open.side_effect=urllib.error.HTTPError('https://api.football-data.org/v4/matches/77',302,RAW,{'Location':'https://evil.example'},io.BytesIO())
  result=self.client.get('football_data','match',identifier=77);self.assertEqual(result['code'],'redirect_not_allowed');self.assertEqual(self.opener.open.call_count,1)
 def test_unallowed_endpoint_cannot_send_a_credential(self):
  result=self.client.get('football_data','https://evil.example',identifier=77);self.assertEqual(result['code'],'endpoint_not_allowed');self.opener.open.assert_not_called()
 def test_provider_echoing_credential_is_rejected_before_cache(self):
  self.opener.open.side_effect=None;self.opener.open.return_value=response({'id':77,'homeTeam':{'id':1,'name':FAKE}})
  result=self.client.get('football_data','match',identifier=77);self.assertEqual(result['state'],'data_unverified');self.safe(result);self.assertEqual(self.client.cache,{})
 def test_unsafe_exception_is_not_exposed(self):
  self.opener.open.side_effect=RuntimeError(RAW+FAKE);result=self.client.get('football_data','match',identifier=77)
  self.assertEqual(result['code'],'provider_transport_failure');self.safe(result)
 def test_external_atomic_budget_denial_precedes_network(self):
  self.shared.return_value=False;result=self.client.get('football_data','match',identifier=77)
  self.assertEqual(result['code'],'shared_budget_exhausted');self.opener.open.assert_not_called()
