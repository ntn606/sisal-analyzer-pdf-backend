# Secure HTTP Diagnostic — isolato e cache-only

Questo branch estende il commit `6bd9b719b4e3548d05282a560ec4cb1d95297b1b` senza cambiare il backend. Trasporto verificato con **mcp==1.30.0** e **uvicorn==0.54.0**; il servizio rifiuta SDK differenti. Un solo tool: `football_history_v2_probe(palinsesto, avvenimento, match_date)`. Gli ID sono stringhe numeriche; la data è ISO `YYYY-MM-DD`.

Restano invarianti `diagnostic_only=true`, `ready_for_analysis=false`, `ready_for_quant=false`, `statistics_usable_in_production=false`. Nessuna quota, previsione o probabilità viene restituita. Provider e Identity Adapter vendorizzati rimangono byte-identici.

## Installazione, revisione e avvio proposto

Dal root del repository:

```bash
python3.12 -m venv /tmp/history-v2-test-venv
/tmp/history-v2-test-venv/bin/python -m pip install -r research/history-v2-mcp-diagnostic/requirements-ci.lock
/tmp/history-v2-test-venv/bin/python research/history-v2-mcp-diagnostic/scripts/verify_offline.py
```

Per un futuro servizio dedicato, dal root `research/history-v2-mcp-diagnostic`:

```bash
python -m pip install -r requirements-http.txt
python -m history_v2_probe.revisions --source . --store /data/history-v2
python -m history_v2_probe.http_server
```

Il secondo comando **non acquisisce** dati: pubblica atomicamente solo i file già esistenti. Deve essere eseguito dall’operatore prima dell’avvio, dopo la revisione delle prove. Il lettore HTTP non ha endpoint di caricamento, attivazione o amministrazione.

Configurazioni obbligatorie:

| Variabile | Contratto |
|---|---|
| `HISTORY_V2_MCP_TOKEN` | Segreto locale al servizio; token casuale URL-safe di almeno 32 byte, codificato in 43–256 caratteri `[A-Za-z0-9_-]`. Non è una chiave dei provider. Nessun valore reale creato o salvato in questa attività. |
| `HISTORY_V2_REVISION_ROOT` | Directory operatore delle revisioni; es. `/data/history-v2`. |
| `HISTORY_V2_ALLOWED_HOSTS` | Host esatti, separati da virgola; es. hostname assegnato al servizio Railway, senza protocollo/percorso. Porta eventuale esplicita. Nessun wildcard. |
| `HISTORY_V2_ALLOWED_ORIGINS` | Origini esatte autorizzate, con HTTPS e senza slash finale. Vuoto rifiuta ogni Origin presente; l’assenza di Origin è consentita ai client server-to-server. HTTP ammesso solo su localhost/127.0.0.1 per test. |
| `PORT` | Porta 1–65535; default 8000. Bind `0.0.0.0`, un worker. |

La configurazione priva di token, Host, directory o revisione valida impedisce l’avvio. Nessun fallback verso token dei provider o autenticazione disattivata. Il factory ASGI è `create_http_app`; usare l’entrypoint documentato per mantenere i limiti Uvicorn.

## Protocollo e client

Percorso esatto `/mcp`, Streamable HTTP **stateless**, risposte JSON. Supporta initialize, notifications/initialized, ping, tools/list e tools/call. POST con Content-Type JSON e Accept compatibile MCP. GET/SSE persistente, sessioni, server notifications, risorse, prompt e pagination non sono offerti. Gli altri metodi restituiscono errori sicuri. I client SDK 1.30 con `httpx.AsyncClient(headers={"Authorization": "Bearer " + token})` e `streamable_http_client` sono stati verificati su TCP loopback reale, non soltanto ASGI simulato.

Ogni POST MCP richiede `Authorization: Bearer <token>`. Token assente o errato: HTTP 401, challenge `WWW-Authenticate: Bearer`, nessun valore riflesso. Token in query/cookie non accettati. Confronto a tempo costante dei digest; repr della configurazione non contiene il segreto. Static Bearer **non implementa OAuth**, issuer o discovery. Client che richiedono OAuth, inclusi eventuali configuratori remoti ChatGPT, non sono dichiarati compatibili. Verificare se il client previsto consente header Bearer preconfigurati; altrimenti progettare OAuth separatamente prima dell’integrazione. Nessuna prova con client remoto o Railway è stata eseguita.

DNS rebinding abilitato esplicitamente anche nell’SDK; barriera esterna Host/Origin esatti prima dell’SDK evita log degli header ostili. Non si fidano X-Forwarded-Host, Forwarded o proxy headers. Il TLS termina sul futuro edge Railway; test HTTP in chiaro solo loopback. L’applicazione non termina TLS né promette protezione di un collegamento interno esposto impropriamente.

