# Rapporto di sicurezza

## Confini di fiducia

Tool diagnostico locale su stdio, cache e registro curati dall'operatore. I contenuti dei siti sono dati non attendibili. Non esistono interprete JS, shell generata, LLM, istruzioni ricavate dal web o tool di raccolta esposto via MCP. Il cliente non sceglie URL/cache/clock. Il trasporto stdio non è un servizio remoto autenticato; accesso e permessi dipendono dal processo locale.

| Rischio | Controllo implementato | Prova offline / limite |
|---|---|---|
| SSRF / domini contraffatti | HTTPS, host esatto ASCII, nessun userinfo/porta/query/fragment; risorsa esatta nel registro; rifiuto traversal/encoding ambiguo/IP/host interni | URL ostili e omografi respinti; non basta l'allowlist di dominio. |
| DNS rebinding | Tutte le risposte DNS devono essere globali, anche IPv6; seconda lettura deve coincidere; socket diretto fissato a un IP pubblico, TLS/SNI per hostname ufficiale | Test DNS privati/misti/mapped, cambiamento e connessione fissata. Nessuna prova live del trasporto diretto. |
| Proxy / CA | CA di sistema e TLS verificato; proxy configurato determina rifiuto, mai fallback diretto | proxy_target_integrity_unverified. Le prove iniziali di CONNECT403 restano separate dalla versione finale del collector. |
| Redirect a destinazione privata | Nessun redirect seguito, neppure verso un altro sito ufficiale; Location non restituita | Test 302 a metadata IP e handler di rifiuto. |
| Sovraccarico | timeout15s, risposta256000byte, rifiuto compressione; JSON-LD max8blocchi/16000caratteri; cache2MB/file,16MB/bundle,128file,256claim | File, risposta e conteggi oltre soglia respinti. |
| Rate limit | Lock POSIX condiviso per dominio, ≥5s o crawl-delay revisionato;429/Retry-After impone backoff ≥60s, nessun retry | Test limite, crawl-delay, budget corrotto fail-closed e429. Rate limit locale, non multi-host. |
| Prompt injection | Estrazione deterministica, pattern di quarantena italiano/inglese; nessuna esecuzione di istruzioni o JS | Tentativi non restituiti come claim; euristica non universale. |
| Segreti / errori | Nessun header auth/cookie/token provider; categorie d'errore chiuse, niente errori grezzi; osservazioni minimizzate; input/output schema; errori SDK tool sanitizzati | Test API key/Bearer/JWT/GitHub/AWS/private key/query e input MCP malformati. |
| Disinformazione / rumor | Distinzione fonte ufficiale/stampa e confermato/riportato/probabile; team canonici, review e hash | Claim sintetici ufficiali verificati solo in modalità test; rumor e probabili mai diventano ufficiali. |
| Disponibilità storica | Orario pubblicazione distinto dall'acquisizione; cutoff esclusivo, revisione già disponibile, scadenza | Unknown/date-only/future/post-kickoff/old publication bloccati o non confermati. |
| Manomissione cache | Revisioni content-addressed, hash di ogni file, controllo symlink/traversal, attivazione atomica completa | Snapshot mancanti/alterati, pointer symlink, aggiornamenti concorrenti e revisione coerente. |
| Diritti dei contenuti | Contenuti non raccolti senza terms/retention/robots revisionati; HTML solo transitorio, corpo mai archiviato | Tutte le fonti consegnate non approvate. robots accessibile non sarebbe una licenza. |
| Traffico nascosto dei test | Guard Python DNS + Linux seccomp fail-closed sui processi test e figli | Socket libc nativo negato; SDK stdio reale funziona via IPC. Nessun download nei test. |

## Minimizzazione e scansione

Artefatti reali: URL candidati, ID canonici/provider dai riferimenti precedenti, orari di verifica, hash e ricevute di accesso negato. Nessun titolo o articolo autentico acquisito. Le prove sintetiche contengono descrizioni artificiali senza nomi di giocatori reali.

Il collector non salva il corpo dei robots; produce soltanto permessi per le risorse note e crawl-delay. Per una pagina consentita conserva al massimo titolo di160caratteri, timestamp/data, URL, SHA del corpo transitorio e stato; tutto richiede ulteriore revisione prima di essere un claim. Nessuna conservazione di HTML integrale, header o stack trace.

scripts/scan_secrets.py scandisce **tutti i file pubblicabili del nuovo prototipo** con pattern; restituisce conteggi senza mostrare corrispondenze. scripts/validate_artifacts.py controlla JSON e hash e verifica che injection/segreti/contenuti esclusi non compaiano negli artefatti pubblicati. I test negativi costruiscono stringhe artificiali a runtime; nessuna credenziale reale viene usata o persistita.

Questa scansione non dimostra l'assenza di qualsiasi possibile segreto. Non è DLP universale. Il repository non richiede credenziali reali; il runner rimuove variabili provider/token/secret dal contesto dei figli e il processo MCP di test le omette.

## Vincoli rispettati

Nuovo branch da main; file aggiunti solo nella cartella di ricerca e workflow dedicato. server.py, Scout, Analyst, Quant, configurazioni Railway e istruzioni cloud attive non modificati. Branch History invariato. Nessun provider live interrogato, nessun servizio creato o costo introdotto. Tutti gli output mantengono diagnostic_only=true, ready_for_analysis=false, ready_for_quant=false, statistics_usable_in_production=false.

## Rischi residui

La cache è fidata rispetto all'operatore: una riscrittura deliberata di documenti e hash non è una revisione indipendente. Non ci sono firme publisher né certificazione legale automatica. Accesso ai siti, terms e robots restano non verificati. Fatti reali, integrazione History, autenticazione HTTP, identità giocatori e backtest non sono validati in questa fase.

Nessuna ripetizione degli accessi negati, IP alternativo, cambio proxy/CA, servizio esterno, aggiramento di paywall o modifica cloud effettuati. Richiedere revisione di Antonio prima di ogni integrazione.
