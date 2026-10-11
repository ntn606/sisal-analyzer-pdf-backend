"""Simulation builder only: never represents AF/Sisal IDs as observed real IDs."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from identity_adapter.core import VERSION
from history_provider_v2 import Dataset,Snapshot,load_snapshots
from history_provider_v2.provider import COMPETITIONS

NOW='2026-10-10T18:05:00Z'
VALIDITY={'from':'2025-01-01T00:00:00Z','until':'2028-01-01T00:00:00Z'}


def write_evidence(root,registry,key,kind,record):
    payload={'origin':'synthetic','kind':kind,'source':f'urn:synthetic:{kind.replace("_","-")}:{key}',
             'acquired_at':'2026-10-10T18:00:00Z','record':deepcopy(record)}
    path=Path(root)/f'{key}.json';path.write_text(json.dumps(payload,indent=2)+'\n')
    registry['evidence'][key]={'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def refresh_review(root,registry):
    entries=[]
    for collection,kind in [('teams','team'),('competitions','competition'),('bindings','binding'),('match_links','match')]:
        for value in registry[collection]:
            value['verification']={'state':'verified','reviewed_at':'2026-10-10T18:00:00Z','evidence_id':'review'}
            entries.append({'entry_kind':kind,'value':{k:deepcopy(v) for k,v in value.items() if k!='verification'}})
    write_evidence(root,registry,'review','review',{'reviewed_at':'2026-10-10T18:00:00Z',
        'reviewer_ref':'synthetic-test-author','entries':entries})


def team_entry(fd_id,name,country='GB'):
    return {'canonical_id':f'local:team:t{fd_id}',
            'provider_ids':{'api_football':900000+fd_id,'football_data':fd_id},
            'profile':{'country':country,'gender':'men','squad_kind':'first','age_group':'senior'},
            'aliases':[{'provider':p,'label':name,'valid_from':'2025-01-01','valid_until':'2027-12-31'} for p in ('sisal','api_football')],
            'validity':deepcopy(VALIDITY)}


def synthetic_row(match_id,when,home=57,away=351,score=(2,1)):
    return {'match_id':match_id,'utc_date':when,'status':'FINISHED','competition_code':'PL',
        'competition_id':2021,'season_id':2502,'season_start':'2026-08-21','season_end':'2027-05-30','requested_season':2026,
        'stage':'REGULAR_SEASON','home':{'id':home,'name':f'Test club {home}'},'away':{'id':away,'name':f'Test club {away}'},
        'duration':'REGULAR','score':{'fullTime':{'home':score[0],'away':score[1]}},'provider':'football-data.org'}


def synthetic_dataset():
    rows=[synthetic_row(i,f'2026-10-0{i}T12:00:00Z') for i in range(1,6)]
    future={'match_id':900,'utc_date':'2026-10-18T15:30:00Z','status':'TIMED',
            'home':{'id':57,'name':'Test club 57'},'away':{'id':351,'name':'Test club 351'}}
    return Dataset((Snapshot('PL',2026,datetime(2026,10,10,17,tzinfo=timezone.utc),tuple(rows),(future,),snapshot_id='synthetic-PL.json'),))


def scenario(root,case='arsenal',synthetic=False):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    dataset=synthetic_dataset() if synthetic else load_snapshots(ROOT/'fixtures/real')
    code,event_id,focus={'arsenal':('PL',560608,57),'psg':('FL1',559672,524),'roma':('CL',575352,100),'leipzig':('BL1',565815,721)}[case]
    if synthetic:code,event_id='PL',900
    snap=next(s for s in dataset.snapshots if s.competition==code and s.season==2026)
    event=next(r for r in snap.nonfinal_records if r['match_id']==event_id)
    countries={'arsenal':['GB','GB'],'psg':['FR','FR'],'roma':['IT','ES'],'leipzig':['DE','DE']}[case]
    teams=[team_entry(event[s]['id'],event[s]['name'],countries[i]) for i,s in enumerate(('home','away'))]
    af={'fixture_id':800000001,'competition_id':700000001,'season_start_year':2026,'kickoff':event['utc_date'],
        **{s:{'team_id':teams[i]['provider_ids']['api_football'],'name':event[s]['name'],'profile':deepcopy(teams[i]['profile'])} for i,s in enumerate(('home','away'))}}
    local=datetime.fromisoformat(event['utc_date'].replace('Z','+00:00')).astimezone(__import__('zoneinfo').ZoneInfo('Europe/Rome'))
    sisal={'palinsesto':'999001','avvenimento':'999002','home':event['home']['name'],'away':event['away']['name'],
           'competition_canonical_id':f'local:competition:{code}','season_start_year':2026,
           'date':local.date().isoformat(),'time':local.strftime('%H:%M:%S'),'timezone':'Europe/Rome'}
    comp={'canonical_id':sisal['competition_canonical_id'],'api_football_id':af['competition_id'],
          'football_data_id':COMPETITIONS[code],'football_data_code':code,'validity':deepcopy(VALIDITY)}
    binding={'palinsesto':sisal['palinsesto'],'avvenimento':sisal['avvenimento'],
             'api_football_fixture_id':af['fixture_id'],'football_data_match_id':event_id,
             'home_canonical_id':teams[0]['canonical_id'],'away_canonical_id':teams[1]['canonical_id'],
             'competition_canonical_id':comp['canonical_id'],'validity':deepcopy(VALIDITY)}
    registry={'schema_version':VERSION,'teams':teams,'competitions':[comp],'bindings':[binding],
              'match_links':[],'availability':{},'evidence':{}}
    write_evidence(root,registry,'sisal','sisal_event',sisal)
    write_evidence(root,registry,'af-fixture','api_football_fixture',af)
    refresh_review(root,registry)
    scope=[code,'CL'] if not synthetic and code in ('PL','FL1') else [code]
    request={'schema_version':VERSION,'evidence_mode':'simulation','purpose':'diagnostic','verified_at':NOW,
             'sisal_event':{**sisal,'evidence_id':'sisal'},
             'api_football':{**af,'state':'available','evidence_id':'af-fixture','history_evidence_ids':[]},
             'football_data':{'state':'available','match_id':event_id},'history_scope':{'home':scope,'away':scope}}
    return request,registry,dataset
