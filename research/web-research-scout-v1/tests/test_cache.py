"""Synthetic cache documents, concurrency and corruptions; no web data."""

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from web_research_scout.cache import EvidenceCache, encoded
from web_research_scout.security import SafeError


class CacheTests(unittest.TestCase):
    data_origin = "synthetic_cache_documents"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cache = EvidenceCache(self.root)

    def test_missing_snapshot(self):
        with self.assertRaises(SafeError):
            self.cache.read()

    def test_activate_roundtrip_and_immutable_name(self):
        rev = self.cache.activate({"a.json": {"n": 1}})
        self.assertEqual(self.cache.read(), (rev, {"a.json": {"n": 1}}))
        self.assertEqual(self.cache.activate({"a.json": {"n": 1}}), rev)

    def test_tampered_snapshot_hash(self):
        rev = self.cache.activate({"a.json": 1})
        (self.root / "revisions" / rev / "a.json").write_text("2")
        with self.assertRaises(SafeError) as error:
            self.cache.read()
        self.assertEqual(error.exception.code, "cache_file_integrity_failed")

    def test_missing_document(self):
        rev = self.cache.activate({"a.json": 1})
        (self.root / "revisions" / rev / "a.json").unlink()
        with self.assertRaises(SafeError):
            self.cache.read()

    def test_tampered_manifest(self):
        rev = self.cache.activate({"a.json": 1})
        (self.root / "revisions" / rev / "manifest.json").write_text("{}")
        with self.assertRaises(SafeError):
            self.cache.read()

    def test_corrupt_existing_revision_cannot_replace_good_pointer(self):
        old = self.cache.activate({"a.json": 1})
        new = self.cache.activate({"a.json": 2})
        self.cache.activate({"a.json": 1})
        (self.root / "revisions" / new / "a.json").write_text("3")
        with self.assertRaises(SafeError):
            self.cache.activate({"a.json": 2})
        self.assertEqual(self.cache.read()[0], old)

    def test_traversal_absolute_reserved_paths_rejected(self):
        for name in (
            "../escape.json",
            "/tmp/escape.json",
            "a\\b.json",
            "manifest.json",
        ):
            with self.subTest(name=name), self.assertRaises(SafeError):
                self.cache.activate({name: 1})

    def test_symlink_documents_and_active_pointer_rejected(self):
        rev = self.cache.activate({"a.json": 1})
        target = self.root / "revisions" / rev / "a.json"
        outside = self.root / "outside.json"
        outside.write_text("1\n")
        target.unlink()
        target.symlink_to(outside)
        with self.assertRaises(SafeError):
            self.cache.read()
        target.unlink()
        target.write_bytes(encoded(1))
        pointer = self.root / "ACTIVE.json"
        outside.write_bytes(pointer.read_bytes())
        pointer.unlink()
        pointer.symlink_to(outside)
        with self.assertRaises(SafeError):
            self.cache.read()

    def test_file_and_count_limits(self):
        for docs in (
            {"big.json": "x" * 2000001},
            {f"{n}.json": n for n in range(129)},
            {},
        ):
            with self.assertRaises(SafeError):
                self.cache.activate(docs)

    def test_concurrent_activation_read_is_coherent(self):
        self.cache.activate({"a.json": 0, "b.json": 0})

        def writer():
            for n in range(1, 30):
                self.cache.activate({"a.json": n, "b.json": n})

        def reader():
            for n in range(150):
                rev, docs = self.cache.read()
                self.assertEqual(docs["a.json"], docs["b.json"])
                self.assertEqual(len(rev), 64)

        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = [pool.submit(writer), *(pool.submit(reader) for _ in range(3))]
            for job in jobs:
                job.result()

    def test_one_read_materialized_snapshot_survives_activation(self):
        old = self.cache.activate({"a.json": 1})
        rev, docs = self.cache.read()
        new = self.cache.activate({"a.json": 2})
        self.assertEqual(rev, old)
        self.assertEqual(docs["a.json"], 1)
        self.assertEqual(self.cache.read()[0], new)

    def test_concurrent_identical_revision_activation(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            revisions = list(
                pool.map(lambda n: self.cache.activate({"a.json": 1}), range(16))
            )
        self.assertEqual(len(set(revisions)), 1)
        self.assertEqual(self.cache.read()[0], revisions[0])
