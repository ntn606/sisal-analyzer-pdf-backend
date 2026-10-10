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

ANALYST_BASELINE_SPECS = (
    ("base", "Esito finale 1X2", ("1", "X", "2")),
    ("base", "Under/Over 2,5", ("Under", "Over")),
    ("base", "Goal/No Goal", ("Goal", "No Goal")),
)

ANALYST_EVIDENCE_REQUIRED = (
    "Risultati recenti delle due squadre, con date e fonti",
    "Gol fatti e subiti e numero di partite del campione",
    "Contesto casa/trasferta e livello delle avversarie",
    "Disponibilita' della rosa e notizie verificabili",
    "Data e orario della partita confermati da una fonte esterna",
)


def _analyst_market_baselines(groups):
    """Misure DESCRITTIVE delle quote: non stime del rendimento sportivo."""
    baselines = []
    unavailable = []
    for sheet, market_name, required in ANALYST_BASELINE_SPECS:
        matching = [m for m in groups if m.get("sheet") == sheet
                    and m.get("market") == market_name]
        if len(matching) != 1:
            unavailable.append({"sheet": sheet, "market": market_name,
                                "reason": "market_missing_or_duplicate"})
            continue
        group = matching[0]
        rows = group.get("selections")
        if not isinstance(rows, list):
            unavailable.append({"sheet": sheet, "market": market_name,
                                "reason": "invalid_selection_format"})
            continue
        by_outcome = {}
        bad = False
        for row in rows:
            if not isinstance(row, dict):
                bad = True
                break
            outcome = row.get("outcome")
            price = row.get("decimal_odds")
            if (outcome in by_outcome or outcome not in required
                    or not isinstance(price, (int, float)) or isinstance(price, bool)
                    or not 1.01 <= price <= 999):
                bad = True
                break
            by_outcome[outcome] = float(price)
        if bad or set(by_outcome) != set(required):
            unavailable.append({"sheet": sheet, "market": market_name,
                                "reason": "incomplete_or_invalid_market"})
            continue
        inverse = {k: 1.0 / by_outcome[k] for k in required}
        total = sum(inverse.values())
        baselines.append({
            "sheet": sheet,
            "market": market_name,
            "pdf_updated": group.get("pdf_updated"),
            "source": group.get("source"),
            "sum_implied_percent": round(100 * total, 2),
            "overround_percent": round(100 * (total - 1), 2),
            "method": "reciprocal_odds_normalized_proportionally",
            "is_independent_probability_model": False,
            "selections": [
                {"outcome": key,
                 "decimal_odds": by_outcome[key],
                 "raw_inverse_odds_percent": round(100 * inverse[key], 2),
                 "normalized_market_share_percent": round(100 * inverse[key] / total, 2)}
                for key in required
            ],
        })
    return baselines, unavailable


def _analyst_review_scout(scout):
    """Transforma i dati Scout in un dossier di mercato, senza inventare stats."""
    result = {
        "agent": "analyst_v1",
        "ok": False,
        "state": "blocked_by_scout",
        "ready_for_quant": False,
        "event": scout.get("event") if isinstance(scout, dict) else None,
        "palinsesto": scout.get("palinsesto") if isinstance(scout, dict) else None,
        "avvenimento": scout.get("avvenimento") if isinstance(scout, dict) else None,
        "reason": "Scout non ha autorizzato l'analisi delle quote",
        "blockers": [],
        "market_count": 0,
        "quoted_selection_count": 0,
        "coverage_by_sheet": {},
        "market_baselines": [],
        "baseline_markets_unavailable": [],
        "independent_evidence": {
            "state": "not_connected",
            "required": list(ANALYST_EVIDENCE_REQUIRED),
        },
        "football_findings": [],
        "recommendations": [],
        "note": (
            "Le percentuali implicite nelle quote NON sono una previsione "
            "indipendente, non indicano value bet e non autorizzano puntate."
        ),
    }
    if not isinstance(scout, dict):
        result["blockers"] = [{"type": "invalid_scout_response"}]
        return result
    if not (scout.get("ok") is True and scout.get("state") == "ready"
            and scout.get("ready_for_analysis") is True):
        result["blockers"] = [{"type": "scout_not_ready",
                               "scout_state": scout.get("state"),
                               "details": scout.get("blockers") or []}]
        return result
    groups = scout.get("markets")
    if not isinstance(groups, list) or not groups:
        result["state"] = "invalid_scout_payload"
        result["blockers"] = [{"type": "scout_markets_missing"}]
        return result
    coverage = {}
    seen = set()
    count = 0
    for group in groups:
        if not isinstance(group, dict):
            result["state"] = "invalid_scout_payload"
            result["blockers"] = [{"type": "invalid_market"}]
            return result
        sheet, market = group.get("sheet"), group.get("market")
        if sheet not in SCOUT_SHEETS or not isinstance(market, str) or not market:
            result["state"] = "invalid_scout_payload"
            result["blockers"] = [{"type": "invalid_market_identity"}]
            return result
        if (sheet, market) in seen:
            result["state"] = "invalid_scout_payload"
            result["blockers"] = [{"type": "duplicate_market", "sheet": sheet, "market": market}]
            return result
        seen.add((sheet, market))
        rows = group.get("selections")
        if not isinstance(rows, list) or not rows:
            result["state"] = "invalid_scout_payload"
            result["blockers"] = [{"type": "empty_market", "sheet": sheet, "market": market}]
            return result
        for row in rows:
            if not isinstance(row, dict):
                result["state"] = "invalid_scout_payload"
                result["blockers"] = [{"type": "invalid_selection"}]
                return result
            price = row.get("decimal_odds")
            if (not isinstance(price, (int, float)) or isinstance(price, bool)
                    or not 1.01 <= price <= 999):
                result["state"] = "invalid_scout_payload"
                result["blockers"] = [{"type": "invalid_quote"}]
                return result
            count += 1
        stats = coverage.setdefault(sheet, {"markets": 0, "quoted_selections": 0})
        stats["markets"] += 1
        stats["quoted_selections"] += len(rows)
    if count != scout.get("candidate_count") or len(groups) != scout.get("market_count"):
        result["state"] = "invalid_scout_payload"
        result["blockers"] = [{"type": "scout_count_mismatch"}]
        return result

    baseline, unavailable = _analyst_market_baselines(groups)
    result.update({
        "ok": True,
        "state": "awaiting_independent_evidence",
        "reason": (
            "Quote tecnicamente verificate. Mancano dati sportivi esterni "
            "e verificabili prima di stimare le probabilita'."
        ),
        "market_count": len(groups),
        "quoted_selection_count": count,
        "coverage_by_sheet": coverage,
        "market_baselines": baseline,
        "baseline_markets_unavailable": unavailable,
    })
    return result


