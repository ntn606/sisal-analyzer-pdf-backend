import io
import os
import re
import time
from typing import Optional

import httpx
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
CACHE_TTL = 600


mcp = FastMCP(
    "Sisal Analyzer PDF",
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False
    ),
)


def fetch_pdf(sheet: str) -> str:
    if sheet not in SHEETS:
        raise ValueError(f"Foglio non supportato: {sheet}")

    now = time.time()

    cached = CACHE.get(sheet)
    if cached and now - cached["time"] < CACHE_TTL:
        return cached["text"]

    url = BASE + SHEETS[sheet]

    response = httpx.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/pdf,*/*",
        },
        timeout=30,
        follow_redirects=True,
    )

    response.raise_for_status()

    if not response.content.startswith(b"%PDF"):
        raise RuntimeError("La risposta Sisal non è un PDF valido.")

    reader = PdfReader(io.BytesIO(response.content))

    text = "\n".join(
        page.extract_text() or ""
        for page in reader.pages
    )

    CACHE[sheet] = {
        "time": now,
        "text": text,
    }

    return text


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

        numbers = re.findall(r"\b\d{3,6}\b", line)

        candidate = None

        if len(numbers) >= 2 and any(
            separator in line
            for separator in (" - ", " – ", " — ")
        ):
            candidate = line

        elif len(numbers) >= 2:
            start = max(0, index - 1)
            end = min(len(lines), index + 2)

            window = " ".join(lines[start:end])

            if any(
                separator in window
                for separator in (" - ", " – ", " — ")
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
def get_matches(
    query: Optional[str] = None,
    limit: int = 100,
):
    """
    Elenca gli eventi calcistici presenti nel Foglio Quote
    ufficiale Sisal "Calcio Base per Data".
    """

    text = fetch_pdf("base")

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
    Cerca lo stesso evento nei Fogli Quote ufficiali
    Base, Combinate ed Extra usando Palinsesto + Avvenimento.
    """

    palinsesto = str(palinsesto)
    avvenimento = str(avvenimento)

    result = {}

    for sheet in SHEETS:

        text = fetch_pdf(sheet)
        lines = clean_lines(text)

        hits = []

        for index, line in enumerate(lines):

            if (
                palinsesto in line
                and avvenimento in line
            ):
                start = max(0, index - 2)
                end = min(len(lines), index + 4)

                hits.append(
                    " | ".join(lines[start:end])
                )

        result[sheet] = {
            "updated": get_updated_timestamp(text),
            "source": BASE + SHEETS[sheet],
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
    Cerca squadre, mercati e selezioni nei Fogli Quote
    ufficiali Sisal configurati.
    """

    if sheet:
        if sheet not in SHEETS:
            raise ValueError(
                "sheet deve essere: base, combinate oppure extra"
            )

        targets = [sheet]

    else:
        targets = list(SHEETS.keys())

    query_lower = query.casefold()

    results = []

    for current_sheet in targets:

        text = fetch_pdf(current_sheet)
        lines = clean_lines(text)

        for index, line in enumerate(lines):

            if query_lower in line.casefold():

                start = max(0, index - 1)
                end = min(len(lines), index + 2)

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


@mcp.tool()
def source_status():
    """
    Controlla se i PDF ufficiali Sisal configurati
    sono raggiungibili e mostra il loro aggiornamento.
    """

    result = {}

    for sheet in SHEETS:

        try:
            text = fetch_pdf(sheet)

            result[sheet] = {
                "ok": True,
                "updated": get_updated_timestamp(text),
                "characters": len(text),
                "source": BASE + SHEETS[sheet],
            }

        except Exception as error:

            result[sheet] = {
                "ok": False,
                "error": str(error),
                "source": BASE + SHEETS[sheet],
            }

    return result


if __name__ == "__main__":

    mcp.settings.host = "0.0.0.0"

    mcp.settings.port = int(
        os.environ.get("PORT", "8000")
    )

    mcp.run(
        transport="streamable-http"
    )
