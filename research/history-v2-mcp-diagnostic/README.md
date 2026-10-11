# Estensione Secure HTTP

Il nuovo trasporto autenticato cache-only è descritto in [SECURE_HTTP.md](SECURE_HTTP.md), con [rapporto sicurezza](SECURITY_REPORT.md), [test aggiornati](reports/secure-test-summary.json) e [proposta Railway non eseguita](RAILWAY_PROPOSAL.md). I risultati sottostanti descrivono la precedente fase stdio e le acquisizioni salvate; non dichiarano nuove verifiche live.

# History Provider V2 — MCP diagnostico isolato

Due nuove catene reali verificate, oltre al precedente caso Atalanta–Venezia:

| Evento futuro | Competizione | Sisal Pal./Avv. | Fixture API-Football | Match FD | Risultati |
|---|---|---|---|---|---|
| Coventry–Newcastle, 12/10/2026 21:00 Europe/Rome | Premier League | 36411/1885 | 1557420 | 560597 | 5/5 + 5/5 |
| Levante–Siviglia, 12/10/2026 21:00 Europe/Rome | LaLiga | 36411/2282 | 1570407 | 564704 | 5/5 + 5/5 |

Entrambe le CLI originali in real_only restituiscono diagnostic_available e
verified_as_of_observation. I due kickoff equivalgono a 19:00 UTC.

- [Dossier Coventry–Newcastle](cases/coventry-newcastle/DOSSIER.md)
- [Dossier Levante–Siviglia](cases/levante-sevilla/DOSSIER.md)
- [JSON wrapper Coventry–Newcastle](examples/coventry-newcastle.json)
- [JSON wrapper Levante–Siviglia](examples/levante-sevilla.json)
- [Test e classificazione dei dati](reports/test-summary.json)
- [Proposta Railway](RAILWAY_PROPOSAL.md)

Gli ultimi cinque risultati sono quelli validi nel dataset acquisito, non una
certificazione di completezza di tutte le competizioni. Lo scope include PL/PD
e CL, ma tutti i venti risultati selezionati appartengono ai campionati nazionali.
Le altre coppe restano fuori copertura; all_competitions_complete=false.
La prima pubblicazione è sconosciuta. Le osservazioni reali dimostrano soltanto
che i risultati erano disponibili entro il controllo effettuato l'11 ottobre.

## Wrapper operativo

Un solo tool MCP, **football_history_v2_probe**, con tre argomenti:

```json
{"palinsesto":"36411","avvenimento":"1885","match_date":"2026-10-12"}
```

Contratti v1: [richiesta](contracts/request.schema.json),
[risposta](contracts/response.schema.json). Il client non passa fixture/team ID,
URL, credenziali, registry, evidenze, clock, mode o flag di verifica.

Il wrapper richiama Identity Adapter e History Provider V2 copiati byte-identici
in vendor/, senza riscriverli. Il catalogo e gli hash sono configurazione locale
revisionata. Hash/provenienza non trasformano una review arbitraria in una prova
autentica: non accettare un catalogo o registry forniti da un client MCP.
Le review presenti sono locali, basate sulle risposte ufficiali conservate.

Ogni risposta mantiene:

```json
{"diagnostic_only":true,"ready_for_analysis":false,"ready_for_quant":false,
 "statistics_usable_in_production":false}
```

Stati: diagnostic_available, identity_unverified, insufficient_history,
temporal_unverified, provider_unavailable, source_stale, data_unverified,
data_conflict. In caso di blocco nessuna statistica è abilitata. I conteggi reali
rimangono disponibili quando il motore ha potuto valutarli. Nessuna quota,
pronostico, probabilità o value bet entra nella risposta.

L'orologio UTC del servizio viene usato per ogni richiesta. A kickoff incluso,
il tool restituisce temporal_unverified/event_already_started e non riusa
statistiche della cache. PDF e fixture devono essere acquisiti entro un'ora;
gli snapshot FD entro 24 ore; finestra delle partite 180 giorni. Le osservazioni
dei risultati devono essere precedenti all'istante corrente. La cache conserva
il dataset compilato, indicizzato per hash dei file; controlli di identità,
integrità, disponibilità e freschezza vengono rieseguiti ad ogni richiamo.

Il tool usa solo prove/cache locali e **non effettua chiamate API automatiche**.
Nessuna credenziale è necessaria per consultare il caso salvato. Quando le prove
scadono, source_stale è l'esito corretto: non presentare l'esempio archiviato come
una nuova verifica live.

## Esecuzione e replay

