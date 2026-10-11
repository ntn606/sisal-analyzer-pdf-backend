"""Synthetic credential formats, never real credentials or mapping evidence."""
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from minimize_sisal_page import retain_anchors,PDF_URLS
from history_v2_probe.publication_safety import findings
class PublicationSafetyTests(unittest.TestCase):
    data_origin='synthetic_secret_format_and_html_attacks_not_real_evidence'
    def page(self,attribute=b'',label=b'document'):
        return b'\n'.join(b'<a '+attribute+b' href="'+url+b'">'+label+b'</a>' for url in PDF_URLS)
    def test_unknown_attributes_cannot_hide_credentials(self):
        for attr in (b'data-token="placeholder"',b'onclick="script()"',b'style="hidden"',b'title="placeholder"'):
            with self.subTest(attribute=attr):
                with self.assertRaises(ValueError):retain_anchors(self.page(attr))
    def test_text_and_nested_elements_cannot_hide_credentials(self):
        for label in (b'<span>document</span>',b'document <!-- hidden -->',b'document '+b'a'*100):
            with self.assertRaises(ValueError):retain_anchors(self.page(label=label))
    def test_duplicate_href_rejected(self):
        with self.assertRaises(ValueError):retain_anchors(self.page(b'href="https://evil.invalid"'))
    def test_encoded_url_and_query_rejected(self):
        for suffix in (b'?access_token=placeholder',b'#fragment'):
            raw=self.page().replace(PDF_URLS[0],PDF_URLS[0]+suffix)
            with self.assertRaises(ValueError):retain_anchors(raw)
    def test_known_secret_formats_detected_without_echo(self):
        cases=[('private_key','-----BEGIN '+'PRIVATE KEY-----'),('aws_access_id','AKIA'+'A'*16),('github_token','ghp_'+'a'*30),('jwt','eyJ'+'a'*12+'.'+'b'*16+'.'+'c'*16),('credential_assignment','api_key='+'x'*32),('credential_query','https://example.invalid/?sig='+'x'*32),('bearer_value','Bearer '+'x'*32),('azure_function_key','x'*42+'AZFu'+'x'*4)]
        for expected,text in cases:self.assertIn(expected,findings(text));self.assertNotIn(text,findings(text))
    def test_encoded_credential_detected(self):
        self.assertIn('credential_query',findings('https://example.invalid/?to%6ben='+'a'*24))
    def test_official_excerpts_still_exact(self):
        root=Path(__file__).resolve().parents[1]
        for path in (root/'cases').glob('*/evidence/sisal-page-excerpt.html'):
            raw=path.read_bytes();self.assertEqual(retain_anchors(raw),raw);self.assertFalse(findings(raw))
    def test_long_nonmatching_token_run_has_bounded_scanning(self):
        from time import perf_counter
        start=perf_counter();self.assertEqual(findings('a'*100_000),[])
        self.assertLess(perf_counter()-start,3,'Scanning must avoid quadratic Azure regex backtracking')
