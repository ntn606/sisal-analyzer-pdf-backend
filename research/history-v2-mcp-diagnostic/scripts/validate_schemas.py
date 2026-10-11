"""Offline deterministic schema checks for existing and HTTP-derived artifacts."""
from pathlib import Path
import json,sys
from jsonschema import Draft202012Validator,FormatChecker
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from history_v2_probe.revisions import publish,RevisionStore
import tempfile

def load(path):return json.loads(path.read_text())
def main():
    schemas={}
    for path in (ROOT/'contracts').rglob('*.schema.json'):
        schema=load(path);Draft202012Validator.check_schema(schema)
        schemas[str(path.relative_to(ROOT/'contracts'))]=Draft202012Validator(schema,format_checker=FormatChecker())
    checked=[]
    def verify(path,key):schemas[key].validate(load(path));checked.append({'file':str(path.relative_to(ROOT)),'schema':key})
    for path in (ROOT/'cases').glob('*/request*.json'):verify(path,'adapter/request.schema.json')
    for path in (ROOT/'cases').glob('*/registry.json'):verify(path,'adapter/registry.schema.json')
    for path in (ROOT/'cases').glob('*/evidence/proof-*.json'):verify(path,'adapter/evidence.schema.json')
    for path in (ROOT/'cases').glob('*/real_only*.json'):verify(path,'adapter/response.schema.json')
    for path in (ROOT/'examples').glob('*.json'):verify(path,'response.schema.json')
    report=load(ROOT/'reports/http-authenticated-evidence.json')
    for output in report['outputs']:schemas['response.schema.json'].validate(output)
    with tempfile.TemporaryDirectory() as directory:
        revision_id=publish(ROOT,directory)
        schemas['revision.schema.json'].validate(load(Path(directory)/'revisions'/revision_id/'REVISION.json'))
        schemas['active-revision.schema.json'].validate(load(Path(directory)/'ACTIVE.json'))
    result={'schema_files_checked':len(schemas),'artifact_documents_checked':len(checked)+4,'passed':True,'documents':checked,'http_response_outputs_checked':2,'revision_and_pointer_checked':2}
    (ROOT/'reports/secure-schema-validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='documents'}))
if __name__=='__main__':main()