Python 3.12; CLI/core con libreria standard. Per MCP usare SDK 1.30.0:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-mcp.txt
.venv/bin/python -m history_v2_probe --mcp --root "$PWD"
```

Trasporto stdio, senza listener HTTP, tunnel o modifica al backend. Il client MCP
avvia il processo e comunica sul suo stdin/stdout. In alternativa JSON via CLI:

```bash
.venv/bin/python -m history_v2_probe --palinsesto 36411 --avvenimento 2282 \
  --match-date 2026-10-12
```

Per riprodurre gli esempi dopo la scadenza della fonte, usare il timestamp di
request-asof-observation.json del relativo dossier:

```bash
python -m history_v2_probe --palinsesto 36411 --avvenimento 1885 \
  --match-date 2026-10-12 --replay-at 2026-10-11T20:26:19.083091+00:00
```

Il replay è etichettato offline_replay; --replay-at non è ammesso con --mcp.
Il timestamp dell'esempio va scelto dopo la verified_at del dossier; il controllo
blocca prove acquisite successivamente all'istante di replay. Il replay non
attesta nuova freschezza live. La factory server accetta un servizio iniettato
solo per test/configurazione locale fidata, mai tramite argomenti MCP.

## Acquisizione e rete

Le prove live sono state completate **prima** di realizzare il wrapper. Totale
acquisizione: 3 GET Sisal, 3 API-Football (status + 2 fixture), 28 football-data.org
(4 team, 2 eventi, 2 calendari, 20 osservazioni uniche). CL riutilizzata dalla
cache fresca del primo dossier. Nessun 429, retry o servizio a pagamento.
Gli errori di piano precedentemente osservati sono limiti aperti, non aggirati.

scripts/acquire_replicas.py, build_replicas.py e observe_replicas.py sono strumenti
operatori di ricerca. I collector preesistenti sono preservati in scripts/reused/.
Non vengono importati dal server MCP. Non rieseguire acquisizioni o rigenerare
mapping senza rivedere le prove; le richieste già tentate non sono ripetute
automaticamente e i timestamp originali restano nella cache.

history_v2_probe.transport.ProviderTransport è un helper opzionale **non
collegato al tool MCP**. Usa solo endpoint ufficiali allowlisted, HTTPS verificato,
X-Auth-Token/x-apisports-key da variabili protette, timeout 20 secondi, limite body
5 MB, nessun redirect, cache di successi 15 minuti e status 60 secondi. Non conserva
header auth o messaggi grezzi degli errori. Distingue HTTP 200 con errore del corpo,
auth, piano, quota, timeout, schema e dati che riecheggiano una credenziale.

Senza callback operatore di prenotazione atomica del budget, ogni richiesta live
è rifiutata. La callback deve coordinare l'intero account, inclusa Railway:
il lock locale non è presentato come coordinamento distribuito. Limite locale
8 secondi fra GET; Retry-After/reset rispettati senza attesa/retry automatico;
riserva API-Football 20/giorno e 2/minuto. Header giornalieri contraddittori non
possono aumentare il saldo locale. Il helper è verificato con risposte simulate;
la replica live usa i collector già sviluppati, non questo nuovo helper.

## Test e limiti

```bash
.venv/bin/python scripts/run_tests.py
```

46 test nuovi offline, con origine dei dati dichiarata per caso: replay dei due
dossier reali, mutazioni sintetiche negative, provider simulati e scambio MCP SDK
stdio con clock di replay fissato. Nessuna API live durante i test. Le regressioni
precedenti sono 61 adapter, 42 provider e 13 backend: totale **162 passati**.
Sono validati anche 38 documenti JSON contro i relativi contratti.

server.py, Scout, Analyst, Quant, le variabili Railway e i PDF di produzione
rimangono invariati. Nessun tool è registrato nel backend. I PDF in questo
laboratorio sono copie di prove ufficiali conservate, non modifiche all'estrazione.
Il branch di ricerca serve per revisione; non è stato eseguito alcun merge.

## Minimizzazione della pagina Sisal

GitHub push protection ha rilevato una Azure Function Key nell’HTML pubblico
completo. Il push iniziale è stato respinto; nessun bypass è stato usato. Il
branch conserva ora soltanto i tre elementi anchor originali che collegano i
PDF autorizzati, byte-per-byte dalla risposta reale, con SHA-256 della pagina
completa e dell’estratto. Non viene generato HTML sintetico e nessuna chiave
è copiata negli estratti. Il collector futuro minimizza in memoria prima di
scrivere il file. I PDF e le prove delle identità rimangono autentici. Dettagli:
[rapporto minimizzazione](reports/sisal-page-minimization.json).
