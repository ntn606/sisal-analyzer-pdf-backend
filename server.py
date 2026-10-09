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
