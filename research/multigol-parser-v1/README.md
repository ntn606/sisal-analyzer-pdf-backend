# Parser Multigol V1 — Sisal Analyzer V3, A2.1

Modulo sperimentale offline. Legge le quote dalle celle fisiche di uno snapshot
del PDF ufficiale Sisal, senza usare l'ordine dei numeri nel testo estratto.

Stato: implementato e verificato sullo snapshot reale descritto sotto, con limiti
espliciti. Non è integrato nel backend e non è un parser universale di ogni PDF.
Nessuna probabilità, modello predittivo, pronostico o indicazione di puntata.

Base del branch: main, 304cb2cf06d9f8f226eb89b701d3ec57beba6a38.
server.py, parser Base/Extra/Combinate, Scout V1 e configurazioni di produzione
sono invariati. Nessun merge/cherry-pick da Champions o Football Evidence A1.1.
Nessuna modifica Railway o servizio aggiuntivo.

## Fonte reale e riproducibilità

URL: https://landing.sisal.it/volantini/Scommesse_Sport/Quote/calcio%20multigoal%20per%20data.pdf

Acquisizione completa effettiva: 2026-10-15T20:42:15.875743Z,
15 ottobre 2026, 22:42:15.875743 Europe/Madrid. HTTP 200, TLS verificato,
proxy conservato, nessun redirect. PDF: 115745 byte, 2 pagine.

SHA-256:
71122a3a521047659941ff400f699db8b38471dd616b6c509c2f3542d0db7b4e

Il documento stampa “15/10/2026 - ore 22:08:15”. La timezone non è dichiarata:
publisher_timestamp_text conserva il valore locale stampato;
published_at_utc rimane null. La rilevazione effettiva UTC è distinta.

PDF e metadati originali in tests/fixtures/. Non si acquisisce una nuova versione
durante i test. Il contenuto viene letto una volta e sia coordinate sia testo
sono ricavati dagli stessi byte, dopo la verifica del relativo hash.
Gli output dimostrano quote di questo archivio, non prezzi attuali.

## Uso locale

Python 3.12. Per usare solo il reader:

~~~bash
python -m venv /tmp/sisal-multigol
/tmp/sisal-multigol/bin/pip install -r research/multigol-parser-v1/requirements.txt
cd research/multigol-parser-v1

/tmp/sisal-multigol/bin/python -m multigol_parser \
  tests/fixtures/multigol-per-data-20261015.pdf \
  --provenance tests/fixtures/multigol-per-data-20261015.provenance.json \
  --identity examples/6028.identity.json
~~~

La CLI legge solo file locali; la URL di provenienza non viene mai scaricata.
Non legge credenziali. Non accetta un override dell'orologio.
Default real_only; synthetic_test è un opt-in esplicito per fixture sintetiche.
Exit code 0 per parsed/partial, 2 per blocked. partial richiede di verificare
gli stati delle singole celle: non significa che ogni selezione abbia una quota.

L'identità attesa deve contenere esattamente palinsesto, avvenimento,
competition_code, home, away, match_date e local_time, tutti stringhe.
Il confronto dei nomi normalizza solo gli spazi: nessun fuzzy match o alias
automatico. Una categoria richiesta esplicitamente causa un blocco, perché
il layout supportato non la stampa separatamente.

Interfaccia Python:

~~~python
from multigol_parser import parse_snapshot

report = parse_snapshot(pdf_path, provenance_path, expected_identity)
~~~

## Risultati e prove delle celle

Il layout osservato presenta 15 fasce, ognuna con fascia e Altro separati:
1–2, 1–3, 1–4, 1–5, 1–6, 2–3, 2–4, 2–5, 2–6,
3–4, 3–5, 3–6, 4–5, 4–6 e 5–6.

