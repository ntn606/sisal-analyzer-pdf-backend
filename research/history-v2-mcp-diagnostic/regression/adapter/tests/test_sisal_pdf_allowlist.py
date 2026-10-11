"""Offline URL/provenance tests. Synthetic fixtures do not verify club identity."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

from identity_adapter.core import EvidenceStore, SISAL_QUOTE_PAGE, VERSION, _public_source, probe
from identity_adapter.cli import main
from history_provider_v2 import Dataset
from history_provider_v2.provider import InputError

URL = 'https://landing.sisal.it/volantini/Scommesse_Sport/Quote/calcio%20base%20per%20data.pdf'
NOW = datetime(2026, 10, 10, 19, 40, tzinfo=timezone.utc)


class SyntheticAllowlistTests(unittest.TestCase):
    """All PDF/HTML byte fixtures, declarations and events in this class are synthetic."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        guard = patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden'))
        guard.start()
        self.addCleanup(guard.stop)
        self.registry = {'schema_version': VERSION, 'evidence': {}}
        self.pdf = self.attach('sheet.pdf', b'%PDF-1.6\nsynthetic offline byte fixture\n%%EOF\n')
        self.page = self.attach('page.html', f'<html><a href="{URL}">Calcio Base per Data</a></html>'.encode())
        self.payload = {'origin': 'real_saved', 'kind': 'sisal_event', 'source': URL,
                        'acquired_at': '2026-10-10T19:13:07Z', 'record': {},
                        'document': {**self.pdf, 'media_type': 'application/pdf',
                                     'landing_page': {**self.page, 'source': SISAL_QUOTE_PAGE,
                                                      'media_type': 'text/html',
                                                      'acquired_at': '2026-10-10T19:12:31Z'}}}
        # real_saved here exercises the validation branch only; these bytes are
        # synthetic unit fixtures, never used in a real registry or mapping.

    def attach(self, filename, raw):
        (self.root / filename).write_bytes(raw)
        return {'file': filename, 'sha256': hashlib.sha256(raw).hexdigest()}

    def store(self, payload=None):
        raw = json.dumps(self.payload if payload is None else payload).encode()
        ref = self.attach('evidence.json', raw)
        self.registry['evidence']['sisal'] = ref
        return EvidenceStore(self.registry, self.root, 'real_only', NOW)

    def assert_blocked(self, payload, code):
        with self.assertRaisesRegex(InputError, code):
            self.store(payload).get('sisal', 'sisal_event')

    def test_synthetic_official_landing_path_is_allowed_with_provenance(self):
        self.assertTrue(_public_source(URL, 'sisal_event', 'real_saved'))
        self.assertEqual(self.store().get('sisal')['source'], URL)

    def test_synthetic_fake_domains_and_userinfo_are_rejected(self):
        for host in ('landing.sisal.it.evil.example', 'evil-landing.sisal.it', 'landing-sisal.it',
                     'landing.sisal.it.', 'www.landing.sisal.it', 'landing.sisaI.it',
                     'landing.sisal.it@evil.example', 'evil.example@landing.sisal.it',
                     '@landing.sisal.it', 'landing.sisal.it%2eevil.example'):
            with self.subTest(host=host):
                self.assertFalse(_public_source(URL.replace('landing.sisal.it', host), 'sisal_event', 'real_saved'))

    def test_synthetic_http_ports_queries_fragments_and_controls_are_rejected(self):
        bad = [URL.replace('https:', 'http:'), URL.replace('https:', 'ftp:'),
               URL.replace('landing.sisal.it', 'landing.sisal.it:80'),
               URL.replace('landing.sisal.it', 'landing.sisal.it:bad'),
               URL.replace('landing.sisal.it', 'landing.sisal.it:'),
               URL + '?token=synthetic-marker', URL + '?', URL + '#section', URL + '#',
               '\n' + URL, URL + '\t', URL.replace('/volantini/', '/volantini\\'),
               URL.replace('%20', ' ')]
        for value in bad:
            with self.subTest(value=value):
                self.assertFalse(_public_source(value, 'sisal_event', 'real_saved'))

    def test_synthetic_unapproved_paths_document_types_and_traversal_are_rejected(self):
        paths = ['/api/v1/live/list', '/private/sheet.pdf', '/volantini/Scommesse_Sport/Quote/unknown.pdf',
                 '/volantini/Scommesse_Sport/Quote/calcio%20base%20per%20data.html',
                 '/volantini/Scommesse_Sport/Quote/../Quote/calcio%20base%20per%20data.pdf',
                 '/volantini/Scommesse_Sport/Quote/%2e%2e/calcio%20base%20per%20data.pdf',
                 '/volantini/Scommesse_Sport/Quote/calcio%2520base%2520per%2520data.pdf']
        for path in paths:
            with self.subTest(path=path):
                self.assertFalse(_public_source('https://landing.sisal.it' + path, 'sisal_event', 'real_saved'))

    def test_synthetic_document_provenance_cannot_be_omitted(self):
        payload = deepcopy(self.payload)
        del payload['document']
        self.assert_blocked(payload, 'missing_or_invalid_sisal_pdf_document')

    def test_synthetic_wrong_mime_type_is_rejected(self):
        payload = deepcopy(self.payload)
        payload['document']['media_type'] = 'text/html'
        self.assert_blocked(payload, 'missing_or_invalid_sisal_pdf_document')

    def test_synthetic_html_renamed_pdf_is_rejected(self):
        payload = deepcopy(self.payload)
        payload['document'].update(self.attach('sheet.pdf', b'<html>not a PDF</html>'))
        self.assert_blocked(payload, 'invalid_pdf_signature')

    def test_synthetic_truncated_pdf_is_rejected(self):
        payload = deepcopy(self.payload)
        payload['document'].update(self.attach('sheet.pdf', b'%PDF-1.6\nno closing marker'))
        self.assert_blocked(payload, 'invalid_pdf_signature')

    def test_synthetic_pdf_hash_mismatch_is_rejected(self):
        (self.root / 'sheet.pdf').write_bytes(b'%PDF-1.6\nchanged\n%%EOF')
        self.assert_blocked(self.payload, 'document_hash_mismatch')

    def test_synthetic_page_hash_mismatch_is_rejected(self):
        (self.root / 'page.html').write_bytes(b'changed')
        self.assert_blocked(self.payload, 'document_hash_mismatch')

    def test_synthetic_document_path_cannot_escape_evidence_root(self):
        payload = deepcopy(self.payload)
        payload['document']['file'] = '../outside.pdf'
        self.assert_blocked(payload, 'document_path_outside_root')

    def test_synthetic_absolute_document_path_is_rejected(self):
        payload = deepcopy(self.payload)
        payload['document']['file'] = str(self.root / 'sheet.pdf')
        self.assert_blocked(payload, 'invalid_document_reference')

    def test_synthetic_invalid_hash_type_is_rejected(self):
        payload = deepcopy(self.payload)
        payload['document']['sha256'] = 17
        self.assert_blocked(payload, 'invalid_document_reference')

    def test_synthetic_provenance_requires_the_exact_official_page(self):
        for source in ('https://www.sisal.it.evil.example/scommesse-matchpoint/foglio-quote',
                       'http://www.sisal.it/scommesse-matchpoint/foglio-quote',
                       'https://www.sisal.it/scommesse-matchpoint/foglio-quote?private=1',
                       'https://www.sisal.it/other'):
            with self.subTest(source=source):
                payload = deepcopy(self.payload)
                payload['document']['landing_page']['source'] = source
                self.assert_blocked(payload, 'invalid_sisal_pdf_provenance_page')

    def test_synthetic_page_must_contain_the_actual_pdf_link(self):
        payload = deepcopy(self.payload)
        payload['document']['landing_page'].update(self.attach('page.html', b'<html>No link</html>'))
        self.assert_blocked(payload, 'sisal_pdf_not_linked_from_official_page')

    def test_synthetic_script_text_does_not_count_as_a_public_link(self):
        payload = deepcopy(self.payload)
        payload['document']['landing_page'].update(self.attach('page.html', f'<script>var url="{URL}";</script>'.encode()))
        self.assert_blocked(payload, 'sisal_pdf_not_linked_from_official_page')

    def test_synthetic_duplicate_href_attributes_do_not_establish_provenance(self):
        payload = deepcopy(self.payload)
        payload['document']['landing_page'].update(self.attach('page.html',
            f'<a href="https://evil.example/sheet.pdf" href="{URL}">ambiguous</a>'.encode()))
        self.assert_blocked(payload, 'sisal_pdf_not_linked_from_official_page')

    def test_synthetic_page_observed_after_pdf_evidence_is_rejected(self):
        payload = deepcopy(self.payload)
        payload['document']['landing_page']['acquired_at'] = '2026-10-10T19:20:00Z'
        self.assert_blocked(payload, 'sisal_page_acquired_after_pdf_evidence')

    def test_synthetic_schema_supports_unavailable_provider_without_invented_ids(self):
        import jsonschema
        root = Path(__file__).resolve().parents[1]
        request = {'schema_version': VERSION, 'evidence_mode': 'real_only', 'purpose': 'diagnostic',
                   'verified_at': NOW.isoformat(), 'api_football': {'state': 'unavailable'},
                   'football_data': {'state': 'unavailable'}, 'history_scope': {'home': ['SA'], 'away': ['SA']},
                   'sisal_event': {'palinsesto': '36411', 'avvenimento': '1370', 'home': 'Como', 'away': 'Roma',
                                   'competition_canonical_id': 'local:competition:SA', 'season_start_year': 2026,
                                   'date': '2026-10-11', 'time': '12:30:00', 'timezone': 'Europe/Rome', 'evidence_id': 'sisal'}}
        jsonschema.validate(request, json.loads((root / 'contracts/request.schema.json').read_text()))
        result = probe(request, self.registry, Dataset(()), self.root)
        self.assertEqual(result['status'], 'provider_unavailable')
        self.assertEqual(result['histories'], {})
        self.assertFalse(result['ready_for_quant'])
        invalid = deepcopy(request)
        invalid['api_football']['state'] = 'available'
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(invalid, json.loads((root / 'contracts/request.schema.json').read_text()))

    def test_synthetic_cli_unavailable_provider_is_explicit_and_blocks_histories(self):
        request = {'schema_version': VERSION, 'evidence_mode': 'real_only', 'purpose': 'diagnostic',
                   'verified_at': NOW.isoformat(), 'api_football': {'state': 'unavailable'},
                   'football_data': {'state': 'unavailable'}, 'history_scope': {'home': ['SA'], 'away': ['SA']},
                   'sisal_event': {'palinsesto': '36411', 'avvenimento': '1370', 'home': 'Como', 'away': 'Roma',
                                   'competition_canonical_id': 'local:competition:SA', 'season_start_year': 2026,
                                   'date': '2026-10-11', 'time': '12:30:00', 'timezone': 'Europe/Rome', 'evidence_id': 'sisal'}}
        (self.root / 'request.json').write_text(json.dumps(request))
        (self.root / 'registry.json').write_text(json.dumps(self.registry))
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(['--request', str(self.root / 'request.json'), '--registry', str(self.root / 'registry.json'),
                         '--evidence', str(self.root), '--snapshots', str(self.root)])
        result = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'provider_unavailable')
        self.assertFalse(result['diagnostic_statistics_allowed'])
        self.assertEqual(result['histories'], {})


