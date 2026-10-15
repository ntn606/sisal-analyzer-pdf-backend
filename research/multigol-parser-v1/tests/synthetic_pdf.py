"""Explicitly SYNTHETIC PDF documents. No real fixture, price or provider ID.

The PDF is generated via pypdf using Helvetica and physical grid lines. Tests
exercise pdfplumber on real PDF bytes, not a mock accepting arbitrary columns.
"""

import io

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject


def identity(**updates):
    value = {
        "palinsesto": "99001",
        "avvenimento": "101",
        "competition_code": "SYN1",
        "home": "Demo Club",
        "away": "Other Club",
        "match_date": "2026-10-17",
        "local_time": "20:00",
    }
    value.update(updates)
    return value


def make_pdf(
    *,
    ranges=((1, 2), (2, 4), (3, 6)),
    prices=None,
    events=None,
    title="CALCIO MULTIGOAL PER DATA",
    shift=0,
    bad_altro=False,
    wrong_upper=False,
    grid=True,
    body_grid=True,
    body_shift=0,
    publisher="15/10/2026 - ore 22:00:00",
):
    writer = PdfWriter()
    page = writer.add_blank_page(842, 595)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    commands = []

    def text(value, x, top, size=6):
        escaped = (
            str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        )
        commands.append(
            f"BT /F1 {size} Tf 1 0 0 1 {x + shift:.4f} {595 - top - size:.4f} Tm ({escaped}) Tj ET"
        )

    def line(x0, y0, x1, y1):
        if grid:
            commands.append(f"{x0 + shift} {595 - y0} m {x1 + shift} {595 - y1} l S")

    bounds = [15, 45, 85, 125, 165, 265, 365] + [
        365 + 40 * i for i in range(1, 2 * len(ranges) + 1)
    ]
    text(title, 180, 40, 10)
    labels = ["Ora", "Manif.", "Pal.", "Avv.", "Squadra 1", "Squadra 2"]
    for n, (low, high) in enumerate(ranges):
        labels += [f"{low}-{high}", "Over" if bad_altro and n == 0 else "Altro"]
        text(
            "9 - 9" if wrong_upper and n == 0 else f"{low} - {high}",
            bounds[6 + 2 * n] + 25,
            66,
        )
    for n, label in enumerate(labels):
        text(label, bounds[n] + 2, 77)
    for x in bounds:
        line(x, 75, x, 85)
    for x in (bounds[0], bounds[6], bounds[-1]):
        line(x, 55, x, 85)
    line(bounds[0], 55, bounds[-1], 55)
    line(bounds[6], 65, bounds[-1], 65)
    line(bounds[0], 75, bounds[-1], 75)
    line(bounds[0], 85, bounds[-1], 85)
    text("sabato, 17 ottobre", 20, 88, 7)
    line(bounds[0], 97, bounds[-1], 97)
    events = events or [identity()]
    for row_number, event in enumerate(events):
        top = 97 + 12 * row_number
        if body_grid:
            for x in bounds:
                line(x + body_shift, top, x + body_shift, top + 12)
        values = [
            event["local_time"].replace(":", "."),
            event["competition_code"],
            event["palinsesto"],
            event["avvenimento"],
            event["home"],
            event["away"],
        ]
        current_prices = event.get("prices", prices)
        if current_prices is None:
            current_prices = ["2,10", "1,70"] * len(ranges)
        values += current_prices
        for n, value in enumerate(values):
            if value is not None:
                text(value, bounds[n] + 2, top + 3)
        line(bounds[0], top + 12, bounds[-1], top + 12)
    if publisher:
        text("Dati aggiornati al " + publisher, 450, 572, 7)
    stream = DecodedStreamObject()
    stream.set_data("\n".join(commands).encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
