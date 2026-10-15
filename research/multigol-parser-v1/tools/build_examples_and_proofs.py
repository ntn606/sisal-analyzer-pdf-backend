"""Read the archived original PDF; never fetch or regenerate source timestamps."""

import json
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from multigol_parser import parse_snapshot
from multigol_parser.common import load_json


def main():
    fixtures = ROOT / "tests" / "fixtures"
    pdf_path = fixtures / "multigol-per-data-20261015.pdf"
    provenance = fixtures / "multigol-per-data-20261015.provenance.json"
    golden = load_json(fixtures / "manual-cell-golden.json")
    examples = ROOT / "examples"
    proof = ROOT / "proof"
    examples.mkdir(exist_ok=True)
    proof.mkdir(exist_ok=True)
    audits = []
    for index, event in enumerate(golden["events"]):
        key = event["identity"]["avvenimento"]
        (examples / (key + ".identity.json")).write_text(
            json.dumps(event["identity"], indent=2) + "\n"
        )
        report = parse_snapshot(pdf_path, provenance, event["identity"])
        assert report["status"] in ("parsed", "partial"), report["reasons"]
        (examples / (key + ".output.json")).write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        )
        for actual, manual in zip(report["selections"], event["cells"]):
            assert actual["decimal_original"] == manual["decimal_original"]
            audits.append(
                {
                    "event_key": report["event"]["event_key"],
                    "page": actual["page"],
                    "range_min": actual["range_min"],
                    "range_max": actual["range_max"],
                    "selection": actual["selection"],
                    "cell_bbox": actual["cell_bbox"],
                    "manual_original": manual["decimal_original"],
                    "parsed_original": actual["decimal_original"],
                    "source_sha256": actual["source_sha256"],
                    "matches": True,
                }
            )
    mismatch = dict(golden["events"][0]["identity"], competition_code="EUUYL")
    blocked = parse_snapshot(pdf_path, provenance, mismatch)
    assert blocked["status"] == "blocked"
    (examples / "blocked-identity.output.json").write_text(
        json.dumps(blocked, indent=2) + "\n"
    )
    (proof / "90-cell-audit.json").write_text(
        json.dumps(
            {
                "data_origin": "archived_real",
                "source_sha256": golden["source_sha256"],
                "scope": "archived document cells, not current prices",
                "reviewer": golden["reviewer"],
                "cells": audits,
            },
            indent=2,
        )
        + "\n"
    )
    # Render original glyphs and table grid. Colored outlines identify cells;
    # no numbers, labels, missing prices or timestamps are drawn into the PDF.
    with pdfplumber.open(pdf_path) as pdf:
        for number, bottom in ((1, 144), (2, 122)):
            page = pdf.pages[number - 1]
            image = page.crop((13, 39, 829, bottom)).to_image(resolution=150)
            for event in golden["events"]:
                if event["page"] == number:
                    for cell in event["cells"]:
                        if (cell["range_min"], cell["range_max"]) in (
                            (1, 2),
                            (1, 6),
                            (2, 4),
                            (3, 6),
                            (5, 6),
                        ):
                            color = (
                                "#2674db" if cell["selection"] == "range" else "#dc7613"
                            )
                            image.draw_rect(
                                cell["cell_bbox"],
                                fill=None,
                                stroke=color,
                                stroke_width=1,
                            )
            image.save(proof / ("original-page-" + str(number) + ".png"))
    print("Archived real examples and 90-cell audit rendered from the same PDF hash")


if __name__ == "__main__":
    main()
