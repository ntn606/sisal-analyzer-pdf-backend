"""Synthetic journal integrity, temporal and concurrency regressions."""

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from fixtures import AFTER, NOW, dossier, result
from football_validation.common import ValidationError, canonical, loads, schema_errors
from football_validation.register import Registry


class RegisterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.registry = Registry(
            self.tmp.name, mode="synthetic_test", _clock=lambda: NOW
        )

    def test_record_complete_snapshot_and_immutable_input(self):
        data = dossier()
        record = self.registry.record_prediction(data)
        self.assertEqual(schema_errors(record, "record"), [])
        self.assertEqual(record["recorded_at"], "2026-10-14T10:00:00Z")
        self.assertEqual(record["data"]["evaluated_quote"], "2.10")
        data["decision"]["reasons"] = ["Changed caller input"]
        record["data"]["snapshot"]["decision"]["status"] = "watch"
        loaded = self.registry.get(record["record_id"])
        self.assertEqual(loaded["data"]["snapshot"]["decision"]["status"], "candidate")
        self.assertNotEqual(
            loaded["data"]["snapshot"]["decision"]["reasons"],
            data["decision"]["reasons"],
        )

    def test_unique_ids_and_no_update_delete_interface(self):
        one = self.registry.record_prediction(dossier())
        two = self.registry.record_prediction(dossier())
        self.assertNotEqual(one["record_id"], two["record_id"])
        self.assertEqual(two["previous_hash"], one["content_hash"])
        self.assertEqual(self.registry.get(one["record_id"]), one)
        self.assertFalse(hasattr(self.registry, "update"))
        self.assertFalse(hasattr(self.registry, "delete"))

    def test_modified_snapshot_detected(self):
        self.registry.record_prediction(dossier())
        record = loads(self.registry.path.read_bytes())
        record["data"]["snapshot"]["decision"]["reasons"] = ["Tampered"]
        self.registry.path.write_bytes(canonical(record) + b"\n")
        with self.assertRaisesRegex(ValidationError, "journal_integrity_failed"):
            self.registry.verify()

    def test_prediction_and_result_separate_and_original_unchanged(self):
        prediction = self.registry.record_prediction(dossier())
        original = self.registry.path.read_bytes()
        later = Registry(self.tmp.name, mode="synthetic_test", _clock=lambda: AFTER)
        outcome = later.record_outcome(prediction["record_id"], result())
        self.assertEqual(outcome["record_type"], "outcome")
        self.assertEqual(outcome["data"]["prediction_hash"], prediction["content_hash"])
        self.assertEqual(outcome["data"]["evaluation"]["status"], "winning")
        self.assertTrue(self.registry.path.read_bytes().startswith(original))
        self.assertEqual(self.registry.get(prediction["record_id"]), prediction)
        self.assertEqual(later.verify()["count"], 2)

    def test_outcome_correction_appends_another_separate_record(self):
        prediction = self.registry.record_prediction(dossier())
        later = Registry(self.tmp.name, mode="synthetic_test", _clock=lambda: AFTER)
        one = later.record_outcome(prediction["record_id"], result())
        two = later.record_outcome(
            prediction["record_id"], result({"home": 0, "away": 1})
        )
        self.assertNotEqual(one["record_id"], two["record_id"])
        self.assertEqual(later.get(one["record_id"]), one)
        self.assertEqual(later.verify()["count"], 3)

    def test_no_record_after_or_at_kickoff(self):
        for hours in (56, 57):
            later = Registry(
                self.tmp.name,
                mode="synthetic_test",
                _clock=lambda: NOW + timedelta(hours=hours),
            )
            with self.assertRaisesRegex(ValidationError, "kickoff_reached"):
                later.record_prediction(dossier())
        self.assertEqual(self.registry.verify()["count"], 0)

    def test_stale_quote_revalidated_at_registration(self):
        later = Registry(
            self.tmp.name,
            mode="synthetic_test",
            _clock=lambda: NOW + timedelta(hours=2),
        )
        with self.assertRaisesRegex(ValidationError, "odds_stale"):
            later.record_prediction(dossier())

    def test_kickoff_crossed_during_preparation_blocks_append(self):
        times = iter([NOW, NOW + timedelta(hours=56)])
        registry = Registry(
            self.tmp.name, mode="synthetic_test", _clock=lambda: next(times)
        )
        with self.assertRaisesRegex(ValidationError, "kickoff_reached"):
            registry.record_prediction(dossier())
        self.assertEqual(self.registry.verify()["count"], 0)

    def test_recorded_at_cannot_be_supplied(self):
        data = dossier()
        data["recorded_at"] = "2026-10-13T00:00:00Z"
        with self.assertRaisesRegex(ValidationError, "dossier_blocked"):
            self.registry.record_prediction(data)

    def test_partial_write_blocks_further_appends(self):
        self.registry.record_prediction(dossier())
        with self.registry.path.open("ab") as stream:
            stream.write(b'{"partial":')
        with self.assertRaisesRegex(ValidationError, "journal_partial_write"):
            self.registry.record_prediction(dossier())

    def test_tail_deletion_detected_with_external_checkpoint(self):
        self.registry.record_prediction(dossier())
        self.registry.record_prediction(dossier())
        checkpoint = self.registry.verify()
        lines = self.registry.path.read_bytes().splitlines(keepends=True)
        self.registry.path.write_bytes(lines[0])
        # The remaining prefix is intrinsically valid; the trusted checkpoint
        # is necessary to detect truncation. We document this limitation.
        self.assertEqual(self.registry.verify()["count"], 1)
        with self.assertRaisesRegex(ValidationError, "checkpoint_mismatch"):
            self.registry.verify(checkpoint)

    def test_old_checkpoint_allows_valid_new_appends(self):
        self.registry.record_prediction(dossier())
        checkpoint = self.registry.verify()
        self.registry.record_prediction(dossier())
        self.assertEqual(self.registry.verify(checkpoint)["count"], 2)

    def test_concurrent_writers_create_consistent_chain(self):
        def write(_):
            return Registry(
                self.tmp.name, mode="synthetic_test", _clock=lambda: NOW
            ).record_prediction(dossier())

        with ThreadPoolExecutor(max_workers=4) as executor:
            records = list(executor.map(write, range(12)))
        self.assertEqual(len({r["record_id"] for r in records}), 12)
        self.assertEqual(sorted(r["sequence"] for r in records), list(range(1, 13)))
        self.assertEqual(self.registry.verify()["count"], 12)

    def test_symlink_journal_rejected(self):
        target = Path(self.tmp.name) / "other.jsonl"
        target.write_text("")
        self.registry.path.symlink_to(target)
        with self.assertRaises(OSError):
            self.registry.verify()

    def test_duplicate_json_keys_and_non_finite_numbers(self):
        for invalid in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
            with self.assertRaises(ValidationError):
                loads(invalid)

    def test_unknown_prediction_cannot_receive_result(self):
        with self.assertRaisesRegex(ValidationError, "prediction_not_found"):
            self.registry.record_outcome("unknown", result())

    def test_mode_cannot_turn_synthetic_prediction_into_real(self):
        record = self.registry.record_prediction(dossier())
        real = Registry(self.tmp.name, _clock=lambda: AFTER)
        with self.assertRaisesRegex(ValidationError, "registry_mode_mismatch"):
            real.record_outcome(record["record_id"], result())

    def test_missing_score_saved_only_as_not_evaluable(self):
        record = self.registry.record_prediction(dossier())
        later = Registry(self.tmp.name, mode="synthetic_test", _clock=lambda: AFTER)
        outcome = result()
        outcome["regular_time"] = None
        saved = later.record_outcome(record["record_id"], outcome)
        self.assertEqual(saved["data"]["evaluation"]["status"], "not_evaluable")

    def test_clock_rollback_rejected(self):
        self.registry.record_prediction(dossier())
        data = dossier()
        data["analysis_at"] = "2026-10-14T09:59:00Z"
        earlier = Registry(
            self.tmp.name,
            mode="synthetic_test",
            _clock=lambda: NOW - timedelta(seconds=1),
        )
        with self.assertRaisesRegex(ValidationError, "clock_moved_backwards"):
            earlier.record_prediction(data)
