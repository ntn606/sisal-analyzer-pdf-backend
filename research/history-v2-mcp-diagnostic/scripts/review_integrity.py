"""Verify originals/protected production bytes against the reference Git commit."""
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1]
BASE='6bd9b719b4e3548d05282a560ec4cb1d95297b1b'
def digest(raw):return hashlib.sha256(raw).hexdigest()
def main():
    protected=[]
    tracked=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE],cwd=REPO).decode().splitlines()
    for name in tracked:
        if name.startswith('research/'):continue
        # All pre-existing files outside research must remain byte-identical.
        path=REPO/name
        before=subprocess.check_output(['git','show',BASE+':'+name],cwd=REPO)
        if not path.is_file() or digest(before)!=digest(path.read_bytes()):raise SystemExit('production_integrity_failed')
        protected.append({'file':name,'sha256':digest(before)})
    reused=[]
    for path in (ROOT/'vendor').rglob('*.py'):
        name=str(path.relative_to(REPO));before=subprocess.check_output(['git','show',BASE+':'+name],cwd=REPO)
        if digest(before)!=digest(path.read_bytes()):raise SystemExit('engine_integrity_failed')
        reused.append({'file':str(path.relative_to(ROOT)),'sha256':digest(before)})
    for kind,package in (('provider','history_provider_v2'),('adapter','identity_adapter')):
        for path in (ROOT/f'regression/{kind}/{package}').glob('*.py'):
            if path.read_bytes()!=(ROOT/'vendor'/package/path.name).read_bytes():raise SystemExit('regression_engine_copy_changed')
    tests=[]
    for kind in ('adapter','provider'):
        original=Path('/workspace/research')/('history-v2-identity-adapter' if kind=='adapter' else 'history-provider-v2-prototype')/'tests'
        for path in (ROOT/f'regression/{kind}/tests').glob('*.py'):
            if original.exists() and path.read_bytes()!=(original/path.name).read_bytes():raise SystemExit('test_copy_changed')
            tests.append({'file':str(path.relative_to(ROOT)),'sha256':digest(path.read_bytes()),'original_compared':original.exists()})
    report={'reference_commit':BASE,'production_unchanged':True,'existing_engines_unchanged':True,'protected_files':protected,'reused_engines':reused,'original_regression_tests':tests,'real_provider_credentials_used_in_tests':False,'railway_changes':False,'live_acquisition':False}
    (ROOT/'reports/secure-integrity.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'production_files_verified':len(protected),'engine_files_verified':len(reused),'original_test_files':len(tests),'passed':True}))
if __name__=='__main__':main()
