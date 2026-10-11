# Rapporto sicurezza — History V2 Secure HTTP

Perimetro: servizio diagnostico isolato, cache-only, senza import di server.py o accesso ai provider. Nessun deploy, merge o modifica Railway. Gli engine originali e i test originali sono conservati. Risultati aggiornati in reports/secure-test-summary.json.

| Controllo | Implementazione / prova |
|---|---|
| Autenticazione obbligatoria MCP | Bearer su ogni POST /mcp; token errato/assente 401, segreti assenti bloccano startup. Test SDK non autorizzato e HTTP diretto. Healthz è eccezione pubblica minima documentata. |
| Segreto e confronto | Repr omette token; solo digest confrontati a tempo costante. Token reali non usati. Token sintetici generati nel test e non conservati nei report. |
| DNS rebinding | Host e Origin esatti controllati prima dell’SDK; TransportSecuritySettings.enable_dns_rebinding_protection=true. Test host contraffatti, Origin null/estranei, forwarded header ostili e host Railway health-only. |
| Errori sicuri | Nessun input ostile, header, token, errore grezzo o stack trace nei payload d’errore. Input MCP prevalidato, errore sintetico interno sanitizzato, startup generico. Access log disabilitato; SDK CRITICAL. |
| Dimensioni / concorrenza | 16KiB anche chunked, encoding compresso rifiutato, 4 richieste in volo, 429 con Retry-After, timeout cooperativo20s, Uvicorn32/1worker. Test limiti e timeout. |
| Integrità catalogo | Manifest content-addressed completo, attivazione atomica POSIX; copia privata per revisione. Test hash/snapshot/puntatore, symlink, mapping ambiguo, concorrenza HTTP reale durante attivazione, rollback. |
| Prove sintetiche | Origine real_saved e review locale richieste; rifiuto prove synthetic prima dell’attivazione. Un campo origin o hash da solo non prova autenticità: writer/operatore è una radice di fiducia. |
| Tempo e freschezza | Controllo per richiesta, senza risposta cached oltre kickoff; test al kickoff, dopo e stale. Pubblicazione revisioni non rinnova timestamp. |
| Nessun traffico provider | Guard globali socket.connect/connect_ex e getaddrinfo: solo loopback/IPC. Contatori zero tentativi esterni. Credenziali provider eliminate nei processi test; nessun download. |
| Minimizzazione Sisal | Solo tre anchor originali esatti, href documenti consentiti, target _blank, testo limitato; rifiuto attributi ignoti, duplicati, markup annidato, commenti, query e frammenti. Pagine complete mai pubblicate. |
| Scansione pubblicabile | Pattern JWT, chiavi GitHub/AWS/Google/Azure/OpenAI/Slack, private key, Bearer, URL credenziali, assegnazioni/query; decoding HTML/URL. Scansione PDF con estrazione testo + byte, evidenze, fixture, esempi, report e staged additions. Report solo path/rule; nessun valore trovato stampato. |

Il runner riproducibile verifica anche il codice backend con richieste simulate. Le copie regression aggiunte rendono i precedenti 103 test dei due prototipi eseguibili in una checkout nuova senza directory esterne. Codice test identico agli originali; l’HTML storico del fixture regression è stato minimizzato conservando gli anchor originali e SHA originale in provenance.json. Nessun originale fuori dalla checkout è stato modificato.

Limiti residui: nessun OAuth; client SDK con Bearer verificato, client remoto ChatGPT non verificato. HTTPS e hostname finale dipendono dal futuro edge e vanno verificati prima di attivare il servizio. Healthcheck Railway non provato su un servizio reale. Nessuna firma di revisione; nessuna difesa da writer/host compromesso. Immutabilità del volume va applicata nell’infrastruttura. Timeout thread cooperativo, non kill forzato. Scansione dei formati noti non garantisce assenza di qualsiasi segreto sconosciuto, specialmente in PDF compressi/metadati arbitrari. Nessuna automatic acquisition né egress firewall di servizio creato: codice HTTP cache-only e assenza di credenziali provider sono il primo isolamento; una futura policy di rete è raccomandata. Copertura sportiva limitata ai precedenti dossier; la prima pubblicazione dei risultati rimane sconosciuta.

Il materiale salvato può essere scaduto all’istante reale corrente. I test congelati dimostrano la correttezza del replay e del protocollo, non freschezza attuale. Per dati freschi servirà un incarico di acquisizione separato e autorizzato; questo branch non lo esegue.

La scansione completa del codice rileva quattro fixture negative intenzionali con placeholder sintetici. Le eccezioni sono **solo per sorgenti test `.py` revisionati e con SHA-256 esatto**, e richiedono la stessa categoria rilevata: ogni modifica invalida l’eccezione. Nessuna evidenza JSON/HTML/PDF può ricevere un’eccezione. Il report espone path, hash, categoria e motivo, mai i valori; tre test verificano applicazione, invalidazione e divieto sulle prove. Nessun blocco di Push Protection viene aggirato.
