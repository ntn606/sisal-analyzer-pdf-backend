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


def download_pdf(sheet: str) -> str:
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
                request_url += (
                    f"?cb={int(time.time())}"
                )

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

            return text

        except Exception as error:
            last_error = error

            if attempt == 0:
                time.sleep(1)

    raise RuntimeError(
        f"Download Sisal fallito: {last_error}"
    )


def save_cache(sheet: str, text: str):
    with CACHE_LOCK:
        CACHE[sheet] = {
            "text": text,
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
        text = download_pdf(sheet)
        save_cache(sheet, text)
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
    lines = clean_lines(text)

    events = []
    seen = set()

    for index, line in enumerate(lines):
        numbers = re.findall(
            r"\b\d{3,6}\b",
            line,
        )

        candidate = None

        if len(numbers) >= 2 and any(
            separator in line
            for separator in (" - ", " – ", " — ")
        ):
            candidate = line

        elif len(numbers) >= 2:
            start = max(0, index - 1)
            end = min(len(lines), index + 2)

            window = " ".join(
                lines[start:end]
            )

            if any(
                separator in window
                for separator in (
                    " - ",
                    " – ",
                    " — ",
                )
            ):
                candidate = window

        if candidate:
            key = (
                numbers[0],
                numbers[1],
                candidate,
            )

            if key not in seen:
                seen.add(key)

                events.append(
                    {
                        "palinsesto": numbers[0],
                        "avvenimento": numbers[1],
                        "raw": candidate,
                    }
                )

    return events


@mcp.tool()
def source_status():
    """
    Mostra lo stato della cache dei Fogli Quote Sisal.
    Questa funzione non effettua download e risponde subito.
    """

    result = {}

    with CACHE_LOCK:
        snapshot = dict(CACHE)

    for sheet in SHEETS:
        item = snapshot.get(sheet)

        if not item:
            result[sheet] = {
                "ok": False,
                "state": "loading",
                "source": pdf_url(sheet),
            }
            continue

        text = item.get("text")

        result[sheet] = {
            "ok": bool(text),
            "state": (
                "ready"
                if text
                else "download_error"
            ),
            "updated": (
                get_updated_timestamp(text)
                if text
                else None
            ),
            "characters": (
                len(text)
                if text
                else 0
            ),
            "cache_age_seconds": cache_age(sheet),
            "last_error": item.get("error"),
            "source": pdf_url(sheet),
        }

    return result


@mcp.tool()
def refresh_sources():
    """
    Avvia in background un nuovo aggiornamento dei PDF.
    Risponde immediatamente.
    """

    thread = threading.Thread(
        target=refresh_all,
        daemon=True,
    )
    thread.start()

    return {
        "ok": True,
        "message": "Aggiornamento Sisal avviato in background.",
    }


@mcp.tool()
def get_matches(
    query: Optional[str] = None,
    limit: int = 100,
):
    """
    Elenca gli eventi presenti nella copia cache
    del Foglio Quote Calcio Base.
    """

    text = get_cached_text("base")

    if not text:
        return {
            "ok": False,
            "state": "source_not_ready",
            "message": (
                "Il Foglio Quote Base non è ancora "
                "disponibile nella cache."
            ),
            "matches": [],
        }

    events = extract_events(text)

    if query:
        q = query.casefold()

        events = [
            event
            for event in events
            if q in event["raw"].casefold()
        ]

    limit = max(1, min(limit, 300))

    return {
        "ok": True,
        "source": pdf_url("base"),
        "updated": get_updated_timestamp(text),
        "cache_age_seconds": cache_age("base"),
        "count": len(events),
        "matches": events[:limit],
    }


@mcp.tool()
def get_event_markets(
    palinsesto: str,
    avvenimento: str,
):
    """
    Cerca un evento nei fogli Base, Combinate ed Extra
    già presenti nella cache.
    """

    palinsesto = str(palinsesto)
    avvenimento = str(avvenimento)

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

        for index, line in enumerate(lines):
            if (
                palinsesto in line
                and avvenimento in line
            ):
                start = max(0, index - 2)
                end = min(
                    len(lines),
                    index + 4,
                )

                hits.append(
                    " | ".join(
                        lines[start:end]
                    )
                )

        result[sheet] = {
            "ok": True,
            "updated": get_updated_timestamp(text),
            "cache_age_seconds": cache_age(sheet),
            "source": pdf_url(sheet),
            "hits": hits[:30],
        }

    return {
        "palinsesto": palinsesto,
        "avvenimento": avvenimento,
        "sheets": result,
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
