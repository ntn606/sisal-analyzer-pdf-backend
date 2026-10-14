"""Synthetic schema, CLI and committed example checks."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from fixtures import NOW, dossier
from football_validation.cli import main
from football_validation.common import (
    SCHEMAS,
    load,
    schema_errors,
)
from football_validation.register import Registry
from football_validation.validation import validate_dossier

EXAMPLES = SCHEMAS.parent / "examples"


class ContractTests(unittest.TestCase):
    def test_all_schemas_compile_offline(self):
        for path in SCHEMAS.glob("*.schema.json"):
            with self.subTest(schema=path.name):
                Draft202012Validator.check_schema(load(path))

    def test_timestamp_and_uri_formats_always_enforced_without_optional_extras(self):
        for invalid in (
            "not a time",
            "2026-10-14T10:00:00",
            "2026-10-14T10:00:00+00:60",
            "9999-12-31T23:59:59-23:59",
        ):
            data = dossier()
            data["analysis_at"] = invalid
            self.assertIn("schema:analysis_at", schema_errors(data, "dossier"))
        for invalid in (
            "not a uri",
            "https://",
            "https://user:password@example.test/proof",
            "https://example.test/%ZZ",
        ):
            data = dossier()
            data["identity"]["proof"]["uri"] = invalid
            self.assertIn("schema:identity/proof", schema_errors(data, "dossier"))

    def test_committed_valid_example_is_synthetic_and_valid_at_test_clock_only(self):
        data = load(EXAMPLES / "dossier-synthetic-valid.json")
        report = validate_dossier(data, mode="synthetic_test", _clock=lambda: NOW)
        self.assertEqual(report["status"], "validated")
        self.assertEqual(report, load(EXAMPLES / "validation-synthetic-valid.json"))
        self.assertEqual(data["data_origin"], "synthetic")

    def test_committed_blocked_example_and_expected_report(self):
        data = load(EXAMPLES / "dossier-synthetic-blocked.json")
        report = validate_dossier(data, mode="synthetic_test", _clock=lambda: NOW)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report, load(EXAMPLES / "validation-synthetic-blocked.json"))

    def test_saved_prediction_and_outcome_schema_hash_links(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "journal.jsonl"
            records = [
                load(EXAMPLES / file)
                for file in ("prediction-synthetic.json", "outcome-synthetic.json")
            ]
            journal.write_text("".join(json.dumps(record) + "\n" for record in records))
            registry = Registry(directory, mode="synthetic_test")
            self.assertEqual(registry.verify()["count"], 2)
            self.assertEqual(records[1]["data"]["evaluation"]["status"], "winning")

    def test_cli_defaults_real_only_and_does_not_echo_raw_input(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["validate", str(EXAMPLES / "dossier-synthetic-valid.json")])
        self.assertEqual(code, 2)
        result = json.loads(output.getvalue())
        self.assertIn("synthetic_not_allowed", result["reasons"])
        self.assertNotIn("Test Club A", output.getvalue())

    def test_cli_has_no_clock_override(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["--now", "2026-10-14T10:00:00Z", "validate", "unused.json"])

    def test_cli_invalid_json_is_sanitized(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "bad.json"
            file.write_text('{"sensitive-placeholder":')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["validate", str(file)]), 2)
            self.assertNotIn("sensitive-placeholder", output.getvalue())
            self.assertIn("invalid_json", output.getvalue())