@mcp.tool()
def analyst_event(palinsesto: str, avvenimento: str):
    """Analyst V1: prepara il dossier delle quote Scout, senza false statistiche.

    Se Scout blocca, non riporta quote. Se Scout e' pronto, misura soltanto
    il mercato implicito delle quote; NON stima probabilita' indipendenti.
    """
    palinsesto, avvenimento = str(palinsesto).strip(), str(avvenimento).strip()
    try:
        scout = scout_event(palinsesto, avvenimento)
        return _analyst_review_scout(scout)
    except Exception as exc:
        return {
            "agent": "analyst_v1", "ok": False, "state": "analyst_exception",
            "ready_for_quant": False,
            "palinsesto": palinsesto, "avvenimento": avvenimento,
            "blockers": [{"type": "analyst_exception", "detail": str(exc)[:300]}],
            "market_baselines": [], "football_findings": [], "recommendations": [],
        }

import unicodedata
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

AF_API_BASE = "https://v3.football.api-sports.io"
AF_TIMEZONE = ZoneInfo("Europe/Rome")
AF_ALLOWED_ENDPOINTS = frozenset(("/status", "/fixtures"))
AF_MIN_HISTORY = 5
AF_HISTORY_DAYS = 180
AF_MAX_FIXTURE_DAYS_AHEAD = 7
AF_MAX_KICKOFF_DIFFERENCE_MINUTES = 30
AF_LOCAL_DAY_LIMIT = 70  # Limite difensivo interno; il piano free ha 100 richieste/die.
AF_LOCAL_MINUTE_LIMIT = 8 # Il piano free ha 10 richieste/minuto.
AF_CACHE = {}
AF_LOCK = threading.RLock()
AF_RATE = {"day": None, "day_count": 0, "minute": None,
           "minute_count": 0, "day_remaining": None,
           "minute_remaining": None, "day_limit": None}


class _AFError(Exception):
    """Errore non sensibile: NON include la chiave API o corpi HTTP."""

    def __init__(self, code, *, diagnostic=None):
        super().__init__(code)
        self.diagnostic = diagnostic


def _af_error_blocker(error):
    blocker = {"type": str(error)}
    if error.diagnostic is not None:
        blocker["diagnostic"] = error.diagnostic
    return blocker