`GET /healthz` è l’unica eccezione senza Bearer, intenzionale per il healthcheck. Host autorizzati del servizio più `healthcheck.railway.app` **esclusivamente su questo percorso**; nessuna eccezione per Origin. Risposta minima: stato, diagnostic_only, cache_only. Nessuna credenziale, ID squadra, percorso, dettaglio degli errori o API. Una revisione/puntatore non caricabile produce 503. Uno snapshot valido ma scaduto resta leggibile e healthz 200: la freschezza viene valutata per tool call e restituisce source_stale. Liveness/readiness non certifica freschezza calcistica.

## Revisioni e integrità

`ACTIVE.json` contiene schema e SHA-256 della revisione. Directory `revisions/<sha256>/REVISION.json`: manifest completo dei file con hash, schema e base della review locale già esistente. Il nome è il digest dei **byte del manifest**, deterministici. Non è una firma né la prova dell’approvazione di Antonio.

Il publisher usa staging, fsync, rename, lock advisory tra publisher e `os.replace` di ACTIVE; una revisione esistente non è sovrascritta. Prima dell’attivazione verifica tutti i file, ancore, origini real_saved, review e limiti. Symlink, traversal, file mancanti, hash alterati, JSON duplicati e prove sintetiche vengono rifiutati. Il runtime carica i byte verificati in una **copia privata**; ciascuna richiesta tiene il riferimento alla stessa revisione fino al termine. Cambiamenti nel volume non possono modificare una copia già caricata. Nuove richieste vedono la revisione nuova solo dopo il caricamento completo. Un puntatore nuovo invalido blocca: non si ripiega silenziosamente sulla revisione precedente.

Le revisioni del volume sono immutabili **per contratto operativo**: mount read-only nel lettore, writer separato e accesso amministrativo protetto. Hash, permessi e copie private non difendono da un operatore/host compromesso che può scrivere tutto e ricalcolare prove. L’identità è rivalidata dagli engine, anche con manifest valido; mapping ambiguo => identity_unverified, senza statistiche.

Revisioni complete possono contenere prove ormai scadute: pubblicarle non rinnova acquired_at. Età evento massima 1h, snapshot 24h, finestra risultati 180 giorni; cutoff prepartita e rispetto alla verifica. Al kickoff e dopo: temporal_unverified con storico vuoto. Backtest: osservazione disponibile entro, non data della prima pubblicazione. La revisione usata compare in `provenance.catalog_revision`. Per il rollback operatore: ripubblicare una fonte conservata, oppure verificare la revisione precedente con RevisionStore.load e sostituire atomicamente il puntatore; mai editare i record della revisione.

## Limiti e prove offline

Barriera: 16 KiB per body, limite anche chunked, nessuna decompressione, massimo 4 richieste MCP in volo senza coda; eccedenza 429/Retry-After 1. Deadline 20s per ingestione/handler cooperativo. Uvicorn: un worker, massimo 32 connessioni/task, keep-alive 5s, access log disattivato. Il worker thread Python non può essere terminato forzatamente in sicurezza: una verifica CPU bloccata può superare la deadline, mantenendo la capacità occupata fino alla conclusione. Limiti del processo e timeout dell’edge restano necessari; non si dichiara un hard timeout su codice Python arbitrario.

Revisione: massimo 2048 file, 5MB per file, 64MB totali; copie private e dataset richiedono memoria e spazio temporaneo. Il publisher concorrente è coordinato su filesystem POSIX locale. Non si dichiara un’attivazione globale simultanea su più pod/regioni o storage non POSIX. Una sola replica è il primo perimetro proposto.

`verify_offline.py` esegue i test precedenti conservati, test nuovi, schemi e scansione. Tutte le suite hanno un blocco globale dei socket e DNS esterni; HTTP e SDK comunicano realmente solo su loopback. Credenziali dei provider rimosse dal worker; token HTTP sintetici effimeri non memorizzati. Test positivi HTTP usano dati reali salvati con orologio di replay congelato, **non validazioni live nuove**. Test negativi modificano copie sintetiche e sono dichiarati tali.

Prove consultabili: [risultati completi](reports/secure-test-summary.json), [scambio autenticato reale locale](reports/http-authenticated-evidence.json), [casi HTTP](reports/secure-wrapper-tests.json), [schemi](reports/secure-schema-validation.json), [rapporto sicurezza](SECURITY_REPORT.md). CI offline riproducibile nella nuova workflow; l’esecuzione GitHub remota non è dichiarata completata prima della pubblicazione.

Esempio senza clock congelato: [http-current-time.json](examples/http-current-time.json), calcolato offline all’istante riportato nel JSON. Restituisce **source_stale**, storico vuoto e tutte le flag di produzione false. Le evidenze non vengono rese fresche ripubblicandole.
