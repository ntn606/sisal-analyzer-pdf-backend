"""Observe selected finished scores, once per official match ID, <=10 GETs.

Needed because the existing adapter accepts availability evidence only from
/v4/matches/{id}. Response completion proves 'known by', never first publication.
No repeat failed calls and no changes to the isolated adapter.
"""
import json
from pathlib import Path
from datetime import datetime,timezone
import collect_evidence as c
from collect_fd import pause

def match(body):
 clean={k:body.get(k) for k in ('id','utcDate','status','score','stage','matchday','lastUpdated')}
 for key,fields in [('competition',('id','name','code','type')),('season',('id','startDate','endDate')),('homeTeam',('id','name')),('awayTeam',('id','name'))]:
  clean[key]={field:body.get(key,{}).get(field) for field in fields}
 return clean

if __name__=='__main__':
 output=json.loads((c.ROOT/'reports/real_only-preliminary.json').read_text())
 assert output['status']=='diagnostic_available'
 selected={m['match_id']:m for h in output['histories'].values() for m in h['matches']}
 assert len(selected)<=10 and all(h['counts']['selected_results']==5 for h in output['histories'].values())
 metas=list((c.ROOT/'evidence').glob('fd-*.json.meta.json'))
 previous=json.loads(max(metas,key=lambda p:p.stat().st_mtime).read_text())
 registry=json.loads((c.ROOT/'registry.json').read_text())
 for mid,saved in selected.items():
  name=f'fd-result-{mid}.json';metadata=c.ROOT/'evidence'/(name+'.meta.json')
  if metadata.exists():
   previous=json.loads(metadata.read_text())
  else:
   pause(previous)
   previous=c.get(f'https://api.football-data.org/v4/matches/{mid}',name,auth=('X-Auth-Token','FOOTBALL_DATA_TOKEN'),select=match)
  if previous['state']!='retrieved': raise SystemExit('result_observation_unavailable')
  raw=json.loads((c.ROOT/'evidence'/name).read_text())
  period='fullTime' if raw['score']['duration']=='REGULAR' else 'regularTime'
  assert (raw['id']==mid and raw['status']=='FINISHED' and raw['homeTeam']['id']==saved['home']['provider_id'] and raw['awayTeam']['id']==saved['away']['provider_id'] and raw['score'].get(period)==saved['score_90_minutes'] and datetime.fromisoformat(raw['utcDate'].replace('Z','+00:00'))==datetime.fromisoformat(saved['utc_date']) and raw['competition']['id']==saved['competition']['id'] and raw['season']['id']==saved['season']['id']), 'observed_record_conflict'
  record={'football_data_match_id':mid,'status':raw['status'],'home_team_id':raw['homeTeam']['id'],'away_team_id':raw['awayTeam']['id'],'score_90_minutes':raw['score'][period],'observed_at':previous['response_completed_at']}
  proof={'origin':'real_saved','kind':'result_observation','source':previous['source'],'acquired_at':previous['response_completed_at'],'record':record}
  proofname=f'proof-observation-{mid}.json';c.save(proofname,proof)
  import hashlib
  registry['evidence'][f'observation-{mid}']={'file':proofname,'sha256':hashlib.sha256((c.ROOT/'evidence'/proofname).read_bytes()).hexdigest()}
  registry['availability'][str(mid)]=f'observation-{mid}'
 (c.ROOT/'registry.json').write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n')
 request=json.loads((c.ROOT/'request-diagnostic.json').read_text())
 analysis=c.now();request['verified_at']=c.now()
 (c.ROOT/'request-diagnostic.json').write_text(json.dumps(request,ensure_ascii=False,indent=2)+'\n')
 request.update(purpose='historical_backtest',analysis_at=analysis)
 (c.ROOT/'request-asof-observation.json').write_text(json.dumps(request,ensure_ascii=False,indent=2)+'\n')
 request['analysis_at']='2026-09-21T12:00:00Z'
 (c.ROOT/'request-historical-unverified.json').write_text(json.dumps(request,ensure_ascii=False,indent=2)+'\n')
 print('observed_unique_matches',len(selected),'availability_asof',analysis)
