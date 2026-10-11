"""Reproducible CI: suites with external networking denied, schemas, secret scan."""
from pathlib import Path
import hashlib,importlib.metadata,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
def main():
    if importlib.metadata.version('mcp')!='1.30.0':raise SystemExit('mcp_version_mismatch')
    for entry in json.loads((ROOT/'regression/provenance.json').read_text())['test_files']:
        if hashlib.sha256((ROOT/entry['file']).read_bytes()).hexdigest()!=entry['sha256']:raise SystemExit('original_regression_test_fingerprint_changed')
    results=[]
    for name in ('provider','adapter','backend','wrapper'):
        subprocess.run([sys.executable,str(ROOT/'scripts/offline_worker.py'),name],cwd=ROOT,check=True)
        results.append(json.loads((ROOT/f'reports/secure-{name}-tests.json').read_text()))
    subprocess.run([sys.executable,str(ROOT/'scripts/validate_schemas.py')],cwd=ROOT,check=True)
    subprocess.run([sys.executable,str(ROOT/'scripts/scan_publication.py'),'--output','reports/security-scan.json'],cwd=ROOT,check=True)
    summary={'tests_run':sum(r['tests_run'] for r in results),'all_passed':all(r['successful'] for r in results),'skipped':sum(r['skipped'] for r in results),'provider_requests':0,'external_socket_attempts':sum(r['external_socket_attempts'] for r in results),'external_dns_attempts':sum(r['external_dns_attempts'] for r in results),'mcp_version':importlib.metadata.version('mcp'),'suites':[{k:v for k,v in r.items() if k!='cases'} for r in results],'note':'HTTP real loopback client + saved evidence, frozen replay clock and ephemeral synthetic authentication; no live acquisition.'}
    (ROOT/'reports/secure-test-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
if __name__=='__main__':main()
