# Risultati Secure HTTP Diagnostic

Branch di ricerca basato su `6bd9b719b4e3548d05282a560ec4cb1d95297b1b`. Nessuna acquisizione live, merge o deployment. Tutti i risultati seguenti sono test locali offline o replay di snapshot autentici salvati.

| Suite | Test | Errori / fallimenti / saltati |
|---|---:|---|
| provider | 42 | 0 / 0 / 0 |
| adapter | 61 | 0 / 0 / 0 |
| backend | 13 | 0 / 0 / 0 |
| wrapper | 96 | 0 / 0 / 0 |

**Totale: 212 test superati**, compresi i 162 precedenti. Il wrapper ne esegue 96: i 46 originali e 50 nuovi (23 HTTP, 16 revisioni, 8 minimizzazione/scanner, 3 policy eccezioni sintetiche). Zero test saltati. Suite eseguite in virtualenv nuova con dipendenze bloccate e mcp1.30.0; pip check senza conflitti.

Contatori del guard globale: **0 tentativi socket esterni e 0 DNS esterni**. Le connessioni HTTP sono TCP loopback reali; il figlio stdio originale è strumentato tramite sitecustomize e riportato nel riepilogo. Nessuna chiave provider è utilizzata; Bearer sintetici effimeri non sono conservati.

SDK HTTP: initialize, initialized, list_tools e call_tool per Coventry–Newcastle e Levante–Siviglia. Un solo tool con tre argomenti. Replay congelato delle stesse prove: diagnostic_available e 5/5 risultati per squadra. Gli scambi HTTP effettivi sono registrati con soli metodo, percorso e stato, senza header o token.

| Richiesta osservata | Stato HTTP |
|---|---:|
| POST /mcp | 200 |
| POST /mcp | 202 |
| POST /mcp | 200 |
| POST /mcp | 200 |
| POST /mcp | 200 |
| POST /mcp | 202 |
| POST /mcp | 200 |
| POST /mcp | 200 |

Test negativi: 401 senza token/errato; inizializzazione SDK non autorizzata; segreto assente impedisce startup; Host421 e Origin403; host healthcheckRailway ammesso solo healthz; body413 anche chunked; concorrenza429/Retry-After; timeout504; errori interni500 sanitizzati; JSON400 senza riflesso; percorso/query404; snapshot/hash/puntatore/symlink; mapping ambiguo; prove synthetic; stale; cutoff al/dopo kickoff; richieste parallele con switch revisioni e rollback.

**8 schemi** JSON verificati e **43 documenti** validati, inclusi risposte HTTP e manifest/puntatore generati. Scansione completa: testo dei sette PDF, evidenze, fixture, sorgenti, documentazione, report e CI. Nessun segreto reale rilevato; quattro sorgenti test con placeholder negativi sono eccezioni esplicite e bloccate su SHA, mai sulle evidenze.

La chiamata cache-only con orologio reale in [http-current-time.json](examples/http-current-time.json) restituisce source_stale, con storico vuoto: un replay positivo non certifica freschezza attuale.

Report completi: [suite e contatori](reports/secure-test-summary.json), [ogni caso wrapper](reports/secure-wrapper-tests.json), [prove HTTP](reports/http-authenticated-evidence.json), [schemi](reports/secure-schema-validation.json), [integrità](reports/secure-integrity.json), [scan](reports/security-scan.json), [sicurezza e limiti](SECURITY_REPORT.md).

CI aggiunta in `.github/workflows/history-v2-secure-http.yml`: checkout, Python3.12, install requirements-ci.lock, runner offline, schemi, scan, confronto produzione/engine col commit base. La workflow è riprodotta localmente; esito remoto GitHub non verificato prima del push.

Problemi aperti: static Bearer senza OAuth; compatibilità client remoti da confermare; TLS/hostname/healthcheck Railway non provati su piattaforma; revisione con review locale, non firma; immutabilità infrastrutturale da applicare; deadline thread cooperativa; dati salvati scaduti/copertura parziale/prima pubblicazione sconosciuta. [Proposta Railway](RAILWAY_PROPOSAL.md), soltanto preparata. Richiedere approvazione di Antonio prima di merge/deploy.
