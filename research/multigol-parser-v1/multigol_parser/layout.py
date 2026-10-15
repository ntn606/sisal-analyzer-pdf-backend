"""Recognize physical cells from the current page, never fixed price offsets."""

import re

from .common import Blocked, fingerprint

EPS = 0.25


def box(word):
    return [round(word[k], 4) for k in ("x0", "top", "x1", "bottom")]


def contained(word, bbox):
    return (
        word["x0"] >= bbox[0] - EPS
        and word["x1"] <= bbox[2] + EPS
        and word["top"] >= bbox[1] - EPS
        and word["bottom"] <= bbox[3] + EPS
    )


def join(words):
    return " ".join(w["text"] for w in sorted(words, key=lambda w: w["x0"]))


def collapse(numbers, tolerance=0.15):
    result = []
    for value in sorted(numbers):
        if not result or value - result[-1] > tolerance:
            result.append(value)
    return result


def recognize(page):
    words = page["words"]
    lines = page["lines"]
    if not words:
        raise Blocked("text_layer_missing")
    # A profile is recognized by its title and two agreeing header tiers.
    # Team-specific and manifestation variants never inherit match prices.
    title_rows = {}
    for word in words:
        if word["top"] < page["height"] / 4:
            title_rows.setdefault(round(word["top"]), []).append(word)
    titles = [join(row).upper() for row in title_rows.values()]
    if any(
        "MULTIGOAL" in title and any(s in title for s in ("SQUADRA", "CASA", "OSPITE"))
        for title in titles
    ):
        raise Blocked("team_market_layout_unsupported")
    if "CALCIO MULTIGOAL PER DATA" not in titles:
        raise Blocked("document_layout_unrecognized")
    anchors = [w for w in words if w["text"] == "Ora" and w["top"] < page["height"] / 3]
    if len(anchors) != 1:
        raise Blocked("header_ambiguous")
    anchor = anchors[0]
    if any(
        w["top"] < anchor["top"] - 1.5
        and w["text"].upper() in {"CASA", "OSPITE", "SQUADRA", "TEAM", "HOME", "AWAY"}
        for w in words
    ):
        raise Blocked("team_market_layout_unsupported")
    header_words = [w for w in words if abs(w["top"] - anchor["top"]) <= 1.5]
    middle = (anchor["top"] + anchor["bottom"]) / 2
    verticals = collapse(
        l["x0"]
        for l in lines
        if abs(l["x0"] - l["x1"]) < 0.1 and l["top"] <= middle <= l["bottom"]
    )
    horizontals = collapse(
        l["top"]
        for l in lines
        if abs(l["top"] - l["bottom"]) < 0.1
        and l["x0"] <= anchor["x0"]
        and l["x1"] >= max(w["x1"] for w in header_words) - EPS
    )
    above = [y for y in horizontals if y <= min(w["top"] for w in header_words)]
    below = [y for y in horizontals if y >= max(w["bottom"] for w in header_words)]
    if not above or not below or len(verticals) < 9:
        raise Blocked("header_grid_missing")
    top, bottom = max(above), min(below)
    header_boxes = [[a, top, b, bottom] for a, b in zip(verticals, verticals[1:])]
    labels = []
    for bbox in header_boxes:
        labels.append(
            re.sub(r"\s+", "", join(w for w in header_words if contained(w, bbox)))
        )
    if labels[:6] != ["Ora", "Manif.", "Pal.", "Avv.", "Squadra1", "Squadra2"]:
        raise Blocked("identity_columns_unrecognized")
    if (len(labels) - 6) % 2 or len(labels) == 6:
        raise Blocked("range_altro_pairing_invalid")
    # Every header glyph must belong to exactly one physical sub-cell.
    if any(sum(contained(w, b) for b in header_boxes) != 1 for w in header_words):
        raise Blocked("header_cell_overlap")
    markets, seen = [], set()
    for i in range(6, len(labels), 2):
        match = re.fullmatch(r"(\d{1,2})-(\d{1,2})", labels[i])
        if not match or labels[i + 1] != "Altro":
            raise Blocked("range_altro_pairing_invalid")
        low, high = map(int, match.groups())
        if low > high or high > 20 or (low, high) in seen:
            raise Blocked("range_header_invalid")
        seen.add((low, high))
        left, right = verticals[i], verticals[i + 2]
        # The immediately preceding grid row must explicitly repeat the range.
        upper_candidates = [
            line["top"]
            for line in lines
            if abs(line["top"] - line["bottom"]) < 0.1
            and line["top"] < top - EPS
            and line["x0"] <= left + 0.7
            and line["x1"] >= right - 0.7
        ]
        if not upper_candidates:
            raise Blocked("upper_band_missing")
        upper_top = max(upper_candidates)
        upper_bbox = [left, upper_top, right, top]
        upper = re.sub(r"\s+", "", join(w for w in words if contained(w, upper_bbox)))
        if upper != labels[i]:
            raise Blocked("header_tiers_disagree")
        for offset, outcome in ((0, "range"), (1, "altro")):
            index = i + offset
            markets.append(
                {
                    "range_min": low,
                    "range_max": high,
                    "selection": outcome,
                    "column_index": index,
                    "header_text": labels[index],
                    "header_bbox": header_boxes[index],
                    "band_bbox": upper_bbox,
                }
            )
    boundaries = collapse(
        l["top"]
        for l in lines
        if abs(l["top"] - l["bottom"]) < 0.1
        and l["x0"] <= verticals[0] + 0.7
        and l["x1"] >= verticals[-1] - 0.7
        and l["top"] >= bottom - EPS
    )
    if len(boundaries) < 2 or abs(boundaries[0] - bottom) > EPS:
        raise Blocked("body_grid_missing")
    result = {
        "profile": "sisal_multigol_per_data_paired_v1",
        "page": page["page"],
        "source_sha256": page["source_sha256"],
        "header_top": top,
        "header_bottom": bottom,
        "x_boundaries": verticals,
        "row_boundaries": boundaries,
        "markets": markets,
    }
    result["layout_sha256"] = fingerprint(result)
    return result
