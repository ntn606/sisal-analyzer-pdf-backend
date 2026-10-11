"""Observe selected real scores once, respecting Free headers (<=20 GETs)."""
import sys,json,hashlib,shutil,subprocess,os
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/reused'))
import collect_evidence as c
from collect_fd import pause
from collect_observations import match
c.ROOT=ROOT/'live'
def read(path):return json.loads(path.read_text())
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':
 cases=sorted((ROOT/'cases').iterdir());selected={}
 for folder in cases:
  output=read(folder/'real_only-preliminary.json')
  if output['status']!='diagnostic_available':continue
  for history in output['histories'].values():
   for row in history['matches']:
    if row['match_id'] in selected and selected[row['match_id']]['score_90_minutes']!=row['score_90_minutes']:raise SystemExit('conflicting_selected_match')
    selected[row['match_id']]=row
 if len(selected)>20:raise SystemExit('local_observation_budget')
 metas=list((c.ROOT/'evidence').glob('fd-*.json.meta.json'));previous=read(max(metas,key=lambda p:p.stat().st_mtime))
 for mid,saved in selected.items():
  name=f'fd-result-{mid}.json';metadata=c.ROOT/'evidence'/(name+'.meta.json')
  if metadata.exists():previous=read(metadata)
  else:
   pause(previous)
   previous=c.get(f'https://api.football-data.org/v4/matches/{mid}',name,auth=('X-Auth-Token','FOOTBALL_DATA_TOKEN'),select=match)
  if previous['state']!='retrieved':raise SystemExit('result_observation_unavailable')
  raw=read(c.ROOT/'evidence'/name);period='fullTime' if raw['score']['duration']=='REGULAR' else 'regularTime'
  if not (raw['id']==mid and raw['status']=='FINISHED' and raw['homeTeam']['id']==saved['home']['provider_id'] and raw['awayTeam']['id']==saved['away']['provider_id'] and raw['score'].get(period)==saved['score_90_minutes'] and datetime.fromisoformat(raw['utcDate'].replace('Z','+00:00'))==datetime.fromisoformat(saved['utc_date']) and raw['season']['id']==saved['season']['id'] and raw['competition']['id']==saved['competition']['id']):raise SystemExit('observed_record_conflict')
 for folder in cases:
  original=read(folder/'real_only-preliminary.json');registry=read(folder/'registry.json')
  for history in original['histories'].values():
   for saved in history['matches']:
    mid=saved['match_id'];name=f'fd-result-{mid}.json';meta=read(c.ROOT/'evidence'/(name+'.meta.json'));raw=read(c.ROOT/'evidence'/name)
    shutil.copyfile(c.ROOT/'evidence'/name,folder/'evidence'/name)
    record={'football_data_match_id':mid,'status':'FINISHED','home_team_id':raw['homeTeam']['id'],'away_team_id':raw['awayTeam']['id'],'score_90_minutes':saved['score_90_minutes'],'observed_at':meta['response_completed_at']}
    proof={'origin':'real_saved','kind':'result_observation','source':meta['source'],'acquired_at':meta['response_completed_at'],'record':record}
    pname=f'proof-observation-{mid}.json';write(folder/'evidence'/pname,proof)
    registry['evidence'][f'observation-{mid}']={'file':pname,'sha256':hashlib.sha256((folder/'evidence'/pname).read_bytes()).hexdigest()}
    registry['availability'][str(mid)]=f'observation-{mid}'
  write(folder/'registry.json',registry)
  request=read(folder/'request-diagnostic.json');analysis=c.now();request['verified_at']=c.now()
  write(folder/'request-diagnostic.json',request)
  request.update(purpose='historical_backtest',analysis_at=analysis)
  write(folder/'request-asof-observation.json',request)
  env=dict(os.environ,PYTHONPATH=str(ROOT/'vendor'),PYTHONDONTWRITEBYTECODE='1')
  run=subprocess.run([sys.executable,'-m','identity_adapter','--request',str(folder/'request-asof-observation.json'),'--registry',str(folder/'registry.json'),'--evidence',str(folder/'evidence'),'--snapshots',str(ROOT/'live/snapshots')],env=env,capture_output=True,text=True,check=True)
  (folder/'real_only.json').write_text(run.stdout)
  result=json.loads(run.stdout);print(folder.name,result['status'],result['temporal']['state'],[h['counts']['selected_results'] for h in result['histories'].values()],flush=True)
 print('new_unique_observations',len(selected),flush=True)
