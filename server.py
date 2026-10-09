import io
import os
import re
import pdfplumber
import threading
import time
from typing import Optional

from curl_cffi import requests
from pypdf import PdfReader
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings


BASE = "https://landing.sisal.it/volantini/Scommesse_Sport/Quote/"

SHEETS = {
    "base": "calcio%20base%20per%20data.pdf",
    "combinate": "calcio%20combinate.pdf",
    "extra": "calcio%20extra%20per%20data.pdf",
}

CACHE = {}
CACHE_LOCK = threading.Lock()

# Sisal aggiorna i fogli periodicamente.
# Manteniamo una copia pronta nel backend.
CACHE_TTL = 3600
REFRESH_INTERVAL = 1800


mcp = FastMCP(
    "Sisal Analyzer PDF",
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False
    ),
)


def pdf_url(sheet: str) -> str:
    if sheet not in SHEETS:
        raise ValueError(f"Foglio non supportato: {sheet}")

    return BASE + SHEETS[sheet]


def download_pdf(sheet: str):
    url = pdf_url(sheet)

    headers = {
        "Accept": (
            "application/pdf,application/octet-stream;"
            "q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
        "Referer": (
            "https://www.sisal.it/"
            "scommesse-matchpoint/foglio-quote"
        ),
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    last_error = None

    for attempt in range(2):
        try:
            request_url = url

            if attempt:
                request_url += f"?cb={int(time.time())}"

            response = requests.get(
                request_url,
                headers=headers,
                impersonate="chrome",
                timeout=20,
                allow_redirects=True,
            )

            response.raise_for_status()
            content = response.content

            if not content.startswith(b"%PDF"):
                raise RuntimeError(
                    "La risposta ricevuta non è un PDF valido."
                )

            reader = PdfReader(io.BytesIO(content))

            text = "\n".join(
                page.extract_text() or ""
                for page in reader.pages
            )

            if not text.strip():
                raise RuntimeError(
                    "PDF scaricato ma senza testo estraibile."
                )

            return text, content

        except Exception as error:
            last_error = error

            if attempt == 0:
                time.sleep(1)

    raise RuntimeError(
        f"Download Sisal fallito: {last_error}"
    )

def save_cache(sheet: str, text: str, pdf_bytes: bytes):
    with CACHE_LOCK:
        CACHE[sheet] = {
            "text": text,
            "pdf_bytes": pdf_bytes,
            "time": time.time(),
            "error": None,
        }

def save_error(sheet: str, error):
    with CACHE_LOCK:
        previous = CACHE.get(sheet, {})

        CACHE[sheet] = {
            "text": previous.get("text"),
            "time": previous.get("time"),
            "error": str(error),
        }


def refresh_sheet(sheet: str):
    try:
        text, pdf_bytes = download_pdf(sheet)
        save_cache(sheet, text, pdf_bytes)
        print(
            f"[SISAL] {sheet}: aggiornato "
            f"({len(text)} caratteri)",
            flush=True,
        )

    except Exception as error:
        save_error(sheet, error)

        print(
            f"[SISAL] {sheet}: ERRORE: {error}",
            flush=True,
        )


def refresh_all():
    threads = []

    for sheet in SHEETS:
        thread = threading.Thread(
            target=refresh_sheet,
            args=(sheet,),
            daemon=True,
        )

        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join(timeout=45)


def background_refresher():
    # Primo caricamento all'avvio.
    refresh_all()

    while True:
        time.sleep(REFRESH_INTERVAL)
        refresh_all()


def start_background_refresher():
    thread = threading.Thread(
        target=background_refresher,
        daemon=True,
    )
    thread.start()


def get_cached_text(sheet: str):
    with CACHE_LOCK:
        item = CACHE.get(sheet)

        if not item:
            return None

        return item.get("text")

def get_cached_pdf(sheet: str):
    with CACHE_LOCK:
        item = CACHE.get(sheet)

        if not item:
            return None

        return item.get("pdf_bytes")


def extract_positioned_text(sheet: str, palinsesto: str, avvenimento: str):
    """Diagnostica per parole, con coordinate reali del PDF."""
    pdf_bytes = get_cached_pdf(sheet)
    if not pdf_bytes:
        return []

    palinsesto = str(palinsesto).strip()
    avvenimento = str(avvenimento).strip()
    pair = re.compile(
        rf"(?<!\d){re.escape(palinsesto)}\s+{re.escape(avvenimento)}(?!\d)"
    )
    results = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            words = page.extract_words(
                x_tolerance=1,
                y_tolerance=2,
                keep_blank_chars=False,
                use_text_flow=False,
            )
            lines = {}
            for word in words:
                y_key = round(word["top"] / 3) * 3
                lines.setdefault(y_key, []).append(word)

            ordered_lines = []
            for y_key, line_words in sorted(lines.items()):
                line_words.sort(key=lambda w: w["x0"])
                joined = " ".join(w["text"] for w in line_words)
                ordered_lines.append((y_key, joined, line_words))

            for index, (y_key, joined, line_words) in enumerate(ordered_lines):
                if not pair.search(joined):
                    continue
                # Include also nearby lines, useful for reading column headers.
                nearby = []
                for other_y, other_text, other_words in ordered_lines[max(0, index - 14):index + 3]:
                    nearby.append({
                        "top": other_y,
                        "text": other_text,
                        "words": [
                            {"text": w["text"], "x0": round(w["x0"], 2),
                             "x1": round(w["x1"], 2), "top": round(w["top"], 2)}
                            for w in other_words
                        ],
                    })
                results.append({
                    "page": page_number,
                    "top": y_key,
                    "joined": joined,
                    "fragments": [
                        {"text": w["text"], "x0": round(w["x0"], 2),
                         "x1": round(w["x1"], 2), "top": round(w["top"], 2)}
                        for w in line_words
                    ],
                    "nearby_lines": nearby,
                })
                if len(results) >= 5:
                    return results
    return results



def cache_age(sheet: str):
    with CACHE_LOCK:
        item = CACHE.get(sheet)

        if not item or not item.get("time"):
            return None

        return round(
            time.time() - item["time"],
            1,
        )


def get_updated_timestamp(text: str):
    match = re.search(
        r"Dati aggiornati al\s+([^\n]+)",
        text,
        re.IGNORECASE,
    )

    if match:
        return match.group(1).strip()

    return None


def clean_lines(text: str):
    return [
        re.sub(r"\s+", " ", line).strip()
        for line in text.splitlines()
        if line.strip()
    ]


def extract_events(text: str):
    """
    Estrae gli eventi dal Foglio Quote Calcio Base.

    Struttura reale osservata nel testo pypdf:

    MANIFESTAZIONE+ORA PALINSESTO AVVENIMENTO
    NOME EVENTO QUOTA QUOTA ...

    Esempio:
    ECU222.30 36391 39662 Cd Alianza Cotopaxi
    Vinotinto Fc Ecuador 2,45 3,00 2,80 ...
    """

    lines = clean_lines(text)

    events = []
    seen = set()

    # In Sisal l'ora estratta dal PDF usa normalmente
    # il punto: 20.45, 22.30, 01.00 ecc.
    row_re = re.compile(
        r"^"
        r"(?P<manifestazione>.*?)"
        r"(?P<ora>(?:[01]?\d|2[0-3])[.:][0-5]\d)"
        r"\s+"
        r"(?P<palinsesto>\d{3,6})"
        r"\s+"
        r"(?P<avvenimento>\d{1,6})"
        r"\s+"
        r"(?P<body>.+)"
        r"$"
    )

    # La prima quota segna la fine del nome dell'evento.
    odds_re = re.compile(
        r"(?<!\d)"
        r"\d{1,3}[,.]\d{1,3}"
        r"(?!\d)"
    )

    for line in lines:

        match = row_re.match(line)

        if not match:
            continue

        body = match.group("body").strip()

        odds_match = odds_re.search(body)

        if not odds_match:
            continue

        event_name = body[
            :odds_match.start()
        ].strip()

        # Elimina eventuali spazi multipli.
        event_name = re.sub(
            r"\s+",
            " ",
            event_name,
        )

        # Deve esserci realmente del testo nel nome.
        if len(event_name) < 3:
            continue

        if not re.search(
            r"[A-Za-zÀ-ÿ]",
            event_name,
        ):
            continue

        palinsesto = match.group(
            "palinsesto"
        )

        avvenimento = match.group(
            "avvenimento"
        )

        key = (
            palinsesto,
            avvenimento,
        )

        if key in seen:
            continue

        seen.add(key)

        raw_time = match.group("ora")

        # Restituiamo l'orario nel formato più leggibile HH:MM.
        ora = raw_time.replace(".", ":")

        manifestazione = (
            match.group("manifestazione")
            .strip()
        )

        events.append(
            {
                "time": ora,
                "manifestazione": manifestazione,
                "match": event_name,
                "palinsesto": palinsesto,
                "avvenimento": avvenimento,
                "raw": line,
            }
        )

    return events


@mcp.tool()
def get_matches(
    query: Optional[str] = None,
    limit: int = 100,
):
    """
    Elenca gli eventi calcistici presenti nel Foglio Quote
    ufficiale Sisal "Calcio Base per Data".

    Restituisce ora, manifestazione, nome evento,
    Palinsesto e Avvenimento.
    """

    text = get_cached_text("base")

    if not text:
        return {
            "ok": False,
            "state": "source_not_ready",
            "count": 0,
            "matches": [],
        }

    events = extract_events(text)

    if query:
        q = query.casefold().strip()

        events = [
            event
            for event in events
            if (
                q in event["match"].casefold()
                or q in event[
                    "manifestazione"
                ].casefold()
                or q == event[
                    "palinsesto"
                ].casefold()
                or q == event[
                    "avvenimento"
                ].casefold()
            )
        ]

    limit = max(
        1,
        min(limit, 300),
    )

    return {
        "ok": True,
        "source": BASE + SHEETS["base"],
        "updated": get_updated_timestamp(text),
        "count": len(events),
        "matches": events[:limit],
    }
    
@mcp.tool()
def get_event_markets(
    palinsesto: str,
    avvenimento: str,
):
    """
    Diagnostica la struttura reale dei Fogli Quote
    attorno a uno specifico evento.

    Usa Palinsesto + Avvenimento come chiave.
    Restituisce le righe precedenti e successive
    separatamente, senza unirle o reinterpretarle.
    """

    palinsesto = str(palinsesto).strip()
    avvenimento = str(avvenimento).strip()

    result = {}

    for sheet in SHEETS:
        text = get_cached_text(sheet)

        if not text:
            result[sheet] = {
                "ok": False,
                "state": "source_not_ready",
                "hits": [],
            }
            continue

        lines = clean_lines(text)
        hits = []

        # Cerchiamo la coppia esatta Palinsesto + Avvenimento.
        pair_re = re.compile(
            rf"(?<!\d){re.escape(palinsesto)}"
            rf"\s+"
            rf"{re.escape(avvenimento)}(?!\d)"
        )

        for index, line in enumerate(lines):
            if not pair_re.search(line):
                continue

            # Contesto volutamente ampio:
            # ci serve per capire intestazioni, mercati
            # e disposizione reale delle quote nel PDF.
            start = max(0, index - 12)
            end = min(len(lines), index + 13)

            context = []

            for line_index in range(start, end):
                context.append(
                    {
                        "index": line_index,
                        "relative": line_index - index,
                        "is_event_line": line_index == index,
                        "text": lines[line_index],
                    }
                )

            hits.append(
                {
                    "event_line_index": index,
                    "event_line": line,
                    "context": context,
                }
            )

        result[sheet] = {
            "ok": True,
            "updated": get_updated_timestamp(text),
            "cache_age_seconds": cache_age(sheet),
            "source": pdf_url(sheet),
            "hit_count": len(hits),
            "hits": hits[:10],
        }

    return {
        "ok": True,
        "mode": "diagnostic_event_context",
        "palinsesto": palinsesto,
        "avvenimento": avvenimento,
        "sheets": result,
    }

@mcp.tool()
def debug_event_positions(
    palinsesto: str,
    avvenimento: str,
    sheet: str = "base",
):
    """
    Mostra testo e coordinate X/Y della riga
    di uno specifico evento nel PDF originale.
    """

    if sheet not in SHEETS:
        raise ValueError(
            "sheet deve essere base, "
            "combinate oppure extra"
        )

    rows = extract_positioned_text(
        sheet,
        palinsesto,
        avvenimento,
    )

    return {
        "ok": True,
        "mode": "position_diagnostic",
        "sheet": sheet,
        "palinsesto": str(palinsesto),
        "avvenimento": str(avvenimento),
        "row_count": len(rows),
        "rows": rows[:20],
    }
BASE_OUTCOME_SPECS = [
    ("Esito finale 1X2", "1"),
    ("Esito finale 1X2", "X"),
    ("Esito finale 1X2", "2"),
    ("1X2 Handicap", "1"),
    ("1X2 Handicap", "X"),
    ("1X2 Handicap", "2"),
    ("Doppia Chance", "1X"),
    ("Doppia Chance", "X2"),
    ("Doppia Chance", "12"),
    ("Under/Over 1,5", "Under"),
    ("Under/Over 1,5", "Over"),
    ("Under/Over 2,5", "Under"),
    ("Under/Over 2,5", "Over"),
    ("Under/Over 3,5", "Under"),
    ("Under/Over 3,5", "Over"),
    ("Goal/No Goal", "Goal"),
    ("Goal/No Goal", "No Goal"),
    ("Segna goal casa", "Si"),
    ("Segna goal casa", "No"),
    ("Segna goal ospite", "Si"),
    ("Segna goal ospite", "No"),
]

# L = indicatore LIVE; H = linea handicap, non quote.
BASE_HEADER_TOKENS = [
    "L", "1", "X", "2", "H", "1", "X", "2",
    "1X", "X2", "12", "U", "O", "U", "O", "U", "O",
    "G", "NG", "SI", "NO", "SI", "NO",
]

def _base_group_lines(words):
    lines = {}
    for word in words:
        top_key = round(float(word["top"]) / 3) * 3
        lines.setdefault(top_key, []).append(word)
    for line_words in lines.values():
        line_words.sort(key=lambda word: float(word["x0"]))
    return lines


def _base_column_anchors(words):
    """Legge le 21 posizioni della testata, rifiuta layout imprevisti."""
    for _, row in sorted(_base_group_lines(words).items()):
        tokens = [word["text"] for word in row]
        if not all(x in tokens for x in ("Ora", "Manif.", "Pal.", "Avv.")):
            continue
        labels = [word for word in row if float(word["x0"]) >= 245]
        if [word["text"] for word in labels] != BASE_HEADER_TOKENS:
            continue
        handicap = next(word for word in labels if word["text"] == "H")
        price_labels = [word for word in labels if word["text"] not in ("L", "H")]
        if len(price_labels) != len(BASE_OUTCOME_SPECS):
            continue
        anchors = [
            (float(w["x0"]) + float(w["x1"])) / 2
            for w in price_labels
        ]
        handicap_center = (float(handicap["x0"]) + float(handicap["x1"])) / 2
        return anchors, handicap_center
    return None, None


def _base_price(text):
    # Le quote del foglio Base possono essere decimali o intere.
    if not re.fullmatch(r"[1-9]\d{0,2}(?:,\d{1,3})?", text):
        return None
    price = float(text.replace(",", "."))
    if not (1.01 <= price <= 999):
        return None
    return price


def _base_find_event_rows(words, palinsesto, avvenimento):
    """Usa gli ID nelle colonne Pal./Avv. e la prossimita' verticale."""
    pals = [w for w in words if w["text"] == palinsesto and 52 <= w["x0"] <= 82]
    avvs = [w for w in words if w["text"] == avvenimento and 80 <= w["x0"] <= 109]
    results = []
    for pal in pals:
        for avv in avvs:
            if abs(float(pal["top"]) - float(avv["top"])) > 3:
                continue
            if not (float(avv["x0"]) > float(pal["x0"])):
                continue
            top = (float(pal["top"]) + float(avv["top"])) / 2
            row = [w for w in words if abs(float(w["top"]) - top) <= 3.5]
            row.sort(key=lambda w: float(w["x0"]))
            if any(w["text"] == palinsesto for w in row) and any(w["text"] == avvenimento for w in row):
                results.append(row)
    return results


def _base_parse_event_row(row, anchors, handicap_center):
    slots = [None] * len(BASE_OUTCOME_SPECS)
    errors = []
    handicap_line = None
    for word in row:
        x0, x1 = float(word["x0"]), float(word["x1"])
        center = (x0 + x1) / 2
        if center < 257:
            continue
        raw = word["text"]
        if abs(center - handicap_center) <= 4.5:
            # L'indicatore handicap puo' essere -1, 1, -2, ecc.
            handicap_line = raw
            continue
        price = _base_price(raw)
        if price is None:
            errors.append({"type": "unparsed_value", "text": raw, "x0": round(x0, 2)})
            continue
        index = min(range(len(anchors)), key=lambda i: abs(center - anchors[i]))
        if abs(center - anchors[index]) > 6.5:
            errors.append({"type": "unaligned_value", "text": raw, "x0": round(x0, 2)})
            continue
        if slots[index] is not None:
            errors.append({"type": "duplicate_cell", "text": raw, "slot": index})
            slots[index] = {"error": "duplicate_cell"}
            continue
        slots[index] = {
            "odd": raw,
            "decimal_odds": price,
            "x0": round(x0, 2),
            "x1": round(x1, 2),
        }
    groups = []
    by_market = {}
    for i, (market, outcome) in enumerate(BASE_OUTCOME_SPECS):
        if market not in by_market:
            by_market[market] = {"market": market, "selections": []}
            groups.append(by_market[market])
        slot = slots[i]
        by_market[market]["selections"].append({
            "outcome": outcome,
            "odd": slot.get("odd") if slot else None,
            "decimal_odds": slot.get("decimal_odds") if slot else None,
            "x0": slot.get("x0") if slot else None,
        })
    home = " ".join(w["text"] for w in row if 105 <= w["x0"] < 179).strip()
    away = " ".join(w["text"] for w in row if 179 <= w["x0"] < 250).strip()
    return {
        "home_printed": home or None,
        "away_printed": away or None,
        "handicap_line": handicap_line,
        "markets": groups,
        "priced_selections": sum(bool(slot and slot.get("odd")) for slot in slots),
        "missing_selections": sum(slot is None for slot in slots),
        "issues": errors,
    }


@mcp.tool()
def get_base_market_quotes(palinsesto: str, avvenimento: str):
    """Quote Calcio Base lette per coordinate, senza spostare colonne vuote.

    Le quote non pubblicate hanno valore null. Se il layout non corrisponde
    alla testata prevista o ci sono frammenti illeggibili, segnala un errore.
    """
    palinsesto = str(palinsesto).strip()
    avvenimento = str(avvenimento).strip()
    pdf_bytes = get_cached_pdf("base")
    if not pdf_bytes:
        return {"ok": False, "state": "source_not_ready"}
    candidates = []
    missing_header_pages = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            words = page.extract_words(
                x_tolerance=1, y_tolerance=2,
                keep_blank_chars=False, use_text_flow=False,
            )
            rows = _base_find_event_rows(words, palinsesto, avvenimento)
            if not rows:
                continue
            anchors, handicap_center = _base_column_anchors(words)
            if not anchors:
                missing_header_pages.append(page_no)
                continue
            for row in rows:
                entry = _base_parse_event_row(row, anchors, handicap_center)
                entry["page"] = page_no
                candidates.append(entry)
    if missing_header_pages:
        return {"ok": False, "state": "header_not_recognized", "pages": missing_header_pages}
    if not candidates:
        return {
            "ok": False,
            "state": "event_not_found",
            "palinsesto": palinsesto,
            "avvenimento": avvenimento,
        }
    if len(candidates) != 1:
        return {"ok": False, "state": "ambiguous_event", "candidate_count": len(candidates)}
    data = candidates[0]
    return {
        "ok": not bool(data["issues"]),
        "state": "ok" if not data["issues"] else "review_required",
        "sheet": "base",
        "palinsesto": palinsesto,
        "avvenimento": avvenimento,
        "source": pdf_url("base"),
        "updated": get_updated_timestamp(get_cached_text("base") or ""),
        "cache_age_seconds": cache_age("base"),
        **data,
    }

EXTRA_OUTCOME_SPECS = [
    ("Parziale/Finale", "1-1"),
    ("Parziale/Finale", "1-X"),
    ("Parziale/Finale", "1-2"),
    ("Parziale/Finale", "X-1"),
    ("Parziale/Finale", "X-X"),
    ("Parziale/Finale", "X-2"),
    ("Parziale/Finale", "2-1"),
    ("Parziale/Finale", "2-X"),
    ("Parziale/Finale", "2-2"),
    ("Somma goal finale", "0"),
    ("Somma goal finale", "1"),
    ("Somma goal finale", "2"),
    ("Somma goal finale", "3"),
    ("Somma goal finale", "4"),
    ("Somma goal finale", ">4"),
]


def _extra_column_anchors(words):
    """Usa solo intestazioni reali del PDF Extra, non coordinate fisse."""
    labels_expected = [outcome for _, outcome in EXTRA_OUTCOME_SPECS]
    for _, row in sorted(_base_group_lines(words).items()):
        tokens = [word["text"] for word in row]
        if not all(label in tokens for label in ("Ora", "Manif.", "Pal.", "Avv.")):
            continue
        labels = [word for word in row if float(word["x0"]) >= 263]
        if [word["text"] for word in labels] != labels_expected:
            continue
        return [(float(word["x0"]) + float(word["x1"])) / 2 for word in labels]
    return None


def _extra_parse_event_row(row, anchors):
    slots = [None] * len(EXTRA_OUTCOME_SPECS)
    issues = []
    for word in row:
        x0, x1 = float(word["x0"]), float(word["x1"])
        center = (x0 + x1) / 2
        if center < 265:
            continue
        raw = str(word["text"])
        price = _base_price(raw)
        if price is None:
            issues.append({"type": "unparsed_value", "text": raw, "x0": round(x0, 2)})
            continue
        distances = [abs(center - anchor) for anchor in anchors]
        index = distances.index(min(distances))
        if distances[index] > 8:
            issues.append({"type": "unaligned_value", "text": raw, "x0": round(x0, 2)})
            continue
        if slots[index] is not None:
            issues.append({"type": "duplicate_cell", "text": raw, "slot": index})
            slots[index] = {"error": "duplicate_cell"}
            continue
        slots[index] = {
            "odd": raw,
            "decimal_odds": price,
            "x0": round(x0, 2),
        }

    markets = []
    by_market = {}
    for index, (market, outcome) in enumerate(EXTRA_OUTCOME_SPECS):
        if market not in by_market:
            group = {"market": market, "selections": []}
            by_market[market] = group
            markets.append(group)
        slot = slots[index]
        by_market[market]["selections"].append({
            "outcome": outcome,
            "odd": slot.get("odd") if slot else None,
            "decimal_odds": slot.get("decimal_odds") if slot else None,
            "x0": slot.get("x0") if slot else None,
        })

    priced = sum(bool(slot and slot.get("odd")) for slot in slots)
    return {
        "home_printed": " ".join(w["text"] for w in row if 105 <= w["x0"] < 187).strip() or None,
        "away_printed": " ".join(w["text"] for w in row if 187 <= w["x0"] < 265).strip() or None,
        "markets": markets,
        "priced_selections": priced,
        "missing_selections": sum(slot is None for slot in slots),
        "issues": issues,
    }


@mcp.tool()
def get_extra_market_quotes(palinsesto: str, avvenimento: str):
    """Legge Parziale/Finale e Somma goal finale dal PDF Sisal Extra.

    Ogni quota viene associata alla propria colonna X/Y. Le selezioni senza
    quota restano null e i valori ambigui richiedono revisione.
    """
    palinsesto = str(palinsesto).strip()
    avvenimento = str(avvenimento).strip()
    pdf_bytes = get_cached_pdf("extra")
    if not pdf_bytes:
        return {"ok": False, "state": "source_not_ready", "sheet": "extra"}

    candidates = []
    missing_header_pages = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            words = page.extract_words(
                x_tolerance=1, y_tolerance=2,
                keep_blank_chars=False, use_text_flow=False,
            )
            rows = _base_find_event_rows(words, palinsesto, avvenimento)
            if not rows:
                continue
            anchors = _extra_column_anchors(words)
            if not anchors:
                missing_header_pages.append(page_no)
                continue
            for row in rows:
                entry = _extra_parse_event_row(row, anchors)
                entry["page"] = page_no
                candidates.append(entry)

    if missing_header_pages:
        return {"ok": False, "state": "header_not_recognized", "pages": missing_header_pages}
    if not candidates:
        return {
            "ok": False, "state": "event_not_found", "sheet": "extra",
            "palinsesto": palinsesto, "avvenimento": avvenimento,
        }
    if len(candidates) != 1:
        return {
            "ok": False, "state": "ambiguous_event", "sheet": "extra",
            "candidate_count": len(candidates),
        }

    data = candidates[0]
    if data["issues"]:
        state = "review_required"
    elif not data["priced_selections"]:
        state = "no_quoted_selections"
    else:
        state = "ok"
    return {
        "ok": state == "ok",
        "state": state,
        "sheet": "extra",
        "palinsesto": palinsesto,
        "avvenimento": avvenimento,
        "source": pdf_url("extra"),
        "updated": get_updated_timestamp(get_cached_text("extra") or ""),
        "cache_age_seconds": cache_age("extra"),
        **data,
    }

def _comb_build_specs():
    """Crea 50 colonne nell'ordine effettivo del Foglio Combinate."""
    specs = []
    for goal_limit in ("1,5", "2,5", "3,5", "4,5"):
        market = f"1X2 finale + Under/Over {goal_limit}"
        for result in ("1", "X", "2"):
            for total in ("Under", "Over"):
                specs.append((market, f"{result} + {total}"))

    for market in (
        "1X2 finale + Goal/No Goal",
        "1X2 1T + Goal/No Goal 1T",
    ):
        for result in ("1", "X", "2"):
            for goals in ("Goal", "No Goal"):
                specs.append((market, f"{result} + {goals}"))

    market = "1X2 1T + Under/Over 1,5 1T"
    for result in ("1", "X", "2"):
        for total in ("Under", "Over"):
            specs.append((market, f"{result} + {total}"))

    # Dalla doppia riga della testata PDF: in basso NG/G (1T),
    # in alto NG/G/G/NG (2T). L'ordine NON e' NG,G,NG,G.
    market = "Goal/No Goal 1T + 2T"
    specs.extend([
        (market, "1T No Goal + 2T No Goal"),
        (market, "1T No Goal + 2T Goal"),
        (market, "1T Goal + 2T Goal"),
        (market, "1T Goal + 2T No Goal"),
    ])

    market = "Goal/No Goal finale + Under/Over 2,5"
    specs.extend([
        (market, "Goal + Under"),
        (market, "Goal + Over"),
        (market, "No Goal + Under"),
        (market, "No Goal + Over"),
    ])
    return specs


COMB_OUTCOME_SPECS = _comb_build_specs()

# Queste due righe sono state lette con pdfplumber sul PDF originale.
# I valori sono etichette della testata, non quote della partita.
COMB_HEADER_BOTTOM = (
    ["U", "O"] * 12
    + ["G", "NG"] * 6
    + ["U", "O"] * 3
    + ["NG", "G"]
    + ["U", "O"] * 2
)
COMB_HEADER_TOP = (
    ["1", "X", "2"] * 7
    + ["NG", "G", "G", "NG", "G", "NG"]
)


def _comb_column_anchors(words):
    """Legge le 50 coordinate dalla testata reale di ogni pagina.

    Le quattro colonne 'G/NG 1T + 2T' compaiono nella riga
    superiore: non vanno ricavate per interpolazione geometrica.
    Se cambia la testata, falliamo esplicitamente anziche' inventare quote.
    """
    upper = None
    lower = None
    has_market_names = False
    for _, line in sorted(_base_group_lines(words).items()):
        labels = [w for w in line if float(w["x0"]) >= 260]
        tokens = [str(w["text"]) for w in labels]
        if tokens == COMB_HEADER_TOP:
            upper = labels
        elif tokens == COMB_HEADER_BOTTOM:
            # La riga inferiore comprende anche Ora/Manif./Pal./Avv.
            # che sono a sinistra di X=260 e quindi non compaiono qui.
            lower = labels
        elif (
            "1X2" in tokens and "Finale" in tokens
            and "G/NG" in tokens and "U/O2,5" in tokens
        ):
            has_market_names = True

    if upper is None or lower is None or not has_market_names:
        return None

    # Prime 42 colonne: 4*(1X2+U/O) + 2*(1X2+G/NG) + (1X2+U/O 1T).
    # Quattro colonne centrali: G/NG 1T+2T, visibili sulla testata superiore.
    # Ultime quattro colonne: G/NG finale+U/O2,5.
    cells = lower[:42] + upper[21:25] + lower[44:]
    if len(cells) != len(COMB_OUTCOME_SPECS):
        return None
    anchors = [
        (float(word["x0"]) + float(word["x1"])) / 2
        for word in cells
    ]
    if any(b <= a for a, b in zip(anchors, anchors[1:])):
        return None
    return anchors


def _comb_parse_event_row(row, anchors):
    slots = [None] * len(COMB_OUTCOME_SPECS)
    issues = []
    for word in row:
        x0 = float(word["x0"])
        x1 = float(word["x1"])
        center = (x0 + x1) / 2
        if center < 265:
            continue

        raw = str(word["text"])
        price = _base_price(raw)
        if price is None:
            issues.append({
                "type": "unparsed_value", "text": raw, "x0": round(x0, 2),
            })
            continue
        differences = [abs(center - x) for x in anchors]
        slot_index = differences.index(min(differences))
        if differences[slot_index] > 7.0:
            issues.append({
                "type": "unaligned_value", "text": raw, "x0": round(x0, 2),
            })
            continue
        if slots[slot_index] is not None:
            issues.append({
                "type": "duplicate_cell", "text": raw, "slot": slot_index,
            })
            slots[slot_index] = {"error": "duplicate_cell"}
            continue
        slots[slot_index] = {
            "odd": raw,
            "decimal_odds": price,
            "x0": round(x0, 2),
        }

    markets = []
    by_market = {}
    for i, (market, outcome) in enumerate(COMB_OUTCOME_SPECS):
        if market not in by_market:
            group = {"market": market, "selections": []}
            by_market[market] = group
            markets.append(group)
        slot = slots[i]
        by_market[market]["selections"].append({
            "outcome": outcome,
            "odd": slot.get("odd") if slot else None,
            "decimal_odds": slot.get("decimal_odds") if slot else None,
            "x0": slot.get("x0") if slot else None,
        })

    return {
        "home_printed": " ".join(
            w["text"] for w in row if 105 <= float(w["x0"]) < 187
        ).strip() or None,
        "away_printed": " ".join(
            w["text"] for w in row if 187 <= float(w["x0"]) < 265
        ).strip() or None,
        "markets": markets,
        "priced_selections": sum(bool(s and s.get("odd")) for s in slots),
        "missing_selections": sum(s is None for s in slots),
        "issues": issues,
    }


@mcp.tool()
def get_combinate_market_quotes(palinsesto: str, avvenimento: str):
    """Legge i 9 mercati Calcio Combinate mediante le coordinate PDF.

    Le celle assenti rimangono null. Un'intestazione diversa o una quota
    illeggibile produce un errore esplicito invece di una quota inventata.
    """
    palinsesto = str(palinsesto).strip()
    avvenimento = str(avvenimento).strip()
    pdf_bytes = get_cached_pdf("combinate")
    if not pdf_bytes:
        return {"ok": False, "state": "source_not_ready", "sheet": "combinate"}

    candidates = []
    missing_header_pages = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            words = page.extract_words(
                x_tolerance=1, y_tolerance=2,
                keep_blank_chars=False, use_text_flow=False,
            )
            rows = _base_find_event_rows(words, palinsesto, avvenimento)
            if not rows:
                continue
            anchors = _comb_column_anchors(words)
            if anchors is None:
                missing_header_pages.append(page_no)
                continue
            for row in rows:
                entry = _comb_parse_event_row(row, anchors)
                entry["page"] = page_no
                candidates.append(entry)

    if missing_header_pages:
        return {
            "ok": False, "state": "header_not_recognized",
            "sheet": "combinate", "pages": missing_header_pages,
        }
    if not candidates:
        return {
            "ok": False, "state": "event_not_found", "sheet": "combinate",
            "palinsesto": palinsesto, "avvenimento": avvenimento,
        }
    if len(candidates) != 1:
        return {
            "ok": False, "state": "ambiguous_event", "sheet": "combinate",
            "candidate_count": len(candidates),
        }

    data = candidates[0]
    if data["issues"]:
        state = "review_required"
    elif not data["priced_selections"]:
        state = "no_quoted_selections"
    else:
        state = "ok"

    # pypdf talvolta concatena il numero pagina al timestamp PDF.
    updated_raw = get_updated_timestamp(get_cached_text("combinate") or "") or ""
    timestamp_match = re.search(
        r"\d{2}/\d{2}/\d{4}\s*-\s*ore\s*\d{2}:\d{2}:\d{2}",
        updated_raw,
    )
    updated_clean = timestamp_match.group(0) if timestamp_match else updated_raw

    return {
        "ok": state == "ok", "state": state,
        "sheet": "combinate",
        "palinsesto": palinsesto, "avvenimento": avvenimento,
        "source": pdf_url("combinate"),
        "updated": updated_clean,
        "cache_age_seconds": cache_age("combinate"),
        **data,
    }

def _all_clean_pdf_timestamp(value):
    """Separa la data reale dal numero di pagina/pie' di pagina PDF."""
    match = re.search(
        r"\d{2}/\d{2}/\d{4}\s*-\s*ore\s*\d{2}:\d{2}:\d{2}",
        str(value or ""),
    )
    return match.group(0) if match else None


def _all_cache_versions():
    """Fotografa le versioni dei PDF per rilevare refresh durante la lettura."""
    with CACHE_LOCK:
        return {
            sheet: (CACHE.get(sheet) or {}).get("time")
            for sheet in ("base", "extra", "combinate")
        }


@mcp.tool()
def get_all_event_quotes(palinsesto: str, avvenimento: str):
    """Aggrega le quote Base, Extra e Combinate di uno stesso evento Sisal.

    Riporta lo stato distinto per foglio e tutte le selezioni, comprese quelle
    senza quota (null). 'verified' vale True soltanto per le quote prodotte
    da un parser in stato 'ok'. 'ready_for_agents' e' un controllo conservativo:
    richiede tre fogli validi, nessun problema e cache entro il TTL.
    Questo strumento NON valuta la convenienza di alcuna scommessa.
    """
    palinsesto = str(palinsesto).strip()
    avvenimento = str(avvenimento).strip()
    if not (
        re.fullmatch(r"\d{3,6}", palinsesto)
        and re.fullmatch(r"\d{1,6}", avvenimento)
    ):
        return {
            "ok": False,
            "state": "invalid_event_ids",
            "palinsesto": palinsesto,
            "avvenimento": avvenimento,
            "ready_for_agents": False,
            "sheets": {},
            "markets": [],
        }

    extractors = (
        ("base", get_base_market_quotes),
        ("extra", get_extra_market_quotes),
        ("combinate", get_combinate_market_quotes),
    )
    before_versions = _all_cache_versions()
    sources = {}
    markets = []
    issues = []
    verified_count = 0
    missing_count = 0
    total_quote_count = 0

    for sheet, extractor in extractors:
        try:
            output = extractor(palinsesto, avvenimento)
            if not isinstance(output, dict):
                raise TypeError("Il parser non ha restituito un oggetto")
        except Exception as exc:
            output = {
                "ok": False,
                "state": "parser_exception",
                "issues": [{"type": "parser_exception", "detail": str(exc)[:300]}],
            }

        sheet_state = str(output.get("state") or "unknown")
        verified_sheet = bool(output.get("ok") and sheet_state == "ok")
        sheet_issues = output.get("issues") or []
        if not isinstance(sheet_issues, list):
            sheet_issues = [{"type": "invalid_issue_format"}]
        for issue in sheet_issues:
            issues.append({"sheet": sheet, **(issue if isinstance(issue, dict) else {"detail": str(issue)})})

        raw_markets = output.get("markets") or []
        sheet_market_count = 0
        sheet_verified_count = 0
        sheet_missing_count = 0
        sheet_quoted_count = 0
        pdf_updated = _all_clean_pdf_timestamp(output.get("updated"))
        url = output.get("source") or pdf_url(sheet)

        for group in raw_markets:
            if not isinstance(group, dict):
                issues.append({"sheet": sheet, "type": "invalid_market_format"})
                continue
            sheet_market_count += 1
            selections = []
            for selection in group.get("selections") or []:
                if not isinstance(selection, dict):
                    issues.append({"sheet": sheet, "type": "invalid_selection_format"})
                    continue
                price = selection.get("decimal_odds")
                valid_price = (
                    isinstance(price, (int, float))
                    and not isinstance(price, bool)
                    and 1.01 <= price <= 999
                )
                if price is not None and not valid_price:
                    issues.append({
                        "sheet": sheet,
                        "type": "invalid_decimal_odds",
                        "market": group.get("market"),
                        "outcome": selection.get("outcome"),
                    })
                if valid_price:
                    sheet_quoted_count += 1
                else:
                    sheet_missing_count += 1
                selection_verified = verified_sheet and valid_price
                if selection_verified:
                    sheet_verified_count += 1
                selections.append({
                    "outcome": selection.get("outcome"),
                    "odd": selection.get("odd"),
                    "decimal_odds": price if valid_price else None,
                    "x0": selection.get("x0"),
                    "verified": selection_verified,
                })
            markets.append({
                "sheet": sheet,
                "market": group.get("market"),
                "source": url,
                "pdf_updated": pdf_updated,
                "page": output.get("page"),
                "verified": verified_sheet,
                "selections": selections,
            })

        sources[sheet] = {
            "ok": bool(output.get("ok")),
            "state": sheet_state,
            "source": url,
            "updated": pdf_updated,
            "cache_age_seconds": output.get("cache_age_seconds"),
            "page": output.get("page"),
            "home_printed": output.get("home_printed"),
            "away_printed": output.get("away_printed"),
            "handicap_line": output.get("handicap_line") if sheet == "base" else None,
            "market_count": sheet_market_count,
            "quoted_selections": sheet_quoted_count,
            "verified_selections": sheet_verified_count,
            "missing_selections": sheet_missing_count,
            "issues": sheet_issues,
        }
        verified_count += sheet_verified_count
        missing_count += sheet_missing_count
        total_quote_count += sheet_quoted_count

    warnings = []
    after_versions = _all_cache_versions()
    for sheet in sources:
        if before_versions[sheet] != after_versions[sheet]:
            warnings.append({"type": "cache_updated_during_read", "sheet": sheet})
        age = sources[sheet]["cache_age_seconds"]
        if sources[sheet]["state"] == "ok" and age is None:
            warnings.append({"type": "cache_age_unknown", "sheet": sheet})
        if age is not None and age > CACHE_TTL:
            warnings.append({"type": "stale_cache", "sheet": sheet, "age_seconds": age})
        if sources[sheet]["state"] == "ok" and sources[sheet]["updated"] is None:
            warnings.append({"type": "pdf_timestamp_unknown", "sheet": sheet})

    # Quote prelevate da PDF aggiornati in momenti lontani potrebbero non
    # descrivere lo stesso palinsesto. Per gli agenti richiediamo <=30 minuti.
    from datetime import datetime
    pdf_times = []
    for sheet, source in sources.items():
        if source["state"] == "ok" and source["updated"]:
            try:
                dt = datetime.strptime(source["updated"], "%d/%m/%Y - ore %H:%M:%S")
                pdf_times.append((sheet, dt))
            except ValueError:
                warnings.append({"type": "pdf_timestamp_invalid", "sheet": sheet})
    if len(pdf_times) > 1:
        span = (max(v for _, v in pdf_times) - min(v for _, v in pdf_times)).total_seconds()
        if span > 1800:
            warnings.append({
                "type": "pdf_timestamps_out_of_sync",
                "difference_seconds": round(span),
            })

    # Gli ID Sisal sono la chiave primaria. Conserviamo i nomi stampati per
    # rilevare discrepanze, senza sovrascrivere quelli di altri fogli.
    names = [
        (sheet, sources[sheet]["home_printed"], sources[sheet]["away_printed"])
        for sheet in sources if sources[sheet]["home_printed"] and sources[sheet]["away_printed"]
    ]
    if len({(str(h).casefold(), str(a).casefold()) for _, h, a in names}) > 1:
        warnings.append({"type": "printed_team_names_differ", "sheets": [s for s, _, _ in names]})

    states = [sources[s]["state"] for s, _ in extractors]
    acceptable_absence = {"event_not_found", "no_quoted_selections"}
    if all(state == "event_not_found" for state in states):
        state = "event_not_found"
    elif not verified_count and all(state in acceptable_absence for state in states):
        state = "no_quoted_selections"
    elif issues or warnings or any(
        state not in ("ok", "event_not_found", "no_quoted_selections")
        for state in states
    ):
        state = "review_required"
    elif all(state == "ok" for state in states):
        state = "ok"
    else:
        state = "partial"

    # Un foglio assente non impedisce l'ispezione umana delle quote esistenti,
    # ma solo lo stato pieno 'ok' e' pronto per l'ingestione automatica.
    ready_for_agents = state == "ok" and verified_count > 0
    return {
        "ok": state in ("ok", "partial"),
        "state": state,
        "palinsesto": palinsesto,
        "avvenimento": avvenimento,
        "ready_for_agents": ready_for_agents,
        "sheets": sources,
        "market_count": len(markets),
        "quoted_selections": total_quote_count,
        "verified_selections": verified_count,
        "missing_selections": missing_count,
        "issues": issues,
        "warnings": warnings,
        "markets": markets,
    }

SCOUT_MAX_PDF_AGE_MINUTES = 60
SCOUT_MAX_FUTURE_SECONDS = 120
SCOUT_TIMEZONE = "Europe/Rome"
SCOUT_SHEETS = ("base", "extra", "combinate")


def _scout_evaluate_aggregate(aggregate, now=None):
    """Scout V1: filtra quote tecnicamente leggibili, senza pronostici.

    Funzione separata dal tool per poter testare scenari artificiali.
    'now' e' un datetime aware usato unicamente dai test, non dall'MCP.
    Un errore globale produce SEMPRE mercati vuoti e ready_for_analysis=False.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    if now is None:
        now = datetime.now(ZoneInfo(SCOUT_TIMEZONE))
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Scout richiede un orario timezone-aware")
    now = now.astimezone(ZoneInfo(SCOUT_TIMEZONE))

    result = {
        "agent": "scout_v1",
        "ok": False,
        "state": "blocked",
        "ready_for_analysis": False,
        "palinsesto": str(aggregate.get("palinsesto", "")),
        "avvenimento": str(aggregate.get("avvenimento", "")),
        "event": None,
        "as_of": now.isoformat(timespec="seconds"),
        "max_pdf_age_minutes": SCOUT_MAX_PDF_AGE_MINUTES,
        "aggregate_state": aggregate.get("state"),
        "blockers": [],
        "sources": {},
        "market_count": 0,
        "candidate_count": 0,
        "skipped_missing_quote": 0,
        "skipped_invalid_quote": 0,
        "markets": [],
        "note": (
            "Controllo tecnico delle quote. Non stima probabilita', "
            "value bet o risultati sportivi; non autorizza scommesse."
        ),
    }
    blockers = result["blockers"]

    if aggregate.get("state") == "event_not_found":
        result["state"] = "event_not_found"
        blockers.append({"type": "event_not_found"})
        return result
    if aggregate.get("state") == "invalid_event_ids":
        result["state"] = "invalid_event_ids"
        blockers.append({"type": "invalid_event_ids"})
        return result
    if aggregate.get("state") != "ok" or not aggregate.get("ready_for_agents"):
        blockers.append({
            "type": "aggregate_not_ready",
            "state": aggregate.get("state"),
        })
    if aggregate.get("issues"):
        blockers.append({"type": "aggregate_issues", "count": len(aggregate["issues"])})
    if aggregate.get("warnings"):
        blockers.append({"type": "aggregate_warnings", "details": aggregate["warnings"]})

    sheets = aggregate.get("sheets")
    if not isinstance(sheets, dict):
        sheets = {}
        blockers.append({"type": "sources_missing"})

    names = []
    for sheet in SCOUT_SHEETS:
        source = sheets.get(sheet)
        if not isinstance(source, dict):
            blockers.append({"type": "sheet_missing", "sheet": sheet})
            continue

        state = source.get("state")
        if source.get("source") != pdf_url(sheet):
            blockers.append({"type": "unexpected_pdf_source", "sheet": sheet})
        if not source.get("ok") or state != "ok":
            blockers.append({"type": "sheet_not_ok", "sheet": sheet, "state": state})

        age = source.get("cache_age_seconds")
        if (
            not isinstance(age, (int, float)) or isinstance(age, bool)
            or age < 0 or age > CACHE_TTL
        ):
            blockers.append({"type": "invalid_or_stale_cache", "sheet": sheet, "age_seconds": age})

        updated = _all_clean_pdf_timestamp(source.get("updated"))
        pdf_age_minutes = None
        if updated is None:
            blockers.append({"type": "pdf_timestamp_missing", "sheet": sheet})
        else:
            try:
                printed = datetime.strptime(updated, "%d/%m/%Y - ore %H:%M:%S")
                # Timestamp del PDF in ora italiana; non e' una stringa UTC.
                printed = printed.replace(tzinfo=ZoneInfo(SCOUT_TIMEZONE))
                pdf_age_seconds = (now - printed).total_seconds()
                pdf_age_minutes = round(pdf_age_seconds / 60, 2)
                if pdf_age_seconds > 60 * SCOUT_MAX_PDF_AGE_MINUTES:
                    blockers.append({
                        "type": "pdf_too_old", "sheet": sheet,
                        "pdf_age_minutes": pdf_age_minutes,
                        "max_age_minutes": SCOUT_MAX_PDF_AGE_MINUTES,
                    })
                elif pdf_age_seconds < -SCOUT_MAX_FUTURE_SECONDS:
                    blockers.append({
                        "type": "pdf_timestamp_in_future", "sheet": sheet,
                        "pdf_age_minutes": pdf_age_minutes,
                    })
            except ValueError:
                blockers.append({"type": "pdf_timestamp_invalid", "sheet": sheet, "updated": updated})

        home = str(source.get("home_printed") or "").strip()
        away = str(source.get("away_printed") or "").strip()
        if not home or not away:
            blockers.append({"type": "team_names_missing", "sheet": sheet})
        else:
            names.append((sheet, home, away))

        result["sources"][sheet] = {
            "state": state,
            "source": source.get("source"),
            "pdf_updated": updated,
            "pdf_age_minutes": pdf_age_minutes,
            "cache_age_seconds": age,
            "quoted_selections": source.get("quoted_selections"),
            "missing_selections": source.get("missing_selections"),
        }

    normalized_names = {
        (" ".join(h.casefold().split()), " ".join(a.casefold().split()))
        for _, h, a in names
    }
    if len(normalized_names) > 1:
        blockers.append({"type": "team_names_mismatch", "sheets": [s for s, _, _ in names]})
    if names:
        _, home, away = names[0]
        result["event"] = {"home": home, "away": away}

    # Solo selezioni esplicitamente verificate, con numero e testo coerenti.
    # Se il PDF non e' fresco, si calcolano diagnostiche ma NON si espone
    # alcuna quota utilizzabile agli agenti a valle.
    seen = set()
    groups = []
    counts_by_sheet = {s: 0 for s in SCOUT_SHEETS}
    for group in aggregate.get("markets") or []:
        if not isinstance(group, dict):
            result["skipped_invalid_quote"] += 1
            blockers.append({"type": "invalid_market_format"})
            continue
        sheet = group.get("sheet")
        market = group.get("market")
        if sheet not in SCOUT_SHEETS or not isinstance(market, str) or not market.strip():
            blockers.append({"type": "invalid_market_identity"})
            continue
        key = (sheet, market)
        if key in seen:
            blockers.append({"type": "duplicate_market", "sheet": sheet, "market": market})
            continue
        seen.add(key)
        source = result["sources"].get(sheet)
        if source is None or group.get("source") != source.get("source"):
            blockers.append({"type": "market_source_mismatch", "sheet": sheet, "market": market})
            continue
        if _all_clean_pdf_timestamp(group.get("pdf_updated")) != source["pdf_updated"]:
            blockers.append({"type": "market_timestamp_mismatch", "sheet": sheet, "market": market})
            continue
        page = group.get("page")
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            blockers.append({"type": "market_page_invalid", "sheet": sheet, "market": market})
            continue
        selections = []
        local_seen = set()
        for item in group.get("selections") or []:
            if not isinstance(item, dict):
                result["skipped_invalid_quote"] += 1
                continue
            outcome = item.get("outcome")
            if not isinstance(outcome, str) or not outcome.strip() or outcome in local_seen:
                result["skipped_invalid_quote"] += 1
                blockers.append({"type": "invalid_or_duplicate_outcome", "sheet": sheet, "market": market})
                continue
            local_seen.add(outcome)
            value = item.get("decimal_odds")
            if value is None:
                result["skipped_missing_quote"] += 1
                continue
            raw = str(item.get("odd") or "")
            parsed = _base_price(raw)
            x0 = item.get("x0")
            valid = (
                bool(item.get("verified"))
                and isinstance(value, (int, float)) and not isinstance(value, bool)
                and parsed is not None and abs(float(value) - parsed) < 0.00001
                and isinstance(x0, (int, float)) and not isinstance(x0, bool)
                and 0 < x0 < 1000
            )
            if not valid:
                result["skipped_invalid_quote"] += 1
                blockers.append({"type": "unverified_or_invalid_quote", "sheet": sheet, "market": market, "outcome": outcome})
                continue
            selections.append({
                "outcome": outcome,
                "odd": raw,
                "decimal_odds": value,
                "x0": x0,
            })
            counts_by_sheet[sheet] += 1
        if selections:
            groups.append({
                "sheet": sheet,
                "market": market,
                "source": source["source"],
                "pdf_updated": source["pdf_updated"],
                "page": group.get("page"),
                "selections": selections,
            })

    # Riconcilia i conteggi per individuare troncamenti e output anomali.
    if sum(counts_by_sheet.values()) != aggregate.get("verified_selections"):
        blockers.append({
            "type": "verified_count_mismatch",
            "found": sum(counts_by_sheet.values()),
            "expected": aggregate.get("verified_selections"),
        })
    if sum(counts_by_sheet.values()) + result["skipped_missing_quote"] != (
        aggregate.get("verified_selections", 0) + aggregate.get("missing_selections", 0)
    ):
        blockers.append({"type": "selection_count_mismatch"})

    if blockers:
        # Quota sospetta/non aggiornata: nessun candidato raggiunge Analyst.
        return result
    if not groups:
        result["state"] = "no_quoted_selections"
        result["blockers"].append({"type": "no_quoted_selections"})
        return result

    result["ok"] = True
    result["state"] = "ready"
    result["ready_for_analysis"] = True
    result["markets"] = groups
    result["market_count"] = len(groups)
    result["candidate_count"] = sum(len(x["selections"]) for x in groups)
    return result


@mcp.tool()
def scout_event(palinsesto: str, avvenimento: str):
    """Scout V1: prepara quote verificabili solo da PDF Sisal freschi.

    Un risultato 'blocked' non espone quote agli agenti. Anche un risultato
    'ready' certifica la qualita' tecnica, NON valore economico o probabilita'.
    """
    palinsesto = str(palinsesto).strip()
    avvenimento = str(avvenimento).strip()
    try:
        aggregate = get_all_event_quotes(palinsesto, avvenimento)
        if not isinstance(aggregate, dict):
            raise TypeError("L'aggregatore ha restituito un formato non valido")
        return _scout_evaluate_aggregate(aggregate)
    except Exception as exc:
        return {
            "agent": "scout_v1",
            "ok": False,
            "state": "scout_exception",
            "ready_for_analysis": False,
            "palinsesto": palinsesto,
            "avvenimento": avvenimento,
            "blockers": [{"type": "scout_exception", "detail": str(exc)[:300]}],
            "candidate_count": 0,
            "markets": [],
        }


@mcp.tool()
def search_odds(
    query: str,
    sheet: Optional[str] = None,
    limit: int = 100,
):
    """
    Cerca testo, squadre e mercati nei Fogli Quote
    già presenti nella cache.
    """

    if sheet:
        if sheet not in SHEETS:
            raise ValueError(
                "sheet deve essere base, "
                "combinate oppure extra"
            )

        targets = [sheet]

    else:
        targets = list(SHEETS.keys())

    query_lower = query.casefold()
    results = []

    for current_sheet in targets:
        text = get_cached_text(
            current_sheet
        )

        if not text:
            continue

        lines = clean_lines(text)

        for index, line in enumerate(lines):
            if query_lower in line.casefold():
                start = max(0, index - 1)
                end = min(
                    len(lines),
                    index + 2,
                )

                results.append(
                    {
                        "sheet": current_sheet,
                        "context": " | ".join(
                            lines[start:end]
                        ),
                    }
                )

                if len(results) >= limit:
                    return results

    return results


if __name__ == "__main__":
    start_background_refresher()

    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(
        os.environ.get("PORT", "8000")
    )

    mcp.run(
        transport="streamable-http"
    )
