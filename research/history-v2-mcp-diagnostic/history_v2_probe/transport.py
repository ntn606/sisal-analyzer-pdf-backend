"""Optional operator transport. Not reachable from the MCP tool.

No live request unless an operator supplies an atomic shared-budget reservation.
Cache stores only normalized football data and safe metadata, never headers/auth
or raw errors. Quotas are conservative and never increase from contradictory
remaining-count headers. Multi-process/account coordination belongs to the
supplied shared-budget implementation; this module does not claim to replace it.
"""
from copy import deepcopy
from datetime import datetime,timezone
import json,os,ssl,threading,time,urllib.error,urllib.request
from urllib.parse import urlencode

CODES={'SA','PL','PD','BL1','FL1','DED','PPL','ELC','CL'}
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None

def positive(value):return type(value) is int and value>0

def route(provider,endpoint,identifier=None,competition=None,season=None):
 if provider=='api_football':
  if endpoint=='status' and identifier is None and competition is None and season is None:return 'https://v3.football.api-sports.io/status','x-apisports-key','API_FOOTBALL_KEY'
  if endpoint=='fixture' and positive(identifier) and competition is None and season is None:return f'https://v3.football.api-sports.io/fixtures?id={identifier}','x-apisports-key','API_FOOTBALL_KEY'
 if provider=='football_data':
  if endpoint in ('match','team') and positive(identifier) and competition is None and season is None:return f'https://api.football-data.org/v4/{"matches" if endpoint=="match" else "teams"}/{identifier}','X-Auth-Token','FOOTBALL_DATA_TOKEN'
  if endpoint=='competition_matches' and competition in CODES and type(season) is int and 2000<=season<=2100 and identifier is None:return f'https://api.football-data.org/v4/competitions/{competition}/matches?'+urlencode({'season':season}),'X-Auth-Token','FOOTBALL_DATA_TOKEN'
 raise ValueError('endpoint_not_allowed')

def fields(obj,names):return {key:obj.get(key) for key in names} if isinstance(obj,dict) else {}
def team(obj):
 clean=fields(obj,('id','name','shortName','tla','founded','venue','lastUpdated'))
 clean['area']=fields(obj.get('area'),('id','name','code'))
 clean['runningCompetitions']=[fields(c,('id','name','code','type')) for c in obj.get('runningCompetitions',[]) if isinstance(c,dict)]
 return clean

def match(obj):
 clean=fields(obj,('id','utcDate','status','stage','matchday','lastUpdated'))
 clean['competition']=fields(obj.get('competition'),('id','name','code','type'))
 clean['season']=fields(obj.get('season'),('id','startDate','endDate'))
 clean['homeTeam']=fields(obj.get('homeTeam'),('id','name'));clean['awayTeam']=fields(obj.get('awayTeam'),('id','name'))
 score=obj.get('score',{});clean['score']=fields(score,('winner','duration'))
 for period in ('fullTime','regularTime','halfTime','extraTime','penalties'):
  if isinstance(score.get(period),dict):clean['score'][period]=fields(score[period],('home','away'))
 return clean

def normalize(provider,endpoint,body):
 if not isinstance(body,dict):raise ValueError('invalid_response')
 if provider=='football_data':
  if endpoint=='team':
   if not positive(body.get('id')):raise ValueError('invalid_response')
   return team(body)
  if endpoint=='match':
   if not positive(body.get('id')):raise ValueError('invalid_response')
   return match(body)
  if not isinstance(body.get('matches'),list):raise ValueError('invalid_response')
  return {'matches':[match(row) for row in body['matches'] if isinstance(row,dict)]}
 if endpoint=='status':
  response=body.get('response',{});requests=response.get('requests',{})
  if not all(type(requests.get(k)) is int for k in ('current','limit_day')):raise ValueError('invalid_response')
  return {'requests':fields(requests,('current','limit_day')),'subscription':fields(response.get('subscription',{}),('plan','active'))}
 if not isinstance(body.get('response'),list):raise ValueError('invalid_response')
 rows=[]
 for row in body['response']:
  fixture=row.get('fixture',{});league=row.get('league',{});score=row.get('score',{})
  rows.append({'fixture':{**fields(fixture,('id','date','timestamp','timezone')),'status':fields(fixture.get('status'),('short','long','elapsed')),'venue':fields(fixture.get('venue'),('id','name','city'))},'league':fields(league,('id','name','country','season','round')),'teams':{side:fields(row.get('teams',{}).get(side),('id','name')) for side in ('home','away')},'goals':fields(row.get('goals'),('home','away')),'score':{period:fields(score.get(period),('home','away')) for period in ('halftime','fulltime','extratime','penalty')}})
 return {'response':rows,'results':body.get('results')}

