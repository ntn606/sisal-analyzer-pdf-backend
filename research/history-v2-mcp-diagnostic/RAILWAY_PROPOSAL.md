# Railway — proposta diagnostica separata, non eseguita

Questo documento propone un futuro servizio cache-only. **Nessun servizio Railway, variabile, deploy o backend è stato modificato. Merge/deployment richiedono la revisione e l’approvazione di Antonio.** Non acquistare o attivare risorse a pagamento in questa fase.

## Contratto del servizio

Root directory `research/history-v2-mcp-diagnostic`; Python3.12; mcp==1.30.0; uvicorn==0.54.0. Un tool `/mcp` su Streamable HTTP stateless JSON, autenticazione static Bearer, healthcheck `GET /healthz`. Bind0.0.0.0, PORT Railway. Gli output mantengono diagnostic_only=true, ready_for_analysis=false, ready_for_quant=false e statistics_usable_in_production=false. Nessuna chiamata provider, cron di acquisizione, quote o previsioni.

Build proposto:

```bash
python -m pip install -r requirements-http.txt
```

Avvio proposto, **solo dopo approvazione e preparazione del volume**:

```bash
python -m history_v2_probe.http_server
```

Il command avvia un worker, disabilita access log e trusted proxy headers, imposta timeout keep-alive 5s e limite32 connessioni/task. Il factory ASGI può essere importato per altri runner, ma il command sopra mantiene i limiti testati. HTTPS pubblico tramite edge Railway; non creare tunnel o bypass. Verificare in staging che il dominio assegnato e la connessione edge siano quelli attesi.

## Segreti e hostname

Nuovo segreto inbound `HISTORY_V2_MCP_TOKEN` inserito **solo** nel servizio dedicato tramite gestione segreti protetta, mai in Git/log/chat/commandline. Non riutilizzare le chiavi dei provider e non montarle: il lettore non ne ha bisogno. Un token URL-safe da 32 byte casuali soddisfa il contratto (43 caratteri codificati); distribuzione ai client per canale protetto. Rotazione: sostituire segreto, riavviare servizio, aggiornare i client; nessuna finestra di doppio token implementata.

Variabili nuove proposte, non impostate:

| Nome | Valore/azione proposta |
|---|---|
| HISTORY_V2_REVISION_ROOT | `/data/history-v2`, mount delle revisioni |
| HISTORY_V2_ALLOWED_HOSTS | **Hostname esatto assegnato al nuovo servizio**, senza schema, porta implicita443, slash o wildcard |
| HISTORY_V2_ALLOWED_ORIGINS | Origini HTTPS esatte dei client ammessi; può essere vuoto per client server-to-server senza Origin |
| HISTORY_V2_MCP_TOKEN | Segreto Bearer protetto, nessun valore suggerito |
| PORT | Porta fornita dalla piattaforma |

Non autorizzare `*.railway.app`, *.up.railway.app, arbitrary localhost o forwarded hostname. L’host `healthcheck.railway.app` è ammesso automaticamente **solo per GET /healthz**, mai per /mcp. Il healthcheck non supporta Origin estranei. Verificare in staging l’Host effettivo del healthcheck; se diverso, aggiungere un hostname esatto con test dedicato in una modifica revisionata, senza allargare l’allowlist.

Auth client verificata: SDK MCP 1.30 con header Bearer su ogni POST. Questo servizio non implementa OAuth/discovery. Compatibilità ChatGPT o altro configuratore remoto non ancora provata: se il client richiede OAuth, questa release non è pronta per quel collegamento e serve una progettazione successiva. Non attivare il servizio sperando che static Bearer soddisfi un client OAuth.

## Persistenza e pubblicazione delle evidenze

Volume POSIX locale, una replica. Layout ACTIVE.json + revisions/<SHA256>/REVISION.json + file ancorati. Preparare un bundle offline dopo review delle prove e scansione; il digest è integrità, non firma/certificazione. Il comando operatore:

```bash
python -m history_v2_probe.revisions --source /bundle/reviewed --store /data/history-v2
```

Nessun accesso provider viene effettuato. Staging, fsync e rename precedono `os.replace` del puntatore; writer coordinati con lock advisory. Il reader verifica una revisione completa e utilizza una copia privata coerente per ogni richiesta. Aggiornamenti concurrenti non mescolano snapshot, mapping o prove. Puntatore invalido blocca le nuove richieste; copie già in volo completano sulla revisione precedente.

