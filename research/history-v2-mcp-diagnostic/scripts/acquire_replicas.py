"""Bounded official live acquisition, separate from the MCP wrapper.

Reuses the existing collectors and snapshot client; no production imports.
No automatic retries and no unverified identity certificates.
"""
import sys,os,json,time,shutil,subprocess,re
from pathlib import Path
from datetime import datetime,timezone
from html.parser import HTMLParser
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/reused'))
import collect_evidence as c
from collect_fd import pause,team
from collect_observations import match
sys.path.insert(0,str(ROOT/'scripts/reused'))
from probe_free import Client
from minimize_sisal_page import get_page_excerpt
c.ROOT=ROOT/'live'
TARGETS=[{'key':'coventry-newcastle','palinsesto':'36411','avvenimento':'1885','home':'Coventry','away':'Newcastle','competition':'PL','sisal_competition':'ING Premier League','fixture_id':1557420,'fd_match_id':560597,'fd_team_ids':[1076,67]}, {'key':'levante-sevilla','palinsesto':'36411','avvenimento':'2282','home':'Levante','away':'Siviglia','competition':'PD','sisal_competition':'SPA Primera Division','fixture_id':1570407,'fd_match_id':564704,'fd_team_ids':[88,559]}]

def stored_get(url,name,**kwargs):
 meta=c.ROOT/'evidence'/(name+'.meta.json')
 if meta.exists():return json.loads(meta.read_text())
 return c.get(url,name,**kwargs)

def require(meta):
 if meta['state']!='retrieved':raise SystemExit('live_acquisition_blocked_'+meta['state'])
 return meta

class Links(HTMLParser):
 def __init__(self):super().__init__();self.links=[]
 def handle_starttag(self,tag,attrs):
  if tag=='a':self.links.extend(v for k,v in attrs if k=='href' and v)

if __name__=='__main__':
 c.save('credentials-presence.json',{'checked_at':c.now(),'credentials':{name:bool(os.environ.get(name,'').strip()) for name in ('API_FOOTBALL_KEY','FOOTBALL_DATA_TOKEN')}})
 if not all(os.environ.get(name,'').strip() for name in ('API_FOOTBALL_KEY','FOOTBALL_DATA_TOKEN')):raise SystemExit('credential_missing')
 require(stored_get('https://v3.football.api-sports.io/status','af-status.json',auth=('x-apisports-key','API_FOOTBALL_KEY'),select=c.status_select))
 require(get_page_excerpt(c.ROOT/'evidence'))
 links=Links();links.feed((c.ROOT/'evidence/sisal-page-excerpt.html').read_text())
 for name,path in [('sisal-base','calcio%20base%20per%20data.pdf'),('sisal-manifestazioni','calcio%20base%20per%20manifestazione.pdf')]:
  url='https://landing.sisal.it/volantini/Scommesse_Sport/Quote/'+path
  if url not in links.links:raise SystemExit('official_pdf_link_not_found')
  meta=require(stored_get(url,name+'.pdf',binary=True))
  pdf=c.ROOT/'evidence'/(name+'.pdf')
  if meta['content_type']!='application/pdf' or not pdf.read_bytes().startswith(b'%PDF-'):raise SystemExit('invalid_official_pdf')
  subprocess.run(['pdftotext','-layout',str(pdf),str(pdf.with_suffix('.txt'))],check=True)
 text=(c.ROOT/'evidence/sisal-manifestazioni.txt').read_text()
 for target in TARGETS:
  pattern=re.compile(r'^\s*12/10\s+21\.00\s+'+target['palinsesto']+r'\s+'+target['avvenimento']+r'\s+'+re.escape(target['home'])+r'\s{2,}'+re.escape(target['away'])+r'\s{2,}',re.M)
  matches=list(pattern.finditer(text))
  if len(matches)!=1:raise SystemExit('sisal_candidate_missing_or_ambiguous')
  before=text[:matches[0].start()]
  headings=re.findall(r'^\s*(?:ING|SPA)\s+([^\n]+)',before,re.M)
  target['actual_sisal_heading']=headings[-1].strip() if headings else None
  target['manifest_pdf_page']=before.count('\f')+1
  target.update(date='2026-10-12',time='21:00:00',timezone='Europe/Rome',kickoff_utc='2026-10-12T19:00:00+00:00')
  if datetime.fromisoformat(target['kickoff_utc'])<=datetime.now(timezone.utc):raise SystemExit('event_already_started')
  name='af-fixture-'+target['key']+'.json'
  if not (c.ROOT/'evidence'/(name+'.meta.json')).exists():c.af_budget_check()
  require(stored_get('https://v3.football.api-sports.io/fixtures?id='+str(target['fixture_id']),name,auth=('x-apisports-key','API_FOOTBALL_KEY'),select=c.fixtures_select))
 c.save('selected-events.json',{'acquired_at':c.now(),'targets':TARGETS})
 previous=None
 for target in TARGETS:
  endpoints=[('teams/'+str(mid),'fd-team-'+str(mid)+'.json',team) for mid in target['fd_team_ids']]
  endpoints.append(('matches/'+str(target['fd_match_id']),'fd-event-'+target['key']+'.json',match))
  for endpoint,name,selector in endpoints:
   meta=c.ROOT/'evidence'/(name+'.meta.json')
   if not meta.exists() and previous:pause(previous)
   previous=require(stored_get('https://api.football-data.org/v4/'+endpoint,name,auth=('X-Auth-Token','FOOTBALL_DATA_TOKEN'),select=selector))
 pause(previous)
 client=Client(os.environ['FOOTBALL_DATA_TOKEN'],datetime.now(timezone.utc),c.ROOT/'snapshots')
 for code in ('PL','PD'):
  response=client.matches(code,2026)
  c.save('fd-'+code+'-snapshot-acquisition.json',{'source':response.get('url'),'request_started_at':response.get('requested_at_utc'),'known_received_by':c.now(),'state':response.get('state'),'http_status':response.get('http_status'),'quota':response.get('quota',{})})
  print(code,response.get('state'),len(response.get('records',[])),flush=True)
  if response.get('state')!='retrieved':raise SystemExit('football_data_snapshot_unavailable')
 old=Path('/workspace/research/history-v2-real-e2e-2026-10-11')
 cached=c.ROOT/'snapshots/CL-2026.json'
 original=cached if cached.exists() else old/'snapshots/CL-2026.json'
 snap=json.loads(original.read_text())
 if (datetime.now(timezone.utc)-datetime.fromisoformat(snap['requested_at_utc'])).total_seconds()>86400:raise SystemExit('cached_cl_stale')
 if original!=cached:shutil.copyfile(original,cached)
 c.save('cl-cache-reuse.json',{'original_file':str(old/'snapshots/CL-2026.json'),'source':snap['url'],'original_request_started_at':snap['requested_at_utc'],'reused_at':c.now(),'new_api_calls':0})
 print('replica_acquisition_complete',flush=True)
