"""Synthetic anti-secret scanner exception policy; no real secret or evidence."""
from pathlib import Path
import hashlib,json,tempfile,unittest
from unittest.mock import patch
from scripts import scan_publication
class ScanPolicyTests(unittest.TestCase):
    data_origin='synthetic_source_bytes_and_scanner_exception_policy_no_real_credentials'
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.patch=patch.object(scan_publication,'ROOT',self.root);self.patch.start();self.addCleanup(self.patch.stop)
    def fixture(self,name):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('api_key='+'x'*32)
        contracts=self.root/'contracts';contracts.mkdir(exist_ok=True)
        value={'files':{name:{'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'rules':['credential_assignment'],'reason':'Synthetic test fixture'}}}
        (contracts/'synthetic-scan-exceptions.json').write_text(json.dumps(value));return path
    def test_exact_reviewed_source_is_reported_as_exception(self):
        path=self.fixture('tests/synthetic.py');result=scan_publication.scan([path])
        self.assertTrue(result['passed']);self.assertEqual(len(result['reviewed_synthetic_test_code_exceptions']),1)
        self.assertNotIn('x'*32,json.dumps(result))
    def test_any_source_byte_change_invalidates_exception(self):
        path=self.fixture('tests/synthetic.py');path.write_text(path.read_text()+'\n')
        self.assertFalse(scan_publication.scan([path])['passed'])
    def test_evidence_can_never_receive_test_source_exception(self):
        path=self.fixture('cases/example/evidence/proof.json')
        self.assertFalse(scan_publication.scan([path])['passed'])
