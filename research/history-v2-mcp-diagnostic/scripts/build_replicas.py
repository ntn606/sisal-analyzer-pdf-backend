"""Materialize two locally reviewed cases from authenticated official evidence."""
import sys,json,hashlib,shutil,subprocess,os,re
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
LIVE=ROOT/'live/evidence'
VERSION='history-identity-adapter.1'
def read(path):return json.loads(path.read_text())
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def ref(directory,name):return {'file':name,'sha256':hashlib.sha256((directory/name).read_bytes()).hexdigest()}
def now():return datetime.now(timezone.utc).isoformat()

def main():
 targets=read(LIVE/'selected-events.json')['targets'];text=(LIVE/'sisal-manifestazioni.txt').read_text()
 config={'PL':{'country':'GB','af_country':'England','area':'ENG','sisal_heading':'ENG Premier League','league':39,'fd_comp':2021,'slugs':['coventry','newcastle']},'PD':{'country':'ES','af_country':'Spain','area':'ESP','sisal_heading':'ESP Liga','league':140,'fd_comp':2014,'slugs':['levante','sevilla']}}
 for t in targets:
  cfg=config[t['competition']];pattern=re.compile(r'^\s*12/10\s+21\.00\s+'+t['palinsesto']+r'\s+'+t['avvenimento']+r'\s+',re.M)
  locations=list(pattern.finditer(text));assert len(locations)==1
  before=text[:locations[0].start()];headings=re.findall(r'^\s*((?:ENG|ESP|ITA|INT|GER|FRA|NED|POR|BEL)[ ]+[^\n]+)',before,re.M)
  assert headings and headings[-1].strip()==cfg['sisal_heading'],'sisal_competition_not_confirmed'
  t['actual_sisal_heading']=headings[-1].strip()
  folder=ROOT/'cases'/t['key'];evidence=folder/'evidence';evidence.mkdir(parents=True,exist_ok=True)
  raw_names=['sisal-base.pdf','sisal-page-excerpt.html','sisal-manifestazioni.pdf','sisal-manifestazioni.txt','af-fixture-'+t['key']+'.json','fd-event-'+t['key']+'.json']+['fd-team-'+str(mid)+'.json' for mid in t['fd_team_ids']]
  for name in raw_names:shutil.copyfile(LIVE/name,evidence/name)
  af=read(LIVE/('af-fixture-'+t['key']+'.json'))['response'];assert len(af)==1;af=af[0]
  fd=read(LIVE/('fd-event-'+t['key']+'.json'))
  kickoff=datetime.fromisoformat(t['kickoff_utc'])
  assert af['fixture']['status']['short']=='NS' and fd['status'] in ('TIMED','SCHEDULED')
  assert kickoff>datetime.now(timezone.utc)
  assert datetime.fromisoformat(af['fixture']['date'])==datetime.fromisoformat(fd['utcDate'].replace('Z','+00:00'))==kickoff
  assert af['league']['id']==cfg['league'] and af['league']['country']==cfg['af_country']
  assert fd['competition']['id']==cfg['fd_comp'] and fd['competition']['code']==t['competition']
  assert af['league']['season']==datetime.fromisoformat(fd['season']['startDate']).year==2026
  validity={'from':fd['season']['startDate']+'T00:00:00Z','until':'2026-10-13T00:00:00Z'}
  reviewed=now();verification={'state':'verified','reviewed_at':reviewed,'evidence_id':'review'}
  profile={'country':cfg['country'],'gender':'men','squad_kind':'first','age_group':'senior'}
  event={k:t[k] for k in ('palinsesto','avvenimento','home','away','date','time','timezone')}
  event.update(competition_canonical_id='local:competition:'+t['competition'],season_start_year=2026,utc_offset='+02:00',evidence_id='sisal')
  request={'schema_version':VERSION,'evidence_mode':'real_only','purpose':'diagnostic','verified_at':now(),'sisal_event':event,'api_football':{'state':'available','fixture_id':af['fixture']['id'],'competition_id':af['league']['id'],'season_start_year':af['league']['season'],'kickoff':af['fixture']['date'],'evidence_id':'af-fixture','history_evidence_ids':[]},'football_data':{'state':'available','match_id':fd['id']},'history_scope':{'home':[t['competition'],'CL'],'away':[t['competition'],'CL']}}
  reg={'schema_version':VERSION,'teams':[],'competitions':[],'bindings':[],'match_links':[],'availability':{},'evidence':{}}
  rationales=[]
  for side,slug in zip(('home','away'),cfg['slugs']):
   ft=fd[side+'Team'];team=read(LIVE/('fd-team-'+str(ft['id'])+'.json'))
   assert ft['id']==team['id'] and ft['name']==team['name'] and team['area']['code']==cfg['area']
   assert any(x['code']==t['competition'] and x['id']==cfg['fd_comp'] for x in team['runningCompetitions'])
   request['api_football'][side]={'team_id':af['teams'][side]['id'],'name':af['teams'][side]['name'],'profile':profile.copy()}
   aliases=[{'provider':provider,'label':label,'valid_from':fd['season']['startDate'],'valid_until':'2026-10-12'} for provider,label in [('sisal',t[side]),('api_football',af['teams'][side]['name']),('football_data',ft['name'])]]
   reg['teams'].append({'canonical_id':'local:team:'+slug,'provider_ids':{'api_football':af['teams'][side]['id'],'football_data':ft['id']},'profile':profile.copy(),'aliases':aliases,'validity':validity.copy(),'verification':verification.copy()})
   rationales.append({'side':side,'canonical_id':'local:team:'+slug,'name_only_matching':False,'checks':['official match same home/away position and opposing team','exact UTC kickoff after timezone conversion','same country, league and 2026 season','FD official team ID equals calendar ID and declares competition membership'],'profile_basis':'Contextual normalization from senior male first-team national league, not invented raw API profile fields','evidence_files':[ref(evidence,name) for name in raw_names if name.endswith(('.pdf','.json'))]})
  home_profile=read(LIVE/('fd-team-'+str(fd['homeTeam']['id'])+'.json'))
  assert af['fixture']['venue']['name']==home_profile['venue'],'independent_home_venue_mismatch'
  rationales.append({'independent_home_venue_match':af['fixture']['venue'],'fd_home_venue':home_profile['venue'],'cross_provider_venue_equal':True})
  reg['competitions']=[{'canonical_id':'local:competition:'+t['competition'],'api_football_id':af['league']['id'],'football_data_id':fd['competition']['id'],'football_data_code':t['competition'],'validity':validity.copy(),'verification':verification.copy()}]
  reg['bindings']=[{'palinsesto':t['palinsesto'],'avvenimento':t['avvenimento'],'api_football_fixture_id':af['fixture']['id'],'football_data_match_id':fd['id'],'home_canonical_id':reg['teams'][0]['canonical_id'],'away_canonical_id':reg['teams'][1]['canonical_id'],'competition_canonical_id':reg['competitions'][0]['canonical_id'],'validity':validity.copy(),'verification':verification.copy()}]
  entries=[{'entry_kind':kind,'value':{k:v for k,v in item.items() if k!='verification'}} for collection,kind in [('teams','team'),('competitions','competition'),('bindings','binding')] for item in reg[collection]]
  pdf=read(LIVE/'sisal-base.pdf.meta.json');page=read(LIVE/'sisal-page-excerpt.html.meta.json');afmeta=read(LIVE/('af-fixture-'+t['key']+'.json.meta.json'))
  proofs={'sisal':{'origin':'real_saved','kind':'sisal_event','source':pdf['source'],'acquired_at':pdf['response_completed_at'],'record':{k:v for k,v in event.items() if k!='evidence_id'},'document':{**ref(evidence,'sisal-base.pdf'),'media_type':'application/pdf','landing_page':{**ref(evidence,'sisal-page-excerpt.html'),'source':page['source'],'media_type':'text/html','acquired_at':page['response_completed_at']}}},'af-fixture':{'origin':'real_saved','kind':'api_football_fixture','source':afmeta['source'],'acquired_at':afmeta['response_completed_at'],'record':{k:v for k,v in request['api_football'].items() if k not in ('state','evidence_id','history_evidence_ids')}},'review':{'origin':'real_saved','kind':'review','source':'urn:local:review:'+t['key']+'-2026-10-12','acquired_at':reviewed,'record':{'reviewed_at':reviewed,'reviewer_ref':'local-research-review','entries':entries,'rationales':rationales,'sisal_heading':t['actual_sisal_heading'],'review_scope':'Single real event; local research review, not provider-issued cross-provider certification'}}}
  for key,proof in proofs.items():
   name='proof-'+key+'.json';write(evidence/name,proof);reg['evidence'][key]=ref(evidence,name)
  write(folder/'request-diagnostic.json',request);write(folder/'registry.json',reg);write(folder/'event.json',t)
  env=dict(os.environ,PYTHONPATH=str(ROOT/'vendor'),PYTHONDONTWRITEBYTECODE='1')
  run=subprocess.run([sys.executable,'-m','identity_adapter','--request',str(folder/'request-diagnostic.json'),'--registry',str(folder/'registry.json'),'--evidence',str(evidence),'--snapshots',str(ROOT/'live/snapshots')],env=env,capture_output=True,text=True,check=True)
  (folder/'real_only-preliminary.json').write_text(run.stdout)
  result=json.loads(run.stdout);print(t['key'],result['status'],[h['counts']['selected_results'] for h in result['histories'].values()],flush=True)
 write(LIVE/'selected-events.json',{'verified_context_at':now(),'targets':targets})
if __name__=='__main__':main()
