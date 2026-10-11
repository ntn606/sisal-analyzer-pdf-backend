"""Persist test identity and data origin, preserving the runner exit status."""
from pathlib import Path
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
class Result(unittest.TextTestResult):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.cases=[]
 def startTest(self,test):self.cases.append({'test':test.id(),'data_origin':test.data_origin,'outcome':'running'});super().startTest(test)
 def addSuccess(self,test):self.cases[-1]['outcome']='passed';super().addSuccess(test)
 def addFailure(self,test,error):self.cases[-1]['outcome']='failed';super().addFailure(test,error)
 def addError(self,test,error):self.cases[-1]['outcome']='error';super().addError(test,error)
if __name__=='__main__':
 suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
 with (ROOT/'reports/wrapper-tests.log').open('w') as log:result=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=Result).run(suite)
 summary={'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'successful':result.wasSuccessful(),'provider_api_requests':0,'cases':result.cases}
 (ROOT/'reports/wrapper-tests.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k!='cases'}));raise SystemExit(0 if result.wasSuccessful() else 1)
