"""Synthetic HTML safety fixture, never used as proof of a real mapping."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from minimize_sisal_page import retain_anchors,PDF_URLS
class SimulatedPageMinimizationTests(unittest.TestCase):
 data_origin='synthetic_html_security_fixture_not_live_evidence'
 def test_embedded_non_document_key_is_not_retained(self):
  chunks=[b'<a href="'+url+b'">document</a>' for url in PDF_URLS]
  raw=b'<script>synthetic-service-key-never-publish</script>'+b'\n'.join(chunks)
  excerpt=retain_anchors(raw)
  self.assertNotIn(b'synthetic-service-key-never-publish',excerpt)
  for original in chunks:self.assertIn(original,excerpt)
 def test_missing_authorized_document_link_is_blocked(self):
  with self.assertRaises(ValueError):retain_anchors(b'<a href="https://evil.example/file.pdf">fake</a>')
 def test_credential_in_retained_anchor_is_blocked(self):
  raw=b'\n'.join(b'<a data-code="code=synthetic" href="'+url+b'">document</a>' for url in PDF_URLS)
  with self.assertRaises(ValueError):retain_anchors(raw)
