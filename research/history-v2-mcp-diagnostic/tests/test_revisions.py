"""Atomic revision tests: real saved replays or explicit synthetic mutations."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta
from pathlib import Path
import hashlib,json,shutil,tempfile,threading,unittest
from unittest.mock import patch
from history_v2_probe.revisions import publish,RevisionStore,RevisionProbe,Failure
ROOT=Path(__file__).resolve().parents[1]
STAMP=max(datetime.fromisoformat(json.loads(p.read_text())['verified_at']) for p in (ROOT/'cases').glob('*/request-asof-observation.json'))+timedelta(seconds=1)

def source(directory):
    catalog=json.loads((ROOT/'catalog.json').read_text());names={'catalog.json'}
    for entry in catalog['events']:names.update(entry['files'])
    for name in names:
        target=Path(directory)/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    return Path(directory)

def mutate(root,name,fn):
    path=root/name;value=json.loads(path.read_text());fn(value);path.write_text(json.dumps(value)+'\n')
    cat=json.loads((root/'catalog.json').read_text())
    for entry in cat['events']:
        if name in entry['files']:entry['files'][name]=hashlib.sha256(path.read_bytes()).hexdigest()
    (root/'catalog.json').write_text(json.dumps(cat)+'\n')

class RevisionTests(unittest.TestCase):
    data_origin='real_saved_evidence_with_explicit_synthetic_revision_mutations_no_live_calls'
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=source(self.root/'source');self.store=self.root/'store'
        self.revision_id=publish(self.source,self.store)
        self.manager=RevisionStore(self.store,clock=lambda:STAMP)
        self.addCleanup(self.clear)
    def clear(self):
        if self.manager._current:self.manager._current.private_copy.cleanup()
    def call(self):return RevisionProbe(self.manager).football_history_v2_probe('36411','1885','2026-10-12')
    def test_complete_revision_positive_and_provenance(self):
        result=self.call();self.assertEqual(result['status'],'diagnostic_available');self.assertEqual(result['provenance']['catalog_revision'],self.revision_id)
    def test_missing_snapshot_prevents_start(self):
        (self.store/'revisions'/self.revision_id/'live/snapshots/PL-2026.json').unlink()
        self.assertEqual(self.call()['status'],'provider_unavailable')
    def test_tampered_hash_prevents_loading(self):
        path=self.store/'revisions'/self.revision_id/'live/snapshots/PL-2026.json';path.chmod(0o644);path.write_bytes(b'{}')
        self.assertEqual(self.call()['status'],'data_conflict')
    def test_manifest_tampering_detected(self):
        path=self.store/'revisions'/self.revision_id/'REVISION.json';path.chmod(0o644);path.write_bytes(b'{}')
        self.assertIn('revision_manifest_hash_mismatch',self.call()['blockers'])
    def test_private_copy_immune_to_post_capture_store_mutation(self):
        self.manager.capture()
        path=self.store/'revisions'/self.revision_id/'live/snapshots/PL-2026.json';path.chmod(0o644);path.write_bytes(b'{}')
        self.assertEqual(self.call()['status'],'diagnostic_available')
    def test_synthetic_proof_cannot_be_published(self):
        mutate(self.source,'cases/coventry-newcastle/evidence/proof-review.json',lambda x:x.update(origin='synthetic'))
        with self.assertRaises(Failure):publish(self.source,self.store)
        self.assertEqual(json.loads((self.store/'ACTIVE.json').read_text())['revision_id'],self.revision_id)
    def test_ambiguous_event_cannot_be_published(self):
        mutate(self.source,'catalog.json',lambda x:x['events'].append(deepcopy(x['events'][0])))
        with self.assertRaises(Failure):publish(self.source,self.store)
    def test_mapping_ambiguous_blocks_statistics(self):
        mutate(self.source,'cases/coventry-newcastle/registry.json',lambda x:x['teams'].append(deepcopy(x['teams'][0])))
        publish(self.source,self.store)
        self.assertEqual(self.call()['status'],'identity_unverified');self.assertEqual(self.call()['histories'],{})
    def test_stale_evidence_is_not_revived_by_revision(self):
        self.manager.clock=lambda:STAMP+timedelta(hours=2)
        self.assertEqual(self.call()['status'],'source_stale')
    def test_same_revision_idempotent_publication(self):
        self.assertEqual(publish(self.source,self.store),self.revision_id)
    def test_bad_active_pointer_fails_closed_no_old_fallback(self):
        self.call();(self.store/'ACTIVE.json').write_text('{}')
        self.assertEqual(self.call()['status'],'data_unverified')
    def test_symlink_rejected(self):
        path=self.store/'revisions'/self.revision_id/'live/snapshots/PL-2026.json';path.unlink();path.symlink_to(self.source/'live/snapshots/PL-2026.json')
        self.assertEqual(self.call()['status'],'data_unverified')
    def test_concurrent_activation_pins_old_and_new_requests(self):
        old=self.manager.capture();entered=threading.Event();release=threading.Event()
        original=old.service.football_history_v2_probe
        def paused(*args):entered.set();self.assertTrue(release.wait(10));return original(*args)
        old.service.football_history_v2_probe=paused
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(self.call);self.assertTrue(entered.wait(10))
            mutate(self.source,'cases/coventry-newcastle/request-diagnostic.json',lambda x:x['football_data'].update(state='unavailable'))
            new_id=publish(self.source,self.store);second=pool.submit(self.call);new=second.result(timeout=10)
            release.set();before=first.result(timeout=10)
        self.assertNotEqual(new_id,self.revision_id)
        self.assertEqual(before['status'],'diagnostic_available');self.assertEqual(before['provenance']['catalog_revision'],self.revision_id)
        self.assertEqual(new['status'],'provider_unavailable');self.assertEqual(new['provenance']['catalog_revision'],new_id)
    def test_unsafe_secret_shaped_evidence_is_rejected(self):
        mutate(self.source,'cases/coventry-newcastle/evidence/proof-review.json',lambda x:x.update(access_token='x'*32))
        with self.assertRaisesRegex(Failure,''):publish(self.source,self.store)
        self.assertEqual(json.loads((self.store/'ACTIVE.json').read_text())['revision_id'],self.revision_id)
    def test_full_html_cannot_be_activated_even_without_known_secret(self):
        page=self.source/'cases/coventry-newcastle/evidence/sisal-page-excerpt.html'
        page.write_bytes(b'<html>'+page.read_bytes()+b'</html>')
        cat=json.loads((self.source/'catalog.json').read_text());name=str(page.relative_to(self.source))
        for entry in cat['events']:
            if name in entry['files']:entry['files'][name]=hashlib.sha256(page.read_bytes()).hexdigest()
        (self.source/'catalog.json').write_text(json.dumps(cat)+'\n')
        with self.assertRaises(Failure):publish(self.source,self.store)
    def test_old_revision_can_be_reactivated_atomically(self):
        old_source=source(self.root/'old-source')
        mutate(self.source,'cases/coventry-newcastle/request-diagnostic.json',lambda x:x['football_data'].update(state='unavailable'))
        publish(self.source,self.store);self.assertEqual(self.call()['status'],'provider_unavailable')
        self.assertEqual(publish(old_source,self.store),self.revision_id)
        self.assertEqual(self.call()['status'],'diagnostic_available')