| Evento stampato | Fascia | Quota fascia | Quota Altro |
|---|---|---|---|
| 36421/31108, Club Omnisport De Meknes – Union Touarga Sport | 1–2 | 1,72 | 1,80 |
| stesso evento | 2–4 | 1,52 | 2,05 |
| stesso evento | 3–6 | 2,45 | 1,38 |
| stesso evento | 5–6 | 12 | null, cella vuota |
| 36421/6028, Biellese – Valenzana | 1–6 | null, cella vuota | 7,50 |
| stesso evento | 2–4 | 1,50 | 2,15 |
| 36421/6071, Budoni – Ssd Albalonga, pagina 2 | 2–4 | 1,47 | 2,25 |

Vedi proof/original-page-1.png e original-page-2.png: rasterizzazioni del PDF
originale, con soli contorni blu (fascia) e arancioni (Altro). Nessun numero
è stato generato, completato o disegnato nelle celle.

tests/fixtures/manual-cell-golden.json conserva 90 prezzi/null trascritti
dalla lettura del documento renderizzato, con box fissi e hash dello snapshot.
Non è generato dal parser. Il reviewer è Codex; revisione umana indipendente
ancora richiesta. I test confrontano sia l'output sia le estrazioni dirette da
quei box del PDF con le trascrizioni. proof/90-cell-audit.json documenta il confronto.

Gli esempi completi sono in examples/: due output partial con celle vuote,
uno parsed sulla seconda pagina e un blocco per competizione discordante.
Non attribuiscono questi prezzi a eventi diversi o a mercati squadra.

## Contratto e limiti

schemas/output.schema.json descrive il JSON. LAYOUT_AND_CONTRACT.md spiega
riconoscimento, identità, coordinate, compatibilità A1.1 e casi non supportati.
TEST_REPORT.md riporta il dettaglio della verifica.

Stati generali: parsed, partial, blocked.
Stati delle celle: verified_from_pdf_cell, missing, blocked.
verified_from_pdf_cell certifica la lettura locale della cella sotto l'intestazione,
non un'identità canonica multi-provider, una categoria senior o la freschezza
attuale di una quota. printed_identity_matched confronta soltanto la riga Sisal
con l'identità attesa fornita.

Le uscite mantengono diagnostic_only=true, ready_for_analysis=false,
ready_for_quant=false, statistics_usable_in_production=false.
Periodo di settlement, timezone del match e categoria non sono inferiti:
rimangono null. Nessuna conversione automatica di Altro.

## Test e CI completamente offline

Per suite sperimentale più le 13 regressioni backend, dalla radice del repository:

~~~bash
python -m venv /tmp/sisal-multigol-ci
/tmp/sisal-multigol-ci/bin/pip install -r research/multigol-parser-v1/requirements-ci.txt
/tmp/sisal-multigol-ci/bin/python -m pip check
/tmp/sisal-multigol-ci/bin/python research/multigol-parser-v1/tools/build_schema.py
git diff --exit-code -- research/multigol-parser-v1/schemas
/tmp/sisal-multigol-ci/bin/python research/multigol-parser-v1/tools/check_offline.py
~~~

Il download delle dipendenze è setup separato. Il runner vieta DNS, socket e
richieste libcurl, prima di importare i test. Anche un tentativo intercettato
fa fallire la suite. Non è richiesto alcun token o servizio esterno.

I test usano un clock di replay dichiarato per gli archivi (16 ottobre 2026):
serve a rendere la lettura riproducibile anche su runner con orologi differenti.
Non cambia l'orologio di sistema o i timestamp della fonte e non dimostra
prezzi attuali né una registrazione prepartita.

tools/build_examples_and_proofs.py rigenera esempi e illustrazioni dai soli file
salvati; non rigenera le trascrizioni manuali o i tempi di acquisizione.
Il workflow dedicato è .github/workflows/multigol-parser-v1.yml.

L'acquisizione pubblica è stata effettuata una sola volta fuori dalla suite.
Nessuna API a pagamento o soggetta a quota, servizio, abbonamento o costo aggiuntivo.
Pubblicazione esclusivamente su branch di ricerca per revisione, nessun deploy.
