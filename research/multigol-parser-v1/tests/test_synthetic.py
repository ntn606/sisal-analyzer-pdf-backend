"""Every document in this file is SYNTHETIC; full PDF extraction runs offline."""

import copy
import hashlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from pypdf import PdfReader, PdfWriter

from multigol_parser import parse_snapshot
from multigol_parser.common import Blocked
from multigol_parser.parser import extract_pages, parse_pages
from synthetic_pdf import identity, make_pdf


class SyntheticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def parse(
        self, data=None, expected=None, manifest_updates=None, mode="synthetic_test"
    ):
        data = data if data is not None else make_pdf()
        self.pdf = self.root / "synthetic.pdf"
        self.provenance = self.root / "synthetic.json"
        self.pdf.write_bytes(data)
        manifest = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "source_url": "urn:synthetic:test",
            "retrieved_at": "2026-10-15T20:30:00Z",
            "data_origin": "synthetic",
        }
        manifest.update(manifest_updates or {})
        self.provenance.write_text(json.dumps(manifest))
        return parse_snapshot(
            self.pdf,
            self.provenance,
            expected or identity(),
            mode=mode,
            _clock=lambda: datetime(2026, 10, 16, tzinfo=timezone.utc),
        )

    def blocked(self, report, reason):
        self.assertEqual(report["status"], "blocked", report["reasons"])
        self.assertEqual(report["reasons"], [reason])
        self.assertEqual(report["selections"], [])

    def test_synthetic_pdf_pair_values_and_origin(self):
        report = self.parse()
        self.assertEqual(report["status"], "parsed")
        self.assertEqual(report["source"]["data_origin"], "synthetic")
        self.assertEqual(
            [
                (s["range_min"], s["range_max"], s["selection"], s["decimal_original"])
                for s in report["selections"]
            ],
            [
                (a, b, outcome, price)
                for a, b in ((1, 2), (2, 4), (3, 6))
                for outcome, price in (("range", "2,10"), ("altro", "1,70"))
            ],
        )

    def test_empty_range_does_not_shift_altro_or_next_market(self):
        report = self.parse(
            make_pdf(prices=[None, "7,50", "1,52", "2,05", "2,45", "1,38"])
        )
        self.assertEqual(report["status"], "partial")
        self.assertEqual(
            [s["decimal_original"] for s in report["selections"]],
            [None, "7,50", "1,52", "2,05", "2,45", "1,38"],
        )
        self.assertEqual(report["selections"][0]["reasons"], ["empty_cell"])

    def test_empty_altro_remains_null(self):
        report = self.parse(
            make_pdf(prices=["12", None, "1,52", "2,05", "2,45", "1,38"])
        )
        self.assertEqual(report["selections"][0]["decimal"], "12")
        self.assertIsNone(report["selections"][1]["decimal"])
        self.assertEqual(report["selections"][1]["selection"], "altro")

    def test_unreadable_cell_is_blocked_without_interpolation(self):
        report = self.parse(
            make_pdf(prices=["??", "1,70", "1,52", "2,05", "2,45", "1,38"])
        )
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["selections"][0]["status"], "blocked")
        self.assertEqual(report["selections"][0]["raw_cell_text"], "??")
        self.assertIsNone(report["selections"][0]["decimal"])
        self.assertEqual(report["selections"][1]["decimal"], "1.70")

    def test_two_tokens_in_one_cell_not_a_single_price(self):
        report = self.parse(
            make_pdf(prices=["2,10 3,10", "1,70", "1,52", "2,05", "2,45", "1,38"])
        )
        self.assertEqual(
            report["selections"][0]["reasons"], ["multiple_tokens_in_cell"]
        )
        self.assertIsNone(report["selections"][0]["decimal"])

    def test_invalid_odds_zero_and_one_not_used(self):
        for value in ("0", "1,00", "-2"):
            with self.subTest(value=value):
                report = self.parse(
                    make_pdf(prices=[value, "1,70", "1,52", "2,05", "2,45", "1,38"])
                )
                self.assertIsNone(report["selections"][0]["decimal"])

    def test_range_column_reordering_read_from_headers(self):
        report = self.parse(
            make_pdf(
                ranges=((3, 6), (1, 2), (2, 4)),
                prices=["5", "1,10", "2", "1,60", "3", "1,20"],
            )
        )
        self.assertEqual(
            [
                (s["range_min"], s["range_max"], s["decimal"])
                for s in report["selections"][::2]
            ],
            [(3, 6, "5"), (1, 2, "2"), (2, 4, "3")],
        )

    def test_unpublished_ranges_are_not_invented(self):
        report = self.parse(make_pdf(ranges=((2, 4),), prices=["1,52", "2,05"]))
        self.assertEqual(report["status"], "parsed")
        self.assertEqual(
            [(s["range_min"], s["range_max"]) for s in report["selections"]],
            [(2, 4), (2, 4)],
        )

    def test_shifted_grid_and_header_no_fixed_x_coordinates(self):
        original = self.parse()
        shifted = self.parse(make_pdf(shift=15))
        self.assertEqual(shifted["status"], "parsed")
        self.assertEqual(
            [s["decimal"] for s in original["selections"]],
            [s["decimal"] for s in shifted["selections"]],
        )
        self.assertAlmostEqual(
            shifted["selections"][0]["cell_bbox"][0]
            - original["selections"][0]["cell_bbox"][0],
            15,
        )

    def test_replaced_altro_header_blocks_mapping(self):
        self.blocked(
            self.parse(make_pdf(bad_altro=True)), "range_altro_pairing_invalid"
        )

    def test_header_tiers_must_agree(self):
        self.blocked(self.parse(make_pdf(wrong_upper=True)), "header_tiers_disagree")

    def test_unknown_title_and_manifestation_variant_blocked(self):
        for title in ("CALCIO BASE", "CALCIO MULTIGOAL PER MANIFESTAZIONE"):
            self.blocked(
                self.parse(make_pdf(title=title)), "document_layout_unrecognized"
            )

    def multipage(self, *pages):
        writer = PdfWriter()
        for data in pages:
            writer.add_page(PdfReader(io.BytesIO(data)).pages[0])
        buffer = io.BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    def test_every_page_header_is_checked_before_releasing_target(self):
        data = self.multipage(
            make_pdf(),
            make_pdf(title="CALCIO BASE", events=[identity(avvenimento="202")]),
        )
        self.blocked(self.parse(data), "document_layout_unrecognized")

    def test_different_page_geometry_and_column_order_are_recognized_separately(self):
        data = self.multipage(
            make_pdf(),
            make_pdf(
                shift=15, ranges=((3, 6), (2, 4)), events=[identity(avvenimento="202")]
            ),
        )
        report = self.parse(data, expected=identity(avvenimento="202"))
        self.assertEqual(report["status"], "parsed")
        self.assertEqual(report["event"]["page"], 2)
        self.assertEqual(
            [(s["range_min"], s["range_max"]) for s in report["selections"]],
            [(3, 6), (3, 6), (2, 4), (2, 4)],
        )
        self.assertNotEqual(
            report["layouts"][0]["layout_sha256"], report["layouts"][1]["layout_sha256"]
        )

    def test_conflicting_publisher_timestamps_block_whole_document(self):
        data = self.multipage(
            make_pdf(), make_pdf(publisher="15/10/2026 - ore 22:01:00")
        )
        self.blocked(self.parse(data), "publisher_timestamps_conflict")

    def test_price_crossing_cell_boundary_is_not_assigned_to_nearest_column(self):
        report = self.parse(
            make_pdf(
                prices=["22222222222222222", "1,70", "1,52", "2,05", "2,45", "1,38"]
            )
        )
        self.assertEqual(report["status"], "partial")
        self.assertIsNone(report["selections"][0]["decimal"])
        self.assertIsNone(report["selections"][1]["decimal"])
        self.assertEqual(report["selections"][0]["reasons"], ["cell_boundary_overlap"])

    def test_scanned_or_textless_pdf_does_not_claim_parsing_success(self):
        writer = PdfWriter()
        writer.add_blank_page(842, 595)
        buffer = io.BytesIO()
        writer.write(buffer)
        self.blocked(
            self.parse(buffer.getvalue()), "publisher_timestamp_missing_or_ambiguous"
        )

    def test_team_market_never_inherits_match_odds(self):
        for title in (
            "CALCIO MULTIGOAL SQUADRA CASA",
            "CALCIO MULTIGOAL SQUADRA OSPITE",
        ):
            self.blocked(
                self.parse(make_pdf(title=title)), "team_market_layout_unsupported"
            )

    def test_grid_missing_cannot_use_sequence_of_numbers(self):
        self.blocked(self.parse(make_pdf(grid=False)), "header_grid_missing")

    def test_body_grid_must_agree_with_header_not_just_numeric_values(self):
        for settings in ({"body_grid": False}, {"body_shift": 3}):
            with self.subTest(settings=settings):
                self.blocked(
                    self.parse(make_pdf(**settings)),
                    "body_columns_disagree_with_header",
                )

    def test_event_key_missing_no_name_fallback(self):
        self.blocked(
            self.parse(expected=identity(avvenimento="999")), "event_not_found"
        )

    def test_names_swapped_wrong_date_time_or_competition(self):
        for values in (
            {"home": "Other Club", "away": "Demo Club"},
            {"competition_code": "EUUYL"},
            {"match_date": "2026-10-18"},
            {"local_time": "21:00"},
        ):
            with self.subTest(values=values):
                self.blocked(
                    self.parse(expected=identity(**values)), "printed_identity_mismatch"
                )

    def test_similar_names_and_youth_women_do_not_alias(self):
        for name in ("Demo Club U19", "Demo Club Women", "Demo Club B", "Demo Club FC"):
            row = identity(home=name)
            self.blocked(
                self.parse(make_pdf(events=[row])), "printed_identity_mismatch"
            )

    def test_category_is_not_assumed_senior(self):
        report = self.parse()
        self.assertIsNone(report["event"]["category"])
        self.blocked(
            self.parse(expected=identity(category="men_senior")),
            "category_not_verifiable_from_this_layout",
        )

    def test_identical_printed_home_and_away_names_block_ambiguous_identity(self):
        self.blocked(
            self.parse(make_pdf(events=[identity(away="Demo Club")])),
            "printed_team_identity_ambiguous",
        )

    def test_identical_names_different_ids_never_selected_by_name(self):
        report = self.parse(make_pdf(events=[identity(avvenimento="202"), identity()]))
        self.assertEqual(report["event"]["avvenimento"], "101")

    def test_duplicate_and_conflicting_records(self):
        for prices, reason in (
            (None, "duplicate_event_key"),
            (["3,10", "1,70"] * 3, "conflicting_event_records"),
        ):
            row = identity()
            if prices is not None:
                row["prices"] = prices
            self.blocked(self.parse(make_pdf(events=[identity(), row])), reason)

    def test_missing_expected_identity_is_blocked(self):
        expected = identity()
        del expected["away"]
        self.blocked(self.parse(expected=expected), "expected_identity_incomplete")

    def test_corrupt_and_unrecognized_pdf(self):
        self.blocked(self.parse(b"not a PDF"), "pdf_unrecognized")
        self.blocked(self.parse(b"%PDF-1.7\ncorrupt"), "pdf_corrupt_or_encrypted")

    def test_unavailable_pdf_is_safe_error(self):
        report = parse_snapshot(
            self.root / "absent.pdf", self.root / "absent.json", identity()
        )
        self.blocked(report, "local_file_unavailable")

    def test_snapshot_hash_mismatch_blocks_before_coordinates(self):
        self.blocked(
            self.parse(manifest_updates={"sha256": "0" * 64}), "snapshot_hash_mismatch"
        )

    def test_mixed_snapshot_coordinates_blocked(self):
        pages = extract_pages(make_pdf())
        source = {"sha256": pages[0]["source_sha256"]}
        other = copy.deepcopy(pages[0])
        other["source_sha256"] = "0" * 64
        with self.assertRaisesRegex(Blocked, "mixed_snapshot_coordinates"):
            parse_pages([pages[0], other], source, identity())

    def test_unverified_or_future_acquisition_timestamp(self):
        for stamp, reason in (
            (None, "invalid_acquisition_timestamp"),
            ("2099-01-01T00:00:00Z", "acquisition_in_future"),
        ):
            self.blocked(self.parse(manifest_updates={"retrieved_at": stamp}), reason)

    def test_publisher_stamp_required_and_preserved_without_timezone_guess(self):
        self.blocked(
            self.parse(make_pdf(publisher=None)),
            "publisher_timestamp_missing_or_ambiguous",
        )
        report = self.parse()
        self.assertEqual(
            report["source"]["publisher_timestamp_text"], "15/10/2026 22:00:00"
        )
        self.assertIsNone(report["source"]["published_at_utc"])
        self.assertIsNone(report["event"]["kickoff_utc"])

    def test_synthetic_origin_rejected_by_default_real_only(self):
        self.blocked(self.parse(mode="real_only"), "synthetic_not_allowed")

    def test_forged_official_source_rejected(self):
        for url in (
            "http://landing.sisal.it/volantini/Scommesse_Sport/Quote/calcio%20multigoal%20per%20data.pdf",
            "https://landing.sisal.it.evil.test/file.pdf",
            "https://user:pass@landing.sisal.it/file.pdf",
        ):
            self.blocked(
                self.parse(
                    manifest_updates={"source_url": url, "data_origin": "archived_real"}
                ),
                "official_document_source_unverified",
            )

    def test_flags_and_altro_not_rewritten_as_over_under(self):
        report = self.parse()
        self.assertTrue(report["diagnostic_only"])
        self.assertFalse(report["ready_for_analysis"])
        self.assertFalse(report["ready_for_quant"])
        self.assertFalse(report["statistics_usable_in_production"])
        for selection in report["selections"]:
            self.assertEqual(selection["market_type"], "multigol_match")
            self.assertEqual(selection["scope"], "match")
            self.assertIsNone(selection["period"])
