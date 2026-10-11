"""Bounded official football-data.org diagnostics; reuse the snapshot client."""
import os, sys, json, time
from datetime import datetime, timezone
import collect_evidence as c
sys.path.insert(0,'/workspace/research/history-v2-football-data-free/scripts')
from probe_free import Client

def team(body):
 return {k:body.get(k) for k in ('id','name','shortName','tla','address','website','founded','venue','area','runningCompetitions','lastUpdated')}

def match(body):
 return {k:body.get(k) for k in ('id','utcDate','status','competition','season','homeTeam','awayTeam','score','stage','matchday','lastUpdated')}

def pause(previous):
 elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(previous['response_completed_at'])).total_seconds()
 quota=previous.get('quota',{})
 seconds=max(8,quota.get('retry-after',0))
 if quota.get('x-requests-available-minute',10)<=1:
  seconds=max(seconds,quota.get('x-requestcounter-reset',60)+1)
 while seconds-elapsed>0:
  time.sleep(min(10,seconds-elapsed))
  elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(previous['response_completed_at'])).total_seconds()

if __name__=='__main__':
 previous=None
 for endpoint,name,selector in [('teams/102','fd-team-102.json',team),('teams/454','fd-team-454.json',team),('matches/558579','fd-event.json',match)]:
  path=c.ROOT/'evidence'/(name+'.meta.json')
  if path.exists():
   previous=json.loads(path.read_text())
  else:
   if previous: pause(previous)
   previous=c.get('https://api.football-data.org/v4/'+endpoint,name,auth=('X-Auth-Token','FOOTBALL_DATA_TOKEN'),select=selector)
  if previous['state']!='retrieved': raise SystemExit('football_data_unavailable')
 pause(previous)
 client=Client(os.environ['FOOTBALL_DATA_TOKEN'],datetime.now(timezone.utc),c.ROOT/'snapshots')
 for code in ('SA','CL'):
  response=client.matches(code,2026)
  c.save('fd-'+code+'-snapshot-acquisition.json',{'source':response.get('url'),'request_started_at':response.get('requested_at_utc'),'known_received_by':c.now(),'state':response.get('state'),'http_status':response.get('http_status'),'quota':response.get('quota',{}),'cache_reused':client.calls==0})
  print(code,response.get('state'),response.get('http_status'),len(response.get('records',[])),flush=True)
  if response.get('state')!='retrieved': raise SystemExit('football_data_snapshot_unavailable')
