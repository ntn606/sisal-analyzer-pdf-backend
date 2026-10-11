"""Trusted local catalog -> unchanged identity/history engines -> safe diagnostics."""
from copy import deepcopy
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
import hashlib,json,re,threading
from identity_adapter import probe
from identity_adapter.core import sisal_kickoff
from history_provider_v2 import load_snapshots

VERSION='football-history-v2-probe.1'
class Failure(Exception):
 def __init__(self,status,code):self.status,self.code=status,code

def strict_object(pairs):
 obj={}
 for key,value in pairs:
  if key in obj:raise Failure('data_unverified','duplicate_json_key')
  obj[key]=value
 return obj

def utc(value):
 parsed=datetime.fromisoformat(value.replace('Z','+00:00')) if isinstance(value,str) else value
 if not isinstance(parsed,datetime) or parsed.tzinfo is None:raise Failure('temporal_unverified','timezone_required')
 return parsed.astimezone(timezone.utc)

class ProbeService:
 """The root/catalog/clock are operator configuration, never MCP arguments.

 Cache compiled datasets by verified content hashes, never by client IDs alone.
 Re-run identities, freshness, temporal checks and the kickoff guard on every call.
 No cached response can cross the kickoff boundary.
 """
 def __init__(self,root,clock=None):
  self.root=Path(root).resolve();self.clock=clock or (lambda:datetime.now(timezone.utc))
  self.lock=threading.RLock();self._dataset_key=None;self._dataset=None
 def _path(self,relative):
  if not isinstance(relative,str) or Path(relative).is_absolute():raise Failure('identity_unverified','invalid_local_reference')
  path=(self.root/relative).resolve()
  if not path.is_relative_to(self.root) or path==self.root:raise Failure('identity_unverified','local_reference_outside_root')
  return path
 def _bytes(self,relative):
  path=self._path(relative)
  try:
   if path.stat().st_size>5_000_000:raise Failure('data_unverified','local_document_too_large')
   return path.read_bytes()
  except OSError:raise Failure('provider_unavailable','local_evidence_unavailable') from None
 def _json(self,relative):
  try:return json.loads(self._bytes(relative),object_pairs_hook=strict_object)
  except (ValueError,UnicodeError):raise Failure('data_unverified','invalid_local_json') from None
 def _base(self,palinsesto,avvenimento,match_date,now):
  return {'schema_version':VERSION,'diagnostic_only':True,'ready_for_analysis':False,'ready_for_quant':False,'statistics_usable_in_production':False,'status':'identity_unverified','diagnostic_statistics_allowed':False,'execution_mode':'cached_real_evidence','verified_at_utc':now.isoformat(),'requested_event':{'palinsesto':palinsesto,'avvenimento':avvenimento,'match_date':match_date},'checks':{'event':{'verified':False,'reasons':[]},'teams':{side:{'identity_verified':False,'state':'identity_unverified','reasons':[]} for side in ('home','away')}},'histories':{},'temporal':{'backtest_availability_verified':False,'first_publication_time_verified':False},'blockers':[],'provenance':{'new_api_requests':0,'cache':'approved_local_snapshots','dataset_reused':False,'all_competitions_complete':False,'evidence':[],'cross_provider_duplicate_matches':0}}
 def football_history_v2_probe(self,palinsesto:str,avvenimento:str,match_date:str):
  # Invalid inputs are not echoed, including possible credential-like strings.
  with self.lock:
   now=utc(self.clock());output=self._base(None,None,None,now)
   try:
    if not all(type(x) is str and re.fullmatch(r'[0-9]{1,20}',x) for x in (palinsesto,avvenimento)) or type(match_date) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',match_date):raise Failure('identity_unverified','invalid_event_reference')
    try:
     if date.fromisoformat(match_date).isoformat()!=match_date:raise ValueError
    except ValueError:raise Failure('identity_unverified','invalid_event_date') from None
    output['requested_event']={'palinsesto':palinsesto,'avvenimento':avvenimento,'match_date':match_date}
    catalog=self._json('catalog.json')
    if not isinstance(catalog,dict) or catalog.get('schema_version')!=VERSION:raise Failure('identity_unverified','invalid_catalog_contract')
    entries=[entry for entry in catalog.get('events',[]) if entry.get('event_key')==[palinsesto,avvenimento,match_date]]
    if len(entries)!=1:raise Failure('identity_unverified','event_binding_missing_or_ambiguous')
    entry=entries[0];anchors=entry.get('files',{})
    if not isinstance(anchors,dict) or not anchors:raise Failure('identity_unverified','missing_catalog_integrity')
    for relative,expected in anchors.items():
     if not isinstance(expected,str) or not re.fullmatch(r'[0-9a-f]{64}',expected):raise Failure('identity_unverified','invalid_catalog_digest')
     if hashlib.sha256(self._bytes(relative)).hexdigest()!=expected:raise Failure('data_conflict','catalog_file_integrity_failed')
     if relative.endswith('.json'):self._json(relative)
    request_path=entry['request_file'];registry_path=entry['registry_file']
    if request_path not in anchors or registry_path not in anchors:raise Failure('identity_unverified','unanchored_mapping')
    request=deepcopy(self._json(request_path));registry=self._json(registry_path)
    event=request['sisal_event']
    if [event.get('palinsesto'),event.get('avvenimento'),event.get('date')]!=[palinsesto,avvenimento,match_date]:raise Failure('identity_unverified','catalog_event_mismatch')
    kickoff=sisal_kickoff(event)
    if now>=kickoff:raise Failure('temporal_unverified','event_already_started')
    evidence_relative=entry['evidence_dir'];evidence_root=self._path(evidence_relative)
    for reference in registry.get('evidence',{}).values():
     relative=str(Path(evidence_relative)/reference['file'])
     if relative not in anchors:raise Failure('identity_unverified','unanchored_evidence')
     proof=self._json(relative)
     if proof.get('origin')!='real_saved':raise Failure('identity_unverified','synthetic_evidence_not_accepted')
     acquired=utc(proof['acquired_at'])
     if acquired>now:raise Failure('temporal_unverified','evidence_after_verification')
     if proof.get('kind') in ('sisal_event','api_football_fixture') and now-acquired>timedelta(hours=1):raise Failure('source_stale','event_evidence_older_than_one_hour')
     if proof.get('kind')=='sisal_event':
      document=proof.get('document',{});page=document.get('landing_page',{})
      for attached in (document,page):
       if str(Path(evidence_relative)/attached.get('file','')) not in anchors:raise Failure('identity_unverified','unanchored_sisal_document')
    snapshots_relative=entry['snapshots_dir'];snapshots=self._path(snapshots_relative)
    actual={str(path.relative_to(self.root)) for path in snapshots.glob('*.json')}
    if not actual or not actual.issubset(anchors):raise Failure('provider_unavailable','unanchored_or_missing_snapshots')
    key=tuple(sorted((relative,anchors[relative]) for relative in actual))
    reused=self._dataset_key==key
    if not reused:self._dataset=load_snapshots(snapshots);self._dataset_key=key
    # Internally use the existing availability-checking branch at current time.
    # It proves observed-by-now, never first publication or arbitrary past dates.
    request.update(evidence_mode='real_only',purpose='historical_backtest',analysis_at=now.isoformat(),verified_at=now.isoformat())
    result=probe(request,registry,self._dataset,evidence_root)
    for field in ('status','diagnostic_statistics_allowed','checks','histories','temporal','blockers'):
     output[field]=result[field]
    if any(h.get('diagnostics',{}).get('conflicts') for h in output['histories'].values()):
     output.update(status='data_conflict',diagnostic_statistics_allowed=False)
     output['blockers']=list(output['blockers'])+['conflicting_history_records']
     for history in output['histories'].values():history['statistics']=None
    if 'event_ids' in result:output['event_ids']=result['event_ids']
    output['verification_scope']=result['verification_scope']
    output['temporal']['purpose']='diagnostic'
    output['temporal']['availability_criterion']='actually_observed_by_current_verification'
    output['provenance'].update(dataset_reused=reused,evidence=result['evidence'],cross_provider_duplicate_matches=result['cross_provider_duplicate_matches'])
    return output
   except Failure as error:
    output.update(status=error.status,blockers=[error.code]);return output
   except (OSError,ValueError,KeyError,TypeError,AttributeError):
    output.update(status='data_unverified',blockers=['local_contract_or_data_invalid']);return output