Mount read-only nel reader dove possibile; writer offline separato con sole autorizzazioni necessarie. Se la piattaforma non permette writer separato/read-only sul volume, eseguire aggiornamenti con servizio fermo, poi riavviarlo dopo verifica: documentare questa limitazione, non dichiarare immutabilità infrastrutturale già attiva. Conservare almeno revisione precedente e bundle originale per rollback. Directory read-only/hash non proteggono da un amministratore compromesso.

Non attivare un acquisitore o un budget API in questo servizio. Un futuro acquisitore richiederà autorizzazione distinta, fonte/diritti/freschezza, credenziali separate e budget atomico condiviso con l’account Railway; il lettore resta cache-only. Il contenuto attuale è già osservato in ottobre 2026, soggetto a TTL 1h/24h e cutoff: un healthcheck sano non garantisce un campione fresco.

## Risorse e costi da valutare

Primo perimetro: una replica e un worker. Body16 KiB, richieste MCP4 in volo senza coda, 429Retry-After 1, deadline cooperativa 20s, file 5MB, revisione64MB / 2048 file. Budget iniziale suggerito da **misurare in staging**: 0.5–1vCPU, 512MiB–1GiB RAM, volume1GiB; le copie private per revisioni in volo e i dataset possono richiedere più memoria. Non sono benchmark certificati. Imporre un cap CPU/RAM e limiti edge prima di esporre il servizio; un thread Python non è interrompibile forzatamente dalla deadline ASGI.

L’app non richiede database, Redis o servizi aggiuntivi. Railway compute/volume/traffico possono avere costi e disponibilità legati al piano esistente; nessuna tariffa o gratuità è garantita, nessuna risorsa è stata creata. Verificare prezzi e disponibilità con Antonio prima di attivare. Non aggiungere repliche globali: l’atomicità testata è POSIX per richiesta e per singolo reader, non switch globale simultaneo.

## Healthcheck e monitoraggio sicuro

Path `/healthz`, timeout iniziale proposto 5s. Startup rifiuta configurazione segreti/host/store invalida. Risposta200 minima, nessun provider call; store invalido=>503. Freshness/cutoff sono valutati dalla tool call: un dataset scaduto può dare source_stale pur con healthz 200.

Access log disabilitato, SDK CRITICAL, nessuna stampa body/header/token/exceptiontext. L’ASGI mantiene contatori aggregati per codice sicuro (completed/unauthorized/host_not_allowed/etc.), senza endpoint pubblico metrics, ID utente o eventi. Monitoraggio futuro: health status, 401/429/5xx aggregati, tempo/p95 e memoria dal servizio/edge; exportmetrics richiede una modifica revisionata e accesso protetto. Non raccogliere header Authorization né payload MCP negli strumenti piattaforma.

## Gate prima di qualsiasi integrazione

1. Revisione di Antonio del branch e del rapporto sicurezza, senza merge automatico.
2. Test `python scripts/verify_offline.py`: tutte le suite precedenti, TCP MCP autenticato, guard senza egress, schemi e scan.
3. Client finale compatibile con Bearer, oppure progetto OAuth autorizzato e testato.
4. Prove aggiornate ottenute in un incarico separato; mapping locali revisionati e catalogo completo. Nessun cambio della data di acquisizione per superare la TTL.
5. Staging separato autorizzato: HTTPS, Host/Origin, healthcheck Railway, token assente/errato, fresh/stale, cutoff, RAM, carico e rollback. Nessun collegamento aScout/Analyst/Quant.
6. Solo con ulteriore approvazione attivare diagnostica remota. La promozione degli output per produzione/analisi resta fuori perimetro.

## Rollback proposto

Disabilitare solo il nuovo servizio diagnostico, senza modificare backend o variabili esistenti. Ripristinare la release precedente; per dati, validare e ripubblicare atomicamente il bundle precedente (stessoSHA); non riscrivere file dentro una revisione. Restart se necessario e verificare /healthz + richiesta diagnostica autenticata. Dati precedenti scaduti restano source_stale: rollback non rinnova prove. In caso di segreto esposto, ruotarlo e invalidare client; non bypassare la scansione o Push Protection.