def _af_normalize_team(name):
    if not isinstance(name, str):
        return ""
    transliterated = unicodedata.normalize("NFKD", name.casefold())
    ascii_text = "".join(c for c in transliterated if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", ascii_text))


def _af_int(value):
    try:
        return int(value) if value is not None and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None

def _af_classify_provider_error(errors):
    """Classifica gli errori API-Football senza riportarne il contenuto.

    Nessun testo originale del provider o informazione riservata e' restituita.
    Non modifica la logica di Scout, Analyst, o delle quote.
    """
    if not errors:
        return "provider_reported_error"
    if isinstance(errors, dict):
        keys = {str(k).casefold() for k in errors}
    else:
        keys = set()
    # Il contenuto resta solo in memoria per la classificazione: MAI in output.
    description = str(errors).casefold()[:4096]
    if ("plan" in keys or "subscription" in keys
            or re.search(r"\bfree\s+plans?\b", description)
            or "current plan" in description
            or "upgrade your plan" in description
            or "subscription does not" in description):
        return "provider_plan_restricted"
    if ("quota" in keys or "limit" in keys
            or "ratelimit" in keys or "requests" in keys
            or "quota exceeded" in description
            or "rate limit" in description
            or "request limit" in description
            or "too many requests" in description):
        return "provider_quota_restricted"
    if ("token" in keys or "key" in keys or "auth" in keys
            or "invalid api key" in description
            or "invalid token" in description):
        return "provider_authentication_failed"
    if (keys.intersection({"team", "last", "id", "date", "season", "fixture", "parameters", "parameter"})
            or "invalid parameter" in description
            or "required parameter" in description):
        return "provider_parameters_rejected"
    return "provider_reported_error"


def _af_error_diagnostic(code, path, params, errors=None, http_status=None):
    """Output solo da costanti/allowlist: mai valori o messaggi del provider."""
    categories = {
        "provider_plan_restricted": "plan_restriction",
        "provider_quota_restricted": "api_limit",
        "provider_rate_limited": "api_limit",
        "provider_daily_quota_reserve": "api_limit",
        "provider_minute_quota_reserve": "api_limit",
        "local_daily_budget_exhausted": "local_budget",
        "local_minute_budget_exhausted": "local_budget",
        "provider_authentication_failed": "authentication",
        "provider_parameters_rejected": "invalid_parameters",
        "provider_not_configured": "configuration",
        "endpoint_not_allowed": "endpoint_policy",
        "provider_transport_failure": "transport",
        "provider_http_failure": "http",
        "provider_invalid_json": "invalid_response",
        "provider_invalid_response": "invalid_response",
        "provider_pagination_not_handled": "pagination",
    }
    parameter_names = {"team", "last", "id", "date", "season", "fixture",
                       "timezone", "league", "from", "to", "next", "status", "page"}
    diagnostic = {
        "category": categories.get(code, "other"),
        "endpoint": path if path in AF_ALLOWED_ENDPOINTS else None,
        "request_parameter_names": sorted(parameter_names.intersection(params)),
    }
    if isinstance(http_status, int) and 100 <= http_status <= 599:
        diagnostic["http_status"] = http_status
    if code == "provider_plan_restricted":
        # Indica Free solo se esplicitamente presente nell'errore; non deduce il piano.
        diagnostic["free_plan_restriction"] = bool(
            re.search(r"\bfree\s+plans?\b", str(errors).casefold()[:4096])
        )
    if isinstance(errors, dict):
        diagnostic["error_parameter_names"] = sorted(
            parameter_names.intersection(k.casefold() for k in errors if isinstance(k, str))
        )
    return diagnostic


def _af_request(path, params=None, ttl_seconds=300):
    """GET sicuro con cache, quota locale e messaggi d'errore sanitizzati."""
    def failure(code, errors=None, http_status=None):
        return _AFError(code, diagnostic=_af_error_diagnostic(
            code, path, params or {}, errors, http_status
        ))

    if path not in AF_ALLOWED_ENDPOINTS:
        raise failure("endpoint_not_allowed")
    key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    if not key:
        raise failure("provider_not_configured")
    params = params or {}
    request_key = (path, tuple(sorted((str(k), str(v)) for k, v in params.items())))
    now_ts = time.time()
    with AF_LOCK:
        entry = AF_CACHE.get(request_key)
        if entry and now_ts - entry["at"] < ttl_seconds:
            return entry["body"], True

        utc_day = datetime.now(timezone.utc).date().isoformat()
        minute = int(now_ts // 60)
        if AF_RATE["day"] != utc_day:
            AF_RATE.update(day=utc_day, day_count=0, day_remaining=None,
                           day_limit=None)
        if AF_RATE["minute"] != minute:
            AF_RATE.update(minute=minute, minute_count=0, minute_remaining=None)
        if AF_RATE["day_count"] >= AF_LOCAL_DAY_LIMIT:
            raise failure("local_daily_budget_exhausted")
        if AF_RATE["minute_count"] >= AF_LOCAL_MINUTE_LIMIT:
            raise failure("local_minute_budget_exhausted")
        if AF_RATE["day_remaining"] is not None and AF_RATE["day_remaining"] <= 10:
            raise failure("provider_daily_quota_reserve")
        if AF_RATE["minute_remaining"] is not None and AF_RATE["minute_remaining"] <= 1:
            raise failure("provider_minute_quota_reserve")

        # La chiave viaggia SOLO nell'header HTTPS, mai nell'URL o nell'output.
        AF_RATE["day_count"] += 1
        AF_RATE["minute_count"] += 1
        try:
            response = requests.get(AF_API_BASE + path, params=params,
                headers={"x-apisports-key": key, "Accept": "application/json"},
                timeout=15)
        except Exception:
            raise failure("provider_transport_failure") from None

        for field, header in (("day_remaining", "x-ratelimit-requests-remaining"),
                              ("minute_remaining", "x-ratelimit-remaining"),
                              ("day_limit", "x-ratelimit-requests-limit")):
            parsed = _af_int(response.headers.get(header))
            if parsed is not None:
                AF_RATE[field] = parsed
        if response.status_code in (401, 403):
            raise failure("provider_authentication_failed", http_status=response.status_code)
        if response.status_code == 429:
            raise failure("provider_rate_limited", http_status=response.status_code)
        if response.status_code != 200:
            raise failure("provider_http_failure", http_status=response.status_code)
        try:
            body = response.json()
        except Exception:
            raise failure("provider_invalid_json", http_status=response.status_code) from None
        if not isinstance(body, dict):
            raise failure("provider_invalid_response", http_status=response.status_code)
        if body.get("errors"):
            # Le risposte di errore del provider potrebbero contenere informazioni sensibili.
            raise failure(_af_classify_provider_error(body["errors"]),
                          errors=body["errors"], http_status=response.status_code)
        paging = body.get("paging") or {}
        if isinstance(paging, dict) and (_af_int(paging.get("total")) or 1) > 1:
            raise failure("provider_pagination_not_handled", http_status=response.status_code)
        AF_CACHE[request_key] = {"at": now_ts, "body": body}
        return body, False


def _af_sisal_kickoff_time(palinsesto, avvenimento):
    """Recupera l'ora Sisal dal PDF Base. Non inventa la DATA della partita."""
    pdf_text = get_cached_text("base")
    if not pdf_text:
        return None
    matches = [m for m in extract_events(pdf_text)
               if m.get("palinsesto") == palinsesto and
                  m.get("avvenimento") == avvenimento]
    return matches[0].get("time") if len(matches) == 1 else None


def _af_fixture_kickoff(fixture):
    stamp = _af_int((fixture.get("fixture") or {}).get("timestamp"))
    if stamp is None:
        return None
    try:
        return datetime.fromtimestamp(stamp, timezone.utc).astimezone(AF_TIMEZONE)
    except (ValueError, OSError, OverflowError):
        return None


def _af_fixture_identity(fixture, home, away, sisal_time, match_date):
    if not isinstance(fixture, dict):
        return False, "invalid_fixture"
    teams = fixture.get("teams") or {}
    api_home = (teams.get("home") or {}).get("name")
    api_away = (teams.get("away") or {}).get("name")
    # Identita' stretta: eventuali soprannomi richiedono una mappatura verificata.
    if (_af_normalize_team(api_home) != _af_normalize_team(home)
            or _af_normalize_team(api_away) != _af_normalize_team(away)):
        return False, "team_names_do_not_match"
    kickoff = _af_fixture_kickoff(fixture)
    if kickoff is None:
        return False, "kickoff_missing"
    if kickoff.date().isoformat() != match_date:
        return False, "fixture_date_mismatch"
    if not sisal_time:
        return False, "sisal_kickoff_time_missing"
    if kickoff.strftime("%H:%M") != sisal_time:
        try:
            hh, mm = (int(x) for x in sisal_time.split(":"))
            minutes1 = kickoff.hour * 60 + kickoff.minute
            minutes2 = hh * 60 + mm
            delta = min(abs(minutes1-minutes2), 1440-abs(minutes1-minutes2))
        except (ValueError, TypeError):
            return False, "sisal_kickoff_time_invalid"
        if delta > AF_MAX_KICKOFF_DIFFERENCE_MINUTES:
            return False, "kickoff_time_mismatch"
    short = ((fixture.get("fixture") or {}).get("status") or {}).get("short")
    if short != "NS":
        return False, "fixture_not_pre_match"
    if kickoff <= datetime.now(AF_TIMEZONE):
        return False, "fixture_already_started"
    if (_af_int((teams.get("home") or {}).get("id")) is None or
        _af_int((teams.get("away") or {}).get("id")) is None):
        return False, "team_ids_missing"
    return True, None


def _af_form_for_team(team_id, fixture_timestamp, now_dt):
    body, cache_hit = _af_request("/fixtures", {"team": team_id, "last": 10}, 1800)
    response = body.get("response")
    if not isinstance(response, list):
        raise _AFError("history_invalid_response")
    valid = []
    for match in response:
        if not isinstance(match, dict):
            continue
        meta = match.get("fixture") or {}
        status = (meta.get("status") or {}).get("short")
        stamp = _af_int(meta.get("timestamp"))
        if status not in ("FT", "AET", "PEN") or stamp is None:
            continue
        if stamp >= fixture_timestamp or stamp >= int(now_dt.timestamp()):
            continue
        if stamp < fixture_timestamp - AF_HISTORY_DAYS * 86400:
            continue
        teams = match.get("teams") or {}
        goals = match.get("goals") or {}
        is_home = _af_int((teams.get("home") or {}).get("id")) == team_id
        is_away = _af_int((teams.get("away") or {}).get("id")) == team_id
        if is_home == is_away:
            continue
        gf, ga = ((goals.get("home"), goals.get("away")) if is_home else
                  (goals.get("away"), goals.get("home")))
        gf, ga = _af_int(gf), _af_int(ga)
        if gf is None or ga is None or gf < 0 or ga < 0:
            continue
        valid.append({"fixture_id":_af_int(meta.get("id")),
                      "date":datetime.fromtimestamp(stamp, timezone.utc).date().isoformat(),
                      "competition":(match.get("league") or {}).get("name"),
                      "opponent":((teams.get("away") if is_home else teams.get("home")) or {}).get("name"),
                      "venue":"home" if is_home else "away",
                      "goals_for":gf, "goals_against":ga,
                      "result":"W" if gf>ga else ("D" if gf==ga else "L"),
                      "timestamp":stamp})
    valid.sort(key=lambda m:m["timestamp"],reverse=True)
    valid = valid[:AF_MIN_HISTORY]
    for m in valid:
        m.pop("timestamp",None)
    wins = sum(m["result"] == "W" for m in valid)
    draws = sum(m["result"] == "D" for m in valid)
    losses = sum(m["result"] == "L" for m in valid)
    return {"team_id":team_id,"sample_size":len(valid),
            "wins":wins,"draws":draws,"losses":losses,
            "goals_for":sum(m["goals_for"] for m in valid),
            "goals_against":sum(m["goals_against"] for m in valid),
            "matches":valid,"cache_hit":cache_hit,
            "source_endpoint":"/fixtures?team=<team_id>&last=10"}


def _af_evidence_from_scout(scout, fixture_id=None, match_date=None):
    """Collega eventi Sisal solo dopo Scout READY e un match verificato."""
    result = {"agent":"football_evidence_v1", "ok":False,
              "state":"blocked_by_scout", "ready_for_quant":False,
              "palinsesto":str(scout.get("palinsesto", "")),
              "avvenimento":str(scout.get("avvenimento", "")),
              "event":scout.get("event"), "fixture":None,
              "teams_form":{}, "blockers":[],
              "note":"Statistiche descrittive; non sono probabilita' o suggerimenti di puntata."}
    if not (scout.get("ok") is True and scout.get("state") == "ready" and
            scout.get("ready_for_analysis") is True):
        result["blockers"]=[{"type":"scout_not_ready","state":scout.get("state")}]
        return result
    if not os.environ.get("API_FOOTBALL_KEY", "").strip():
        result.update(state="provider_not_configured", blockers=[{"type":"missing_key"}])
        return result
    now = datetime.now(AF_TIMEZONE)
    if match_date is None:
        match_date = now.date().isoformat()
    else:
        try:
            parsed = datetime.strptime(str(match_date), "%Y-%m-%d").date()
        except ValueError:
            result.update(state="invalid_match_date", blockers=[{"type":"date_must_be_yyyy_mm_dd"}])
            return result
        if parsed < now.date() or parsed > now.date() + timedelta(days=AF_MAX_FIXTURE_DAYS_AHEAD):
            result.update(state="match_date_out_of_range",blockers=[{"type":"outside_next_7_days"}])
            return result
    sisal_time = _af_sisal_kickoff_time(result["palinsesto"],result["avvenimento"])
    if not sisal_time:
        result.update(state="sisal_time_unavailable", blockers=[{"type":"missing_sisal_time"}])
        return result
    if not isinstance(result["event"], dict) or not result["event"].get("home") or not result["event"].get("away"):
        result.update(state="sisal_teams_unavailable",blockers=[{"type":"missing_sisal_teams"}])
        return result
    try:
        fid = _af_int(fixture_id)
        if fixture_id is not None and (fid is None or fid <= 0):
            result.update(state="invalid_fixture_id",blockers=[{"type":"invalid_fixture_id"}])
            return result
        params = ({"id":fid} if fid is not None else
                  {"date":match_date,"timezone":"Europe/Rome"})
        doc,_ = _af_request("/fixtures",params,300)
        fixtures = doc.get("response")
        if not isinstance(fixtures,list):
            raise _AFError("fixtures_invalid_response")
        passing=[]
        failure_reasons={}
        for fixture in fixtures:
            pass_check, reason = _af_fixture_identity(fixture,
                result["event"]["home"],result["event"]["away"],
                sisal_time,match_date)
            if pass_check:
                passing.append(fixture)
            elif reason:
                failure_reasons[reason]=failure_reasons.get(reason,0)+1
        if len(passing)!=1:
            result.update(state="fixture_ambiguous" if len(passing)>1 else "fixture_not_matched",
                blockers=[{"type":"fixture_match_count","count":len(passing),
                           "provider_candidates":len(fixtures),
                           "rejections":failure_reasons}])
            return result
        match=passing[0]
        kickoff=_af_fixture_kickoff(match)
        home=(match.get("teams") or {}).get("home") or {}
        away=(match.get("teams") or {}).get("away") or {}
        result["fixture"]={"id":_af_int((match.get("fixture") or {}).get("id")),
             "kickoff":kickoff.isoformat(timespec="minutes"),
             "league":(match.get("league") or {}).get("name"),
             "country":(match.get("league") or {}).get("country"),
             "home":{"id":_af_int(home.get("id")),"name":home.get("name")},
             "away":{"id":_af_int(away.get("id")),"name":away.get("name")},
             "source":"https://v3.football.api-sports.io/fixtures"}
        if result["fixture"]["id"] is None:
            raise _AFError("fixture_id_missing")
        for side,team in (("home",home),("away",away)):
            stats=_af_form_for_team(_af_int(team.get("id")),
                                    int(kickoff.timestamp()),now)
            stats["team_name"]=team.get("name")
            result["teams_form"][side]=stats
        short=[side for side,stats in result["teams_form"].items()
               if stats["sample_size"] < AF_MIN_HISTORY]
        if short:
            result.update(state="insufficient_recent_history",
                          blockers=[{"type":"less_than_5_recent_matches","sides":short}])
            return result
        result.update(ok=True,state="ready",ready_for_quant=True)
        return result
    except _AFError as exc:
        result.update(state="provider_unavailable",
                      blockers=[_af_error_blocker(exc)])
        return result


@mcp.tool()
def football_provider_status(check_remote: bool = False):
    """Verifica senza esporla la chiave API-Football su Railway.

    Di default non consuma richieste esterne; check_remote=True prova /status.
    """
    configured=bool(os.environ.get("API_FOOTBALL_KEY", "").strip())
    info={"provider":"API-Football", "configured":configured,
          "authenticated":None,"state":"configured_not_tested" if configured else "not_configured",
          "requests_remaining_last_seen":AF_RATE["day_remaining"]}
    if not check_remote or not configured:
        return info
    try:
        doc,_ = _af_request("/status",{},600)
        body=doc.get("response") or {}
        plan=(body.get("subscription") or {})
        quota=(body.get("requests") or {})
        info.update(authenticated=True,state="ok",
                    subscription_active=plan.get("active"),
                    plan=plan.get("plan"),
                    requests_today=quota.get("current"),
                    requests_limit_day=quota.get("limit_day"))
    except _AFError as exc:
        info.update(authenticated=False,state=str(exc))
        if exc.diagnostic is not None:
            info["provider_diagnostic"] = exc.diagnostic
    return info


@mcp.tool()
def football_evidence_event(palinsesto: str, avvenimento: str,
                            fixture_id: Optional[int] = None,
                            match_date: Optional[str] = None):
    """Sport: identifica incontro e ultimi 5 risultati, SENZA suggerire puntate.

    Blocca se Scout non e' ready, nomi/orari diversi, match gia' iniziato,
    dati insufficienti o API non disponibile. Se manca match_date usa oggi
    (ora italiana); per una partita futura specificare YYYY-MM-DD.
    """
    try:
        scout=scout_event(str(palinsesto).strip(),str(avvenimento).strip())
        return _af_evidence_from_scout(scout,fixture_id,match_date)
    except Exception:
        return {"agent":"football_evidence_v1","ok":False,"state":"internal_error",
                "ready_for_quant":False,"blockers":[{"type":"internal_error"}],
                "teams_form":{},"fixture":None}


@mcp.tool()
def analyst_event_enriched(palinsesto: str, avvenimento: str,
                           fixture_id: Optional[int] = None,
                           match_date: Optional[str] = None):
    """Analyst + prove esterne, solo se Scout autorizza.

    ready_for_quant indica dati sufficienti per una futura modellizzazione;
    NON e' una previsione di probabilita' ne' autorizzazione a scommettere.
    """
    try:
        scout=scout_event(str(palinsesto).strip(),str(avvenimento).strip())
        dossier=_analyst_review_scout(scout)
        if dossier.get("state")!="awaiting_independent_evidence":
            return dossier
        evidence=_af_evidence_from_scout(scout,fixture_id,match_date)
        dossier["independent_evidence"] = evidence
        dossier["ready_for_quant"] = evidence.get("ready_for_quant") is True
        dossier["football_findings"] = ([
            {"side":side,"team":stats["team_name"],"sample_size":stats["sample_size"],
             "wins":stats["wins"],"draws":stats["draws"],"losses":stats["losses"],
             "goals_for":stats["goals_for"],"goals_against":stats["goals_against"]}
            for side,stats in evidence.get("teams_form",{}).items()
        ] if evidence.get("state")=="ready" else [])
        dossier["state"] = ("evidence_ready" if dossier["ready_for_quant"]
                             else "awaiting_independent_evidence")
        return dossier
    except Exception:
        return {"agent":"analyst_v1","ok":False,"state":"internal_error",
                "ready_for_quant":False,"football_findings":[],
                "blockers":[{"type":"internal_error"}],"recommendations":[]}

# === API-FOOTBALL: integrazione indipendente V1 (fine) ===

def _af_fixture_probe_review(aggregate, sisal_time, match_date, requester=None, now=None):
    """Diagnostica SOLTANTO identita' e copertura: NON approva quote.

    Consente di controllare se API-Football conosce una partita Sisal anche
    quando i PDF sono vecchi. Non restituisce quote, probabilita', value bet.
    'requester'/'now' permettono test offline senza consumare chiamate API.
    """
    from difflib import SequenceMatcher

    if now is None:
        now = datetime.now(AF_TIMEZONE)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include timezone")
    now = now.astimezone(AF_TIMEZONE)
    result = {
        "diagnostic": "football_fixture_probe_v1",
        "ok": False,
        "state": "not_checked",
        "diagnostic_only": True,
        "ready_for_analysis": False,
        "ready_for_quant": False,
        "palinsesto": str(aggregate.get("palinsesto", "")) if isinstance(aggregate, dict) else "",
        "avvenimento": str(aggregate.get("avvenimento", "")) if isinstance(aggregate, dict) else "",
        "match_date": match_date,
        "sisal": None,
        "provider_fixture_count": 0,
        "exact_matches": [],
        "possible_matches_to_review": [],
        "rejections": {},
        "blockers": [],
        "provider_cache_hit": None,
        "note": (
            "Solo verifica di copertura/identita'. Non restituisce quote e "
            "non aggira i blocchi di Scout; un match API non abilita Quant."
        ),
    }

    # Prima le condizioni locali: zero chiamate esterne se input incerto.
    try:
        day = datetime.strptime(str(match_date), "%Y-%m-%d").date()
        if day.isoformat() != str(match_date):
            raise ValueError("non canonical date")
    except (ValueError, TypeError):
        result.update(state="invalid_date", blockers=[{"type": "date_must_be_yyyy_mm_dd"}])
        return result
    if day < now.date() or day > (now + timedelta(days=7)).date():
        result.update(state="date_out_of_range", blockers=[{"type": "only_next_7_days"}])
        return result
    if not isinstance(aggregate, dict) or aggregate.get("state") not in ("ok", "partial"):
        result.update(state="sisal_unavailable", blockers=[{"type": "aggregate_not_readable"}])
        return result

    sheets = aggregate.get("sheets")
    if not isinstance(sheets, dict):
        result.update(state="sisal_unavailable", blockers=[{"type": "sources_not_available"}])
        return result
    names = []
    for sheet in ("base", "extra", "combinate"):
        source = sheets.get(sheet)
        if not isinstance(source, dict) or source.get("state") != "ok":
            result.update(state="sisal_unavailable", blockers=[{"type": "sheet_not_ok", "sheet": sheet}])
            return result
        home = source.get("home_printed")
        away = source.get("away_printed")
        if not isinstance(home, str) or not home.strip() or not isinstance(away, str) or not away.strip():
            result.update(state="sisal_unavailable", blockers=[{"type": "names_missing", "sheet": sheet}])
            return result
        names.append((home.strip(), away.strip()))
    if len({(_af_normalize_team(h), _af_normalize_team(a)) for h, a in names}) != 1:
        result.update(state="sisal_names_conflict", blockers=[{"type": "source_team_names_disagree"}])
        return result
    if not isinstance(sisal_time, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", sisal_time):
        result.update(state="sisal_time_missing", blockers=[{"type": "invalid_or_missing_kickoff_time"}])
        return result

    home, away = names[0]
    result["sisal"] = {
        "home": home, "away": away, "kickoff_local_time": sisal_time,
        "pdf_updated": {k: sheets[k].get("updated") for k in ("base", "extra", "combinate")},
        "pdf_freshness_not_verified": True,
    }
    if requester is None:
        requester = _af_request
    try:
        response, cached = requester(
            "/fixtures", {"date": match_date, "timezone": "Europe/Rome"}, 300
        )
        fixtures = response.get("response") if isinstance(response, dict) else None
        if not isinstance(fixtures, list):
            raise _AFError("fixtures_invalid_response")
        result["provider_cache_hit"] = bool(cached)
        result["provider_fixture_count"] = len(fixtures)
        near = []
        for match in fixtures:
            if not isinstance(match, dict):
                continue
            teams = match.get("teams") or {}
            if not isinstance(teams, dict):
                continue
            api_home = (teams.get("home") or {}).get("name")
            api_away = (teams.get("away") or {}).get("name")
            if not isinstance(api_home, str) or not isinstance(api_away, str):
                continue
            h_sim = SequenceMatcher(None, _af_normalize_team(home),
                                    _af_normalize_team(api_home)).ratio()
            a_sim = SequenceMatcher(None, _af_normalize_team(away),
                                    _af_normalize_team(api_away)).ratio()
            # Utilizzare il controllo rigoroso gia' presente nel backend.
            exact, why = _af_fixture_identity(match, home, away, sisal_time, match_date)
            kickoff = _af_fixture_kickoff(match)
            info = {
                "fixture_id": _af_int((match.get("fixture") or {}).get("id")),
                "home": api_home,
                "away": api_away,
                "league": (match.get("league") or {}).get("name"),
                "kickoff": kickoff.isoformat(timespec="minutes") if kickoff else None,
                "status": ((match.get("fixture") or {}).get("status") or {}).get("short"),
            }
            if exact:
                result["exact_matches"].append(info)
            else:
                if why:
                    result["rejections"][why] = result["rejections"].get(why, 0) + 1
                if h_sim >= 0.55 and a_sim >= 0.55:
                    near.append({**info, "home_similarity": round(h_sim, 3),
                                 "away_similarity": round(a_sim, 3),
                                 "not_verified_reason": why})
        near.sort(key=lambda x: (x["home_similarity"] + x["away_similarity"]), reverse=True)
        result["possible_matches_to_review"] = near[:5]
        if len(result["exact_matches"]) == 1:
            result.update(ok=True, state="exact_fixture_identified")
        elif len(result["exact_matches"]) > 1:
            result.update(state="ambiguous_fixture", blockers=[{"type": "multiple_exact_fixtures"}])
        else:
            result.update(state="fixture_not_identified", blockers=[{"type": "no_exact_fixture"}])
        return result
    except _AFError as exc:
        result.update(state="provider_unavailable", blockers=[_af_error_blocker(exc)])
        return result


@mcp.tool()
def football_fixture_probe(palinsesto: str, avvenimento: str, match_date: str):
    """Verifica identificazione partita su API-Football SENZA usare quote.

    Diagnostica anche con PDF vecchi: NON sostituisce Scout.
    Restituisce fixture_id, nomi e orario solo per identificazione. Non
    produce risultati, probabilita', consigli ne' ready_for_quant=True.
    Richiede match_date YYYY-MM-DD (oggi o entro sette giorni in Italia).
    """
    palinsesto, avvenimento = str(palinsesto).strip(), str(avvenimento).strip()
    try:
        if not (re.fullmatch(r"\d{3,6}", palinsesto) and
                re.fullmatch(r"\d{1,6}", avvenimento)):
            return {
                "diagnostic": "football_fixture_probe_v1", "ok": False,
                "state": "invalid_event_ids", "diagnostic_only": True,
                "ready_for_analysis": False, "ready_for_quant": False,
                "exact_matches": [], "possible_matches_to_review": [],
            }
        aggregate = get_all_event_quotes(palinsesto, avvenimento)
        sisal_time = _af_sisal_kickoff_time(palinsesto, avvenimento)
        return _af_fixture_probe_review(aggregate, sisal_time, match_date)
    except Exception:
        return {
            "diagnostic": "football_fixture_probe_v1", "ok": False,
            "state": "internal_error", "diagnostic_only": True,
            "ready_for_analysis": False, "ready_for_quant": False,
            "exact_matches": [], "possible_matches_to_review": [],
        }

# === API-FOOTBALL: diagnostica copertura partite V1 (fine) ===

def _af_history_probe_summary(records, team_id, before_kickoff, now_dt):
    """Estrae risultati conclusi da dati API-Football; nessuna quota."""
    from datetime import datetime, timezone

    if not isinstance(records, list):
        raise _AFError("history_invalid_response")
    if not isinstance(team_id, int) or isinstance(team_id, bool) or team_id <= 0:
        raise _AFError("invalid_history_team_id")

    cutoff = int(before_kickoff.timestamp())
    current = int(now_dt.timestamp())
    lower = cutoff - AF_HISTORY_DAYS * 86400
    valid = []
    seen = set()
    excluded = {}

    def skip(reason):
        excluded[reason] = excluded.get(reason, 0) + 1

    for row in records:
        if not isinstance(row, dict):
            skip("invalid_row")
            continue
        fixture = row.get("fixture") or {}
        teams = row.get("teams") or {}
        goals = row.get("goals") or {}
        if not isinstance(fixture, dict) or not isinstance(teams, dict) or not isinstance(goals, dict):
            skip("invalid_row")
            continue

        # Escludiamo i rigori: il campo goals puo' rappresentare il pareggio
        # prima dei rigori e non descrivere il vincitore del confronto.
        if (fixture.get("status") or {}).get("short") not in ("FT", "AET"):
            skip("not_finished_in_regular_or_extra_time")
            continue
        stamp = _af_int(fixture.get("timestamp"))
        fid = _af_int(fixture.get("id"))
        if stamp is None or fid is None or fid <= 0 or stamp >= cutoff or stamp >= current or stamp < lower:
            skip("invalid_or_out_of_window_fixture")
            continue

        side_home = (teams.get("home") or {})
        side_away = (teams.get("away") or {})
        if not isinstance(side_home, dict) or not isinstance(side_away, dict):
            skip("invalid_team_data")
            continue
        home_id = _af_int(side_home.get("id"))
        away_id = _af_int(side_away.get("id"))
        if home_id == away_id or team_id not in (home_id, away_id):
            skip("team_identity_mismatch")
            continue
        if fid in seen:
            skip("duplicate_fixture")
            continue
        is_home = home_id == team_id
        scored = _af_int(goals.get("home" if is_home else "away"))
        conceded = _af_int(goals.get("away" if is_home else "home"))
        opponent = side_away.get("name") if is_home else side_home.get("name")
        if (scored is None or conceded is None or scored < 0 or conceded < 0
                or not isinstance(opponent, str) or not opponent.strip()):
            skip("goals_or_opponent_missing")
            continue

        seen.add(fid)
        league = row.get("league") or {}
        valid.append({
            "fixture_id": fid,
            "date": datetime.fromtimestamp(stamp, timezone.utc).astimezone(AF_TIMEZONE).date().isoformat(),
            "opponent": opponent.strip(),
            "competition": league.get("name") if isinstance(league, dict) else None,
            "venue": "home" if is_home else "away",
            "goals_for": scored,
            "goals_against": conceded,
            "result": "W" if scored > conceded else "D" if scored == conceded else "L",
            "final_status": fixture.get("status").get("short"),
            "_stamp": stamp,
        })

    valid.sort(key=lambda item: item["_stamp"], reverse=True)
    sample = valid[:AF_MIN_HISTORY]
    for row in sample:
        row.pop("_stamp", None)

    return {
        "team_id": team_id,
        "sample_size": len(sample),
        "sample_target": AF_MIN_HISTORY,
        "complete_sample": len(sample) == AF_MIN_HISTORY,
        "wins": sum(row["result"] == "W" for row in sample),
        "draws": sum(row["result"] == "D" for row in sample),
        "losses": sum(row["result"] == "L" for row in sample),
        "goals_for": sum(row["goals_for"] for row in sample),
        "goals_against": sum(row["goals_against"] for row in sample),
        "matches": sample,
        "excluded_records": excluded,
        "source_endpoint": "/fixtures?team=<team_id>&last=10",
    }


def _af_history_probe_review(fixture_id, expected_home, expected_away,
                             match_date, requester=None, now=None):
    """Diagnostica indipendente da Scout, testabile con un requester finto."""
    from datetime import datetime, timedelta

    if now is None:
        now = datetime.now(AF_TIMEZONE)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(AF_TIMEZONE)

    result = {
        "diagnostic": "football_history_probe_v1",
        "ok": False,
        "state": "not_checked",
        "diagnostic_only": True,
        "ready_for_analysis": False,
        "ready_for_quant": False,
        "fixture_id": fixture_id,
        "match_date": match_date,
        "expected_teams": {"home": expected_home, "away": expected_away},
        "fixture": None,
        "teams_form": {},
        "blockers": [],
        "provider_cache_hits": {},
        "api_calls_max_without_cache": 3,
        "note": (
            "Dati descrittivi da API-Football; zero quote e zero pronostici. "
            "Non certifica PDF Sisal, non aggira Scout e non abilita Quant. "
            "Le partite decise ai rigori sono escluse dallo storico; "
            "le altre competizioni sono dichiarate partita per partita."
        ),
    }
    fid = _af_int(fixture_id)
    if fid is None or fid <= 0 or isinstance(fixture_id, bool):
        result.update(state="invalid_fixture_id", blockers=[{"type": "invalid_fixture_id"}])
        return result
    if (not isinstance(expected_home, str) or not isinstance(expected_away, str)
            or not _af_normalize_team(expected_home)
            or not _af_normalize_team(expected_away)
            or _af_normalize_team(expected_home) == _af_normalize_team(expected_away)):
        result.update(state="invalid_expected_teams", blockers=[{"type": "two_distinct_team_names_required"}])
        return result
    try:
        date = datetime.strptime(str(match_date), "%Y-%m-%d").date()
        if date.isoformat() != match_date:
            raise ValueError("non-canonical")
    except (ValueError, TypeError):
        result.update(state="invalid_match_date", blockers=[{"type": "date_must_be_yyyy_mm_dd"}])
        return result
    if not now.date() <= date <= (now + timedelta(days=AF_MAX_FIXTURE_DAYS_AHEAD)).date():
        result.update(state="date_out_of_range", blockers=[{"type": "only_next_7_days"}])
        return result
    if requester is None:
        requester = _af_request

    try:
        body, fixture_cache_hit = requester("/fixtures", {"id": fid}, 300)
        fixtures = body.get("response") if isinstance(body, dict) else None
        result["provider_cache_hits"]["fixture"] = bool(fixture_cache_hit)
        if not isinstance(fixtures, list) or len(fixtures) != 1:
            result.update(state="fixture_not_unique", blockers=[{"type": "fixture_not_found_or_ambiguous"}])
            return result
        match = fixtures[0]
        if not isinstance(match, dict):
            result.update(state="invalid_fixture_payload", blockers=[{"type": "invalid_fixture_payload"}])
            return result
        meta = match.get("fixture") or {}
        teams = match.get("teams") or {}
        if not isinstance(meta, dict) or not isinstance(teams, dict):
            result.update(state="invalid_fixture_payload", blockers=[{"type": "invalid_fixture_payload"}])
            return result
        home = teams.get("home") or {}
        away = teams.get("away") or {}
        if not isinstance(home, dict) or not isinstance(away, dict):
            result.update(state="invalid_fixture_payload", blockers=[{"type": "invalid_fixture_payload"}])
            return result
        hname = home.get("name")
        aname = away.get("name")
        home_id = _af_int(home.get("id"))
        away_id = _af_int(away.get("id"))
        kickoff = _af_fixture_kickoff(match)
        if (_af_int(meta.get("id")) != fid
                or not _af_normalize_team(hname) == _af_normalize_team(expected_home)
                or not _af_normalize_team(aname) == _af_normalize_team(expected_away)
                or home_id is None or away_id is None
                or home_id <= 0 or away_id <= 0 or home_id == away_id):
            result.update(state="fixture_identity_mismatch",
                          blockers=[{"type": "fixture_or_teams_do_not_match"}])
            return result
        if kickoff is None or kickoff.date() != date:
            result.update(state="fixture_date_mismatch", blockers=[{"type": "kickoff_date_mismatch"}])
            return result
        if (meta.get("status") or {}).get("short") != "NS" or kickoff <= now:
            result.update(state="fixture_not_upcoming", blockers=[{"type": "not_pre_match"}])
            return result
        league = match.get("league") or {}
        result["fixture"] = {
            "id": fid,
            "home": {"id": home_id, "name": hname},
            "away": {"id": away_id, "name": aname},
            "competition": league.get("name") if isinstance(league, dict) else None,
            "kickoff": kickoff.isoformat(timespec="minutes"),
            "status": "NS",
            "source": "https://v3.football.api-sports.io/fixtures",
        }
        for side, team_id in (("home", home_id), ("away", away_id)):
            response, hit = requester("/fixtures", {"team": team_id, "last": 10}, 1800)
            rows = response.get("response") if isinstance(response, dict) else None
            result["provider_cache_hits"][side] = bool(hit)
            stats = _af_history_probe_summary(rows, team_id, kickoff, now)
            stats["team_name"] = hname if side == "home" else aname
            result["teams_form"][side] = stats

        missing = [side for side, stats in result["teams_form"].items()
                   if not stats["complete_sample"]]
        if missing:
            result.update(state="insufficient_recent_history",
                          blockers=[{"type": "less_than_5_valid_recent_results", "sides": missing}])
            return result
        result.update(ok=True, state="history_available")
        return result
    except _AFError as exc:
        result.update(state="provider_unavailable", blockers=[_af_error_blocker(exc)])
        return result


@mcp.tool()
def football_history_probe(fixture_id: int, expected_home: str,
                           expected_away: str, match_date: str):
    """Ultimi 5 risultati verificati per le squadre di un fixture futuro.

    Diagnostica slegata da Scout: quote, PDF, probability model e Quant NON
    vengono consultati o autorizzati. Fino a tre richieste API-Football,
    con cache e limiti giornalieri gia' previsti da _af_request.
    """
    try:
        return _af_history_probe_review(fixture_id, expected_home,
                                        expected_away, match_date)
    except Exception:
        return {
            "diagnostic": "football_history_probe_v1",
            "ok": False,
            "state": "internal_error",
            "diagnostic_only": True,
            "ready_for_analysis": False,
            "ready_for_quant": False,
            "fixture_id": fixture_id,
            "teams_form": {},
            "blockers": [{"type": "internal_error"}],
        }

# === API-FOOTBALL: diagnostica storico squadre V1 (fine) ===


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
