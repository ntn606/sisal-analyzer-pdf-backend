"""ARCHIVED REAL snapshot, not live/current odds. No downloads in this suite.

90 prices/nulls manually transcribed from the original rendered PDF. Fixed
crop boxes are independent of parser output. Real snapshot hashes/timestamps
remain unchanged. The fixed test clock is an archive replay, not acquisition.
"""

import copy
import json
import unittest
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import pdfplumber

from multigol_parser import parse_snapshot

FIXTURES = Path(__file__).parent / "fixtures"
PDF = FIXTURES / "multigol-per-data-20261015.pdf"
PROVENANCE = FIXTURES / "multigol-per-data-20261015.provenance.json"
GOLDEN = json.loads((FIXTURES / "manual-cell-golden.json").read_text())
ARCHIVE_CLOCK = datetime(2026, 10, 16, tzinfo=timezone.utc)


@lru_cache(maxsize=3)
def parsed(index):
    return parse_snapshot(
        PDF,
        PROVENANCE,
        GOLDEN["events"][index]["identity"],
        _clock=lambda: ARCHIVE_CLOCK,
    )


class RealSnapshotTests(unittest.TestCase):
    def test_hash_and_acquisition_preserved_per_selection(self):
        provenance = json.loads(PROVENANCE.read_text())
        report = parsed(0)
        self.assertEqual(report["source"]["sha256"], GOLDEN["source_sha256"])
        self.assertEqual(report["source"]["retrieved_at"], provenance["retrieved_at"])
        self.assertEqual(
            report["source"]["publisher_timestamp_text"],
            GOLDEN["publisher_timestamp_text"],
        )
        self.assertEqual(report["source"]["data_origin"], "archived_real")
        for s in report["selections"]:
            self.assertEqual(s["source_sha256"], GOLDEN["source_sha256"])
            self.assertEqual(s["retrieved_at"], provenance["retrieved_at"])
            self.assertIsNone(s["published_at_utc"])

    def test_all_90_selections_match_manual_original_cell_transcription(self):
        for index, event in enumerate(GOLDEN["events"]):
            report = parsed(index)
            self.assertIn(report["status"], ("parsed", "partial"), report["reasons"])
            self.assertEqual(len(report["selections"]), 30)
            for actual, expected in zip(report["selections"], event["cells"]):
                with self.subTest(
                    event=event["identity"]["avvenimento"],
                    range=(expected["range_min"], expected["range_max"]),
                    selection=expected["selection"],
                ):
                    for key in (
                        "range_min",
                        "range_max",
                        "selection",
                        "decimal_original",
                    ):
                        self.assertEqual(actual[key], expected[key])
                    self.assertEqual(actual["page"], event["page"])
                    for a, b in zip(actual["cell_bbox"], expected["cell_bbox"]):
                        self.assertAlmostEqual(a, b, places=3)

    def test_fixed_crops_of_original_pdf_agree_with_manual_values_and_headers(self):
        with pdfplumber.open(PDF) as pdf:
            for event in GOLDEN["events"]:
                page = pdf.pages[event["page"] - 1]
                for cell in event["cells"]:
                    with self.subTest(
                        event=event["identity"]["avvenimento"], box=cell["cell_bbox"]
                    ):
                        original = page.crop(cell["cell_bbox"]).extract_text(
                            x_tolerance=1, y_tolerance=2
                        )
                        self.assertEqual(original or None, cell["decimal_original"])
                        # crop clips intersecting glyph boxes and can include
                        # a sliver of the upper "Da ..." tier as whole text.
                        # Only fully contained original glyphs belong here.
                        band = page.within_bbox(cell["band_bbox"]).extract_text()
                        self.assertEqual(
                            "".join(band.split()),
                            f"{cell['range_min']}-{cell['range_max']}",
                        )

    def test_real_missing_1_6_keeps_7_50_in_altro(self):
        cells = parsed(1)["selections"]
        self.assertEqual(
            (cells[8]["range_min"], cells[8]["range_max"], cells[8]["selection"]),
            (1, 6, "range"),
        )
        self.assertIsNone(cells[8]["decimal"])
        self.assertEqual(cells[9]["selection"], "altro")
        self.assertEqual(cells[9]["decimal_original"], "7,50")
        self.assertEqual(cells[10]["decimal_original"], "1,98")

    def test_real_empty_altro_keeps_integer_12_in_5_6(self):
        cells = parsed(0)["selections"]
        self.assertEqual(cells[-2]["decimal_original"], "12")
        self.assertIsNone(cells[-1]["decimal_original"])
        self.assertEqual(cells[-1]["reasons"], ["empty_cell"])

    def test_real_second_page_identity_and_date(self):
        report = parsed(2)
        self.assertEqual(report["status"], "parsed")
        self.assertEqual(report["event"]["page"], 2)
        self.assertEqual(report["event"]["home"], "Budoni")
        self.assertEqual(report["event"]["away"], "Ssd Albalonga")
        self.assertEqual(report["event"]["match_date"], "2026-10-18")
        self.assertFalse(report["event"]["date_resolution"]["year_explicit"])

    def test_real_named_teams_cannot_be_replaced_with_similar_names(self):
        expected = copy.deepcopy(GOLDEN["events"][0]["identity"])
        expected["home"] = "Club Omnisport De Meknes U19"
        report = parse_snapshot(PDF, PROVENANCE, expected, _clock=lambda: ARCHIVE_CLOCK)
        self.assertEqual(report["reasons"], ["printed_identity_mismatch"])
        self.assertEqual(report["selections"], [])
