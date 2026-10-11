"""Run an entire suite with global external DNS/socket denial, no real secrets."""
from pathlib import Path
import json,os,socket,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
# Provider credentials are deliberately absent even in backend mock regressions.
os.environ.pop('API_FOOTBALL_KEY',None);os.environ.pop('FOOTBALL_DATA_TOKEN',None)
original_connect=socket.socket.connect;original_ex=socket.socket.connect_ex;original_dns=socket.getaddrinfo
attempts={'external_socket_attempts':0,'external_dns_attempts':0,'loopback_socket_connections':0}
def local(address):return isinstance(address,tuple) and address[0] in ('127.0.0.1','::1','localhost')
def guard(function):
    def invoke(sock,address):
        if sock.family==socket.AF_UNIX:return function(sock,address)
        if not local(address):attempts['external_socket_attempts']+=1;raise AssertionError('Offline suite forbids external sockets')
        attempts['loopback_socket_connections']+=1;return function(sock,address)
    return invoke
socket.socket.connect=guard(original_connect);socket.socket.connect_ex=guard(original_ex)
def dns(host,*args,**kwargs):
    if host not in ('127.0.0.1','::1','localhost',None):attempts['external_dns_attempts']+=1;raise AssertionError('Offline suite forbids external DNS')
    return original_dns(host,*args,**kwargs)
socket.getaddrinfo=dns
class Result(unittest.TextTestResult):
    def __init__(self,*a,**kw):super().__init__(*a,**kw);self.cases=[]
    def startTest(self,test):
        origin=getattr(test,'data_origin',None)
        if sys.argv[1]=='provider':origin='real_saved_FD_snapshots_offline' if test.__class__.__name__=='RealSnapshotTests' else 'synthetic_history_fixtures'
        if sys.argv[1]=='adapter':origin='real_saved_Sisal_document_only_no_cross_provider_identity' if test.__class__.__name__=='RealSavedSisalDocumentTests' else 'hybrid_real_FD_history_synthetic_provider_identity' if test.__class__.__name__=='HybridTests' else 'synthetic_identity_or_allowlist_fixtures'
        if sys.argv[1]=='backend':origin='mocked_provider_errors_no_live_calls'
        if test.__class__.__name__=='HTTPTests' and test._testMethodName!='test_real_sdk_authenticated_initialize_list_and_both_calls':origin='offline_HTTP_security_or_synthetic_negative_mutations_of_saved_inputs_no_live_validation'
        self.cases.append({'test':test.id(),'data_origin':origin or 'offline_fixture_see_source','outcome':'running'});super().startTest(test)
    def addSuccess(self,test):self.cases[-1]['outcome']='passed';super().addSuccess(test)
    def addFailure(self,test,error):self.cases[-1]['outcome']='failed';super().addFailure(test,error)
    def addError(self,test,error):self.cases[-1]['outcome']='error';super().addError(test,error)
if __name__=='__main__':
    suite_name=sys.argv[1]
    audit=tempfile.TemporaryDirectory(prefix='history-v2-child-audit-')
    audit_path=Path(audit.name)/'events.jsonl'
    os.environ['HISTORY_V2_OFFLINE_AUDIT']=str(audit_path)
    os.environ['PYTHONPATH']=str(ROOT/'scripts/offline_guard')+os.pathsep+os.environ.get('PYTHONPATH','')
    # SDK stdio intentionally inherits a small safe list; extend it only in
    # this offline runner so the unmodified test's child is guarded as well.
    from mcp.client import stdio as stdio_module
    for name in ('PYTHONPATH','HISTORY_V2_OFFLINE_AUDIT'):
        if name not in stdio_module.DEFAULT_INHERITED_ENV_VARS:stdio_module.DEFAULT_INHERITED_ENV_VARS.append(name)
    roots={'wrapper':ROOT,'provider':ROOT/'regression/provider','adapter':ROOT/'regression/adapter','backend':ROOT.parents[1]}
    target=roots[suite_name];sys.path.insert(0,str(target))
    if suite_name=='adapter':sys.path.insert(1,str(ROOT/'regression/provider'))
    tests=unittest.defaultTestLoader.discover(str(target/'tests'))
    with (ROOT/f'reports/secure-{suite_name}-tests.log').open('w') as log:result=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=Result).run(tests)
    events=[json.loads(line)['event'] for line in audit_path.read_text().splitlines()] if audit_path.exists() else []
    attempts['external_socket_attempts']+=events.count('external_socket_denied')
    attempts['external_dns_attempts']+=events.count('external_dns_denied')
    summary={'suite':suite_name,'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'successful':result.wasSuccessful(),'provider_requests':0,**attempts,'guarded_child_python_processes':events.count('guard_installed'),'cases':result.cases}
    (ROOT/f'reports/secure-{suite_name}-tests.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='cases'}));audit.cleanup();raise SystemExit(0 if result.wasSuccessful() and result.testsRun and not attempts['external_socket_attempts'] and not attempts['external_dns_attempts'] and (suite_name!='wrapper' or events.count('guard_installed')>=1) else 1)
