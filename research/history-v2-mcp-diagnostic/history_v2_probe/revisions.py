"""Content-addressed, operator-reviewed revisions. No network; no client paths.

Activation publishes a fsynced ACTIVE.json with one os.replace. Readers capture
one fully verified private copy; in-flight requests hold that copy until done.
The digest protects integrity, not author identity: store writers are trusted.
"""
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
import argparse, fcntl, hashlib, json, os, re, tempfile, threading
from .service import ProbeService, Failure, VERSION, strict_object
from .publication_safety import findings,validate_pdf_excerpt

REVISION_VERSION='football-history-v2-revision.1'
MAX_FILE=5_000_000
MAX_TOTAL=64_000_000
MAX_FILES=2048

def encode(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()

def digest(raw):return hashlib.sha256(raw).hexdigest()

def obj(raw):
    try:return json.loads(raw,object_pairs_hook=strict_object)
    except (ValueError,UnicodeError):raise Failure('data_unverified','invalid_revision_json') from None

def safe_name(name):
    if not isinstance(name,str) or not name or '\\' in name or any(c in name for c in ('\x00',':')):
        raise Failure('data_unverified','invalid_revision_path')
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or str(p)!=name:
        raise Failure('data_unverified','invalid_revision_path')
    return name

def read(root,name):
    name=safe_name(name);path=root/name
    # Reject every symlink, including parent directories, before a bounded read.
    if root.is_symlink() or any(p.is_symlink() for p in [path,*path.parents] if p==root or p.is_relative_to(root)):
        raise Failure('data_unverified','revision_symlink_not_allowed')
    try:
        with path.open('rb') as file:raw=file.read(MAX_FILE+1)
    except OSError:raise Failure('provider_unavailable','revision_file_missing') from None
    if len(raw)>MAX_FILE:raise Failure('data_unverified','revision_file_too_large')
    return raw

def inspect_files(files):
    for name,raw in files.items():
        if findings(raw):raise Failure('data_unverified','unsafe_publication_content')
        if name.endswith('.html'):
            try:validate_pdf_excerpt(raw)
            except ValueError:raise Failure('data_unverified','unsafe_html_excerpt') from None
    catalog=obj(files['catalog.json'])
    if catalog.get('schema_version')!=VERSION or not isinstance(catalog.get('events'),list) or not catalog['events']:
        raise Failure('identity_unverified','invalid_revision_catalog')
    seen=set()
    for entry in catalog['events']:
        key=tuple(entry['event_key'])
        if len(key)!=3 or key in seen:raise Failure('identity_unverified','ambiguous_revision_binding')
        seen.add(key)
        anchors=entry['files']
        if not anchors:raise Failure('identity_unverified','missing_revision_anchors')
        for name,expected in anchors.items():
            if name not in files:raise Failure('provider_unavailable','revision_file_missing')
            if digest(files[name])!=expected:raise Failure('data_conflict','revision_hash_mismatch')
        if any(entry[field] not in anchors for field in ('request_file','registry_file')):
            raise Failure('identity_unverified','unanchored_revision_mapping')
        registry=obj(files[entry['registry_file']]);reviews=0
        for ref in registry['evidence'].values():
            name=str(PurePosixPath(entry['evidence_dir'])/safe_name(ref['file']))
            if name not in anchors:raise Failure('identity_unverified','unanchored_revision_evidence')
            proof=obj(files[name])
            if proof.get('origin')!='real_saved':raise Failure('identity_unverified','synthetic_evidence_not_accepted')
            if proof.get('kind')=='review':
                if not proof.get('record',{}).get('entries'):raise Failure('identity_unverified','unreviewed_revision')
                reviews+=1
        if not reviews:raise Failure('identity_unverified','unreviewed_revision')
        prefix=entry['snapshots_dir']+'/'
        if not any(n.startswith(prefix) and n.endswith('.json') for n in anchors):
            raise Failure('provider_unavailable','revision_snapshots_missing')
    return catalog

@dataclass(frozen=True)
class Revision:
    revision_id:str
    manifest:dict
    service:ProbeService
    private_copy:tempfile.TemporaryDirectory

class RevisionStore:
    def __init__(self,root,clock=None):
        self.root=Path(root);self.clock=clock;self._lock=threading.RLock();self._current=None
    def capture(self):
        """Atomic pointer read + verification; returned object pins one revision."""
        with self._lock:
            pointer=obj(read(self.root,'ACTIVE.json'))
            revision_id=pointer.get('revision_id')
            if set(pointer)!={'schema_version','revision_id'} or pointer['schema_version']!=REVISION_VERSION or not isinstance(revision_id,str) or not re.fullmatch('[0-9a-f]{64}',revision_id):
                raise Failure('data_unverified','invalid_active_revision')
            if self._current is not None and self._current.revision_id==revision_id:return self._current
            revision=self.load(revision_id)
            self._current=revision
            return revision
    def load(self,revision_id):
        if not re.fullmatch('[0-9a-f]{64}',revision_id):raise Failure('data_unverified','invalid_revision_id')
        root=self.root/'revisions'/revision_id
        manifest_raw=read(root,'REVISION.json')
        if digest(manifest_raw)!=revision_id:raise Failure('data_conflict','revision_manifest_hash_mismatch')
        manifest=obj(manifest_raw)
        if set(manifest)!={'schema_version','review_basis','files'} or manifest['schema_version']!=REVISION_VERSION or manifest['review_basis']!='existing_local_operator_real_evidence_review':
            raise Failure('identity_unverified','unreviewed_revision')
        entries=manifest['files']
        if not isinstance(entries,dict) or not 1<=len(entries)<=MAX_FILES:raise Failure('data_unverified','revision_size_limit')
        files={};total=0
        for name,expected in entries.items():
            if not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected):raise Failure('data_unverified','invalid_revision_digest')
            raw=read(root,name);total+=len(raw)
            if total>MAX_TOTAL:raise Failure('data_unverified','revision_size_limit')
            if digest(raw)!=expected:raise Failure('data_conflict','revision_hash_mismatch')
            files[name]=raw
        try:inspect_files(files)
        except Failure:raise
        except (KeyError,TypeError,ValueError):raise Failure('data_unverified','invalid_revision_contract') from None
        # Engine reads its own private materialization, never the active store.
        # This closes read/hash/read and activation TOCTOU windows for all engines.
        private=tempfile.TemporaryDirectory(prefix='history-v2-pinned-')
        for name,raw in files.items():
            path=Path(private.name)/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);path.chmod(0o400)
        service=ProbeService(private.name,clock=self.clock)
        return Revision(revision_id,MappingProxyType(manifest),service,private)

