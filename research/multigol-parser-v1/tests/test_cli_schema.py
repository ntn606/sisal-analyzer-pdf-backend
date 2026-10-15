"""Schema and CLI checks, separated real snapshots and synthetic invalid input."""

import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from multigol_parser.__main__ import main
from multigol_parser.common import result_blocked
from test_real_snapshot import PDF, PROVENANCE, ARCHIVE_CLOCK, parsed

ROOT = Path(__file__).resolve().parent.parent


class ContractTests(unittest.TestCase):
    def test_output_schema_compiles_offline_and_examples_validate(self):
        schema = json.loads((ROOT / "schemas" / "output.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        for index in range(3):
            validator.validate(parsed(index))
        validator.validate(result_blocked("example_blocked"))
        for path in (ROOT / "examples").glob("*.output.json"):
            validator.validate(json.loads(path.read_text()))

    def test_real_cli_reads_saved_pdf_and_emits_json(self):
        stdout = io.StringIO()
        # Archive replay only; preserve original timestamps, use real parsing.
        with (
            contextlib.redirect_stdout(stdout),
            patch("multigol_parser.parser.utc_now", return_value=ARCHIVE_CLOCK),
        ):
            code = main(
                [
                    str(PDF),
                    "--provenance",
                    str(PROVENANCE),
                    "--identity",
                    str(ROOT / "examples" / "6028.identity.json"),
                ]
            )
        report = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["event"]["event_key"], "36421/6028")
        self.assertIsNone(report["selections"][8]["decimal"])
        self.assertEqual(report["selections"][9]["decimal_original"], "7,50")

    def test_missing_identity_cli_fails_without_raw_traceback(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(
                [
                    str(PDF),
                    "--provenance",
                    str(PROVENANCE),
                    "--identity",
                    "missing.json",
                ]
            )
        self.assertEqual(code, 2)
        self.assertEqual(
            json.loads(stdout.getvalue())["reasons"], ["local_file_unavailable"]
        )
        self.assertNotIn("Traceback", stdout.getvalue())
