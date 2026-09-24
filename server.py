import io
import os
import re
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


def extract_positioned_text(
    sheet: str,
    palinsesto: str,
    avvenimento: str,
):
    """
    Estrae i frammenti di testo dal PDF conservando
    le coordinate X/Y originali.

    Serve per ricostruire correttamente le colonne
    dei Fogli Quote Sisal.
    """

    pdf_bytes = get_cached_pdf(sheet)

    if not pdf_bytes:
        return []

    reader = PdfReader(io.BytesIO(pdf_bytes))

    palinsesto = str(palinsesto).strip()
    avvenimento = str(avvenimento).strip()

    results = []

    for page_number, page in enumerate(reader.pages):
        fragments = []

        def visitor(
            text,
            cm,
            tm,
            font_dict,
            font_size,
        ):
            value = re.sub(
                r"\s+",
                " ",
                text or "",
            ).strip()

            if not value:
                return

            fragments.append(
                {
                    "text": value,
                    "x": round(float(tm[4]), 2),
                    "y": round(float(tm[5]), 2),
                    "font_size": round(
                        float(font_size),
                        2,
                    ),
                }
            )

        page.extract_text(
            visitor_text=visitor
        )

        # Raggruppiamo gli elementi che si trovano
        # approssimativamente sulla stessa riga.
        rows = {}

        for fragment in fragments:
            y_key = round(
                fragment["y"] / 2
            ) * 2

            rows.setdefault(
                y_key,
                [],
            ).append(fragment)

        for y_key, row in rows.items():
            row.sort(
                key=lambda item: item["x"]
            )

            joined = " ".join(
                item["text"]
                for item in row
            )

            # La riga dell'evento deve contenere
            # entrambi gli identificatori.
            if (
                palinsesto not in joined
                or avvenimento not in joined
            ):
                continue

            results.append(
                {
                    "page": page_number + 1,
                    "y": y_key,
                    "joined": joined,
                    "fragments": row,
                }
            )

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