class ProviderTransport:
 def __init__(self,shared_budget=None,opener=None,clock=time.monotonic,utc_clock=None,timeout=20):
  if not 1<=timeout<=25:raise ValueError('invalid_timeout')
  self.shared_budget=shared_budget;self.clock=clock;self.utc_clock=utc_clock or (lambda:datetime.now(timezone.utc))
  self.timeout=timeout;self.lock=threading.RLock();self.cache={};self.next_call={};self.af_remaining=None
  self.opener=opener or urllib.request.build_opener(NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
 def get(self,provider,endpoint,**parameters):
  with self.lock:
   try:url,header,variable=route(provider,endpoint,**parameters)
   except (ValueError,TypeError):return {'state':'provider_unavailable','code':'endpoint_not_allowed'}
   stamp=self.clock();cached=self.cache.get(url)
   if cached and stamp<cached[0]:return {**deepcopy(cached[1]),'cache_reused':True}
   if self.shared_budget is None:return {'state':'provider_unavailable','code':'shared_budget_unconfigured'}
   token=os.environ.get(variable,'').strip()
   if not token:return {'state':'provider_unavailable','code':'credential_missing'}
   if stamp<self.next_call.get(provider,0):return {'state':'provider_rate_limited','code':'quota_wait_required','retry_after_seconds':max(1,int(self.next_call[provider]-stamp)+1)}
   if provider=='api_football' and endpoint!='status' and (self.af_remaining is None or self.af_remaining<=20):return {'state':'provider_rate_limited','code':'shared_daily_reserve_or_unknown_quota'}
   try:reserved=self.shared_budget(provider,url)
   except Exception:return {'state':'provider_unavailable','code':'shared_budget_unavailable'}
   if reserved is not True:return {'state':'provider_rate_limited','code':'shared_budget_exhausted'}
   self.next_call[provider]=stamp+8
   if provider=='api_football' and self.af_remaining is not None:self.af_remaining-=1
   result={'state':'provider_unavailable','source':url,'request_started_at':self.utc_clock().isoformat(),'http_status':None,'quota':{},'cache_reused':False}
   try:
    request=urllib.request.Request(url,headers={header:token,'Accept':'application/json'})
    with self.opener.open(request,timeout=self.timeout) as response:
     result['http_status']=response.status;self._quotas(provider,response.headers,result)
     if response.headers.get_content_type()!='application/json':raise ValueError('invalid_response')
     raw=response.read(5_000_001)
    if len(raw)>5_000_000:raise ValueError('response_too_large')
    body=json.loads(raw)
    errors=body.get('errors') if isinstance(body,dict) else None
    if not errors and isinstance(body,dict) and body.get('errorCode'):errors=body.get('message') or 'provider_reported_error'
    if errors:
     words=json.dumps(errors).lower()
     code='provider_plan_restricted' if any(w in words for w in ('free','subscription','plan')) else 'provider_rate_limited' if any(w in words for w in ('limit','quota')) else 'provider_parameters_rejected' if any(w in words for w in ('parameter','invalid')) else 'provider_reported_error'
     result.update(state=code,code=code)
    else:
     clean=normalize(provider,endpoint,body)
     # Reject even a provider field accidentally echoing either live credential.
     serialized=json.dumps(clean)
     if any(value and value in serialized for value in (os.environ.get('API_FOOTBALL_KEY','').strip(),os.environ.get('FOOTBALL_DATA_TOKEN','').strip())):raise ValueError('sensitive_payload_rejected')
     result.update(state='retrieved',data=clean)
   except urllib.error.HTTPError as error:
    result['http_status']=error.code;self._quotas(provider,error.headers,result)
    if error.code==429:self.next_call[provider]=max(self.next_call.get(provider,0),self.clock()+61)
    result.update(state='provider_authentication_failed' if error.code in (401,403) else 'provider_rate_limited' if error.code==429 else 'provider_unavailable',code='redirect_not_allowed' if 300<=error.code<400 else 'provider_http_failure')
   except (TimeoutError,urllib.error.URLError):result.update(state='provider_unavailable',code='provider_timeout_or_transport_error')
   except (ValueError,KeyError,TypeError,AttributeError):result.update(state='data_unverified',code='invalid_or_sensitive_provider_payload')
   except Exception:result.update(state='provider_unavailable',code='provider_transport_failure')
   result['response_completed_at']=self.utc_clock().isoformat()
   if result['state']=='retrieved':self.cache[url]=(self.clock()+(60 if endpoint=='status' else 900),deepcopy(result))
   return result
 def _quotas(self,provider,headers,result):
  if headers is None:return
  for name in ('x-ratelimit-requests-remaining','x-ratelimit-requests-limit','x-ratelimit-remaining','x-requests-available-minute','x-requestcounter-reset','retry-after'):
   value=headers.get(name)
   if value and value.isascii() and value.isdigit():result['quota'][name]=int(value)
  quota=result['quota'];delay=quota.get('retry-after',0)
  if quota.get('x-requests-available-minute',10)<=1:delay=max(delay,quota.get('x-requestcounter-reset',60)+1)
  if quota.get('x-ratelimit-remaining',10)<=2:delay=max(delay,61)
  if delay:self.next_call[provider]=max(self.next_call.get(provider,0),self.clock()+delay)
  if provider=='api_football':
   reported=quota.get('x-ratelimit-requests-remaining')
   if reported is not None:self.af_remaining=reported if self.af_remaining is None else min(self.af_remaining,reported)