class RevisionProbe:
    def __init__(self,store):self.store=store
    def football_history_v2_probe(self,palinsesto,avvenimento,match_date):
        revision=None
        try:
            revision=self.store.capture()
            result=revision.service.football_history_v2_probe(palinsesto,avvenimento,match_date)
            result['provenance']['catalog_revision']=revision.revision_id
            return result
        except Exception as error:
            # Unexpected exception text is never returned/logged. Fail closed.
            from datetime import datetime,timezone
            base=ProbeService('.')._base(None,None,None,datetime.now(timezone.utc))
            base.update(status=error.status if isinstance(error,Failure) else 'data_unverified',blockers=[error.code if isinstance(error,Failure) else 'revision_unavailable'])
            return base

def publish(source,store):
    """Local operator command only; no runtime RPC or network acquisition."""
    source=Path(source);store=Path(store);store.mkdir(parents=True,exist_ok=True)
    with (store/'.publish.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        catalog_raw=read(source,'catalog.json');catalog=obj(catalog_raw)
        names={'catalog.json'}
        for entry in catalog['events']:names.update(entry['files'])
        if len(names)>MAX_FILES:raise Failure('data_unverified','revision_size_limit')
        files={name:read(source,name) for name in sorted(names)}
        if sum(map(len,files.values()))>MAX_TOTAL:raise Failure('data_unverified','revision_size_limit')
        inspect_files(files)
        manifest={'schema_version':REVISION_VERSION,'review_basis':'existing_local_operator_real_evidence_review','files':{n:digest(r) for n,r in files.items()}}
        raw=encode(manifest);revision_id=digest(raw)
        revisions=store/'revisions';revisions.mkdir(exist_ok=True)
        destination=revisions/revision_id
        if not destination.exists():
            with tempfile.TemporaryDirectory(dir=revisions,prefix='.staging-') as tmp:
                stage=Path(tmp)/'revision';stage.mkdir()
                for name,data in {**files,'REVISION.json':raw}.items():
                    path=stage/name;path.parent.mkdir(parents=True,exist_ok=True)
                    with path.open('wb') as output:output.write(data);output.flush();os.fsync(output.fileno())
                    path.chmod(0o444)
                for directory in sorted([p for p in stage.rglob('*') if p.is_dir()]+[stage],key=lambda p:len(p.parts),reverse=True):
                    fd=os.open(directory,os.O_RDONLY);os.fsync(fd);os.close(fd)
                os.rename(stage,destination)
        # Verify complete stored revision even when reactivating an old digest.
        check=RevisionStore(store).load(revision_id);check.private_copy.cleanup()
        pointer=encode({'schema_version':REVISION_VERSION,'revision_id':revision_id})
        fd,name=tempfile.mkstemp(dir=store,prefix='.active-')
        try:
            with os.fdopen(fd,'wb') as output:output.write(pointer);output.flush();os.fsync(output.fileno())
            os.replace(name,store/'ACTIVE.json')
            for directory in (revisions,store):
                fd=os.open(directory,os.O_RDONLY);os.fsync(fd);os.close(fd)
        finally:
            if os.path.exists(name):os.unlink(name)
        return revision_id

def main():
    parser=argparse.ArgumentParser(description='Publish reviewed cached evidence atomically; no API calls')
    parser.add_argument('--source',required=True);parser.add_argument('--store',required=True);args=parser.parse_args()
    try:print(json.dumps({'revision_id':publish(args.source,args.store),'new_api_requests':0}))
    except Exception:raise SystemExit('revision_publication_failed') from None
if __name__=='__main__':main()