class RealSavedSisalDocumentTests(unittest.TestCase):
    """Real saved public PDF/HTML only: does not verify the cross-provider mapping."""
    def test_real_saved_official_pdf_and_page_pass_document_provenance_only(self):
        source = Path(__file__).resolve().parents[1] / 'fixtures/sisal-real'
        event = json.loads((source / 'sisal-candidate-event.json').read_text())
        page_meta = json.loads((source / 'sisal-foglio-quote.meta.json').read_text())
        with tempfile.TemporaryDirectory() as directory, patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden')):
            root = Path(directory)
            pdf = (source / 'sisal-calcio-base-per-data.pdf').read_bytes()
            html = (source / 'sisal-foglio-quote.html').read_bytes()
            (root / 'sheet.pdf').write_bytes(pdf)
            (root / 'page.html').write_bytes(html)
            payload = {'origin': 'real_saved', 'kind': 'sisal_event', 'source': event['source'],
                       'acquired_at': event['acquired_at'], 'record': event['record'],
                       'document': {'file': 'sheet.pdf', 'sha256': hashlib.sha256(pdf).hexdigest(), 'media_type': 'application/pdf',
                                    'landing_page': {'source': SISAL_QUOTE_PAGE, 'file': 'page.html',
                                                     'sha256': hashlib.sha256(html).hexdigest(), 'media_type': 'text/html',
                                                     'acquired_at': page_meta['completed_at']}}}
            raw = json.dumps(payload).encode()
            (root / 'sisal.json').write_bytes(raw)
            registry = {'evidence': {'sisal': {'file': 'sisal.json', 'sha256': hashlib.sha256(raw).hexdigest()}}}
            actual = EvidenceStore(registry, root, 'real_only', NOW).get('sisal', 'sisal_event')
            self.assertEqual(actual['record']['palinsesto'], '36411')
            self.assertEqual(actual['record']['avvenimento'], '1370')
