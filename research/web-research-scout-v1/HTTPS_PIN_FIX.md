# Correzione HTTPS — 12 ottobre 2026

Branch correttivo: **research/web-research-scout-v1-pin-fix-20261012**.
Base esatta: **5f18c73b1e79f442e18b127eb6ea49783deeb478**.
Il branch originale research/web-research-scout-v1-20261011 rimane invariato.

## Difetto e modifica

Collector verificava due volte gli indirizzi DNS pubblici ma chiamava HTTPSReader senza destination_addresses. Il lettore reale restituiva destination_pin_missing. Il precedente fake accettava parametri arbitrari e non controllava il contratto fra i due componenti.

Unica modifica al codice del componente: passare il set addresses già validato e riconfermato alla chiamata HTTPSReader.read, mantenendo timeout di 15 secondi e limite di 256000 byte. Nessuna risoluzione alternativa, fallback, rimozione di proxy o cambiamento del pinning.

Anche il fake preesistente ora richiede esplicitamente il parametro keyword destination_addresses; nessun test precedente rimosso o disabilitato.

## Dimostrazione prima e dopo

I cinque nuovi test sono stati eseguiti sul Collector del commit di riferimento **prima** della correzione, sotto guardia offline:

| Fase | Test | Passati | Falliti | Interpretazione |
|---|---:|---:|---:|---|
| Codice precedente |5|3|2|Regressione riprodotta: keyword mancante e destination_pin_missing dal lettore reale.|
| Codice corretto |5|5|0|Set approvato trasmesso; percorso HTTP simulato completato.|
| Suite finale del prototipo |107|107|0|Tutti i 102 precedenti più i 5 nuovi.|
| Regressioni backend |13|13|0|Test esistenti con provider simulati; nessuna modifica backend.|

Esito finale: **120/120 test passati, zero falliti o saltati**. La fase iniziale con due errori è la dimostrazione richiesta sul codice difettoso, non l'esito della consegna.

[Rapporto JSON completo](reports/https-pin-fix-tests.json): test con origine dei dati, risultati delle fasi e SHA-256 del Collector precedente/corretto. [Test nuovi](tests/test_https_pin_regression.py).

## Percorso realmente esercitato offline

Fonte editoriale sintetica approvata, hostname riservato club.scout.example, autorizzazioni/robots revisionati artificialmente e clock fisso. Due risoluzioni controllate restituiscono gli stessi due IP pubblici. Il test del contratto confronta esattamente URL, timeout, limite e set passato al reader.

Il secondo test usa **Collector, HTTPSReader, urllib opener, PinnedHTTPSHandler, http.client e socket.create_connection reali**. Il socket di sistema e il flusso TLS sono simulati in memoria. Verifica:

- Esattamente due risoluzioni dell'hostname tramite il resolver iniettato.
- Successiva getaddrinfo soltanto per il literal IP fissato: conversione locale simulata, nessuna nuova risoluzione dell'hostname.
- Connessione simulata solo all'IP approvato, porta 443, timeout di 15 secondi.
- Host HTTP e SNI corrispondenti all'hostname ufficiale della fonte sintetica.
- SSLContext reale con check_hostname=true e CERT_REQUIRED prima e dopo la richiesta.
- Nessun header di autenticazione o cookie.
- HTTP 200 e sola estrazione di metadati sintetici, sempre reported_unconfirmed: nessun fatto verificato automaticamente.

Nessun handshake TLS live o certificato di un sito reale viene dichiarato verificato: il trasporto è deliberatamente simulato.

I restanti casi bloccano il lettore reale prima di qualsiasi trasporto: DNS locale/metadata/mapped/misto, DNS modificato, proxy https/http/all configurato e Collector con live omesso. L'esistente test CLI senza --live rimane incluso e passato. Redirect, dimensione, timeout, rate limit e controlli sui contenuti restano coperti dalla suite preesistente.

## Riproduzione e sicurezza

Da research/web-research-scout-v1, con le dipendenze esistenti:

~~~bash
python scripts/run_offline.py --include-backend-regression
~~~

Il runner installa nei processi test la guardia DNS Python e seccomp Linux, ereditata anche dai figli MCP. Blocca socket Internet nativi, connessioni, x32 e io_uring; i nuovi test verificano solo IPC e trasporto in memoria. Nessuna acquisizione live, connessione esterna o credenziale reale nei test. Nessun servizio permanente o costo aggiunto.

11 schemi e 18 JSON di cache/esempio validati; hash della cache e scansione anti-segreti superati. Il workflow già presente include il nuovo branch tramite il pattern research/web-research-scout-v1-*: non occorre modificarlo. La CI GitHub remota non viene dichiarata verificata da questi risultati locali.

Cache, fonti, dati storici e riferimenti di identità non modificati. Non è stata ripetuta la suite History. Gli esempi reali precedenti restano esempi di limiti d'accesso, non notizie recuperate.

diagnostic_only=true, ready_for_analysis=false, ready_for_quant=false e statistics_usable_in_production=false invariati. Nessuna modifica a main, server.py, Scout, Analyst, Quant, Railway o istruzioni cloud; nessun merge o deployment. Attendere la revisione di Antonio.
