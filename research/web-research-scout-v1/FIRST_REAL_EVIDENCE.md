# Prima evidenza web reale — esito bloccato

Branch: research/web-research-scout-v1-first-real-evidence-20261012.
Base: f114b32bc58339978949303edfd39b80a3f1a274.

**Nessuna nuova informazione calcistica autentica ottenuta.** La raccolta è stata fermata ai prerequisiti di accesso e diritti. Non si dichiara completata la prima acquisizione, né verificato un claim.

## Unica fonte candidata

Arsenal FC, homepage candidata https://www.arsenal.com/, robots candidato https://www.arsenal.com/robots.txt. È un host diverso dai sette già bloccati; nessuno di questi è stato contattato nuovamente.

La selezione si basa sul campo website presente nella documentazione football-data.org già conservata nel workspace. Si tratta di un **esempio di documentazione**, non di una nuova risposta API, una certificazione attuale del dominio o una mappatura delle squadre. Il riferimento al file e il suo hash sono nel rapporto; non viene ricopiata la documentazione integrale. Nessun nuovo team ID o player ID creato. Non è stato individuato un URL di articolo verificabile.

| Requisito | Esito effettivo | Conseguenza |
|---|---|---|
| Identità ufficiale attuale della fonte | Candidata, non revisionata in questa fase | Nessun claim dichiarato ufficialmente confermato. |
| HTTPS autorizzato nell'ambiente | Host assente dalle regole locali e dalla lista effettiva riportata dal runtime; stato enforcement del runtime unknown | Non assumere autorizzazione o un nuovo HTTP403 del sito. |
| Trasporto del collector | Proxy configurato; destinazione finale non attestabile | Il lettore conserva il rifiuto fail-closed; nessun bypass o fallback diretto. |
| Condizioni d'uso e licenza | Non verificabili nell'ambiente; nessun documento fornito dall'operatore | Nessuna autorizzazione alla raccolta editoriale dedotta dalla gratuità. |
| robots | Non acquisito | Nessun permesso di automazione dichiarato. |
| Conservazione dei metadati | Non verificata | Nessun titolo, estratto o corpo salvato. |
| Attribuzione richiesta | Non verificata | Nessuna presunzione che URL e data bastino ai requisiti del titolare. |
| Articolo / disponibilità giocatore | Non acquisiti | Categoria, descrizione, date e hash del documento restano null. |

Non è stata effettuata **alcuna richiesta alla fonte**, nemmeno a robots o terms. Non abbiamo osservato un rifiuto HTTP di Arsenal: target_http_status e proxy_http_status sono null. Sono stati verificati i prerequisiti locali con i normali strumenti di runtime, senza cambiare proxy, CA, configurazione cloud o protezioni del collector. L'assenza dall'allowlist e il rifiuto applicativo del proxy sono distinti dall'accessibilità del sito in altri ambienti.

Il sito non viene aggiunto al registro attivo come fonte approvata. Non vengono cercati altri club, mirror, archivi, IP alternativi o canali capaci di aggirare il blocco.

## Tre livelli distinti

| Livello | Esito | Cosa manca |
|---|---|---|
| Evidenza calcistica autentica acquisita legittimamente | **No** | Documento, provenienza e diritti verificabili. |
| Claim verificato secondo il contratto | **No** | Fonte/identità, revisione, pubblicazione e prova originale. |
| Dato utilizzabile per analisi prepartita | **No** | Oltre ai requisiti precedenti, evento futuro verificato e disponibilità temporale dimostrata. |

[Rapporto diagnostico della fonte](reports/first-real-source-check.json): osservazioni locali autentiche sul blocco, **non un'evidenza calcistica**, non una risposta del tool MCP e non una prova del comportamento del sito. observed_at indica quando sono stati controllati i prerequisiti; non sostituisce pubblicazione o acquisizione di un articolo.

Non esiste un nuovo evento futuro con identità verificata in questa attività. I due eventi del 12 ottobre non vengono riutilizzati come futuri: il controllo negativo usa solo l'ora reale, dopo i kickoff conservati, e attende temporal_unverified. Nessun override dell'orologio, proroga di identità o nuovo identificativo Sisal/API-Football/football-data.org.

## Stato dello Scout

Non sono soddisfatte le condizioni per preparare una prova revisionata, aggiungere claim o attivare una nuova revisione della cache. La revisione attiva rimane identica al commit base. Il contratto corrente dei claim richiede una chiave evento e una mappatura: non inserire valori fittizi per rappresentare un documento standalone.

Il [JSON dei controlli negativi del probe](reports/first-real-existing-event-negative-probes.json) contiene vere chiamate locali al componente esistente, con clock reale e sola cache conservata. Entrambi gli eventi già iniziati devono risultare temporal_unverified, teams vuoto e zero nuove richieste web. Questi controlli **non** collegano Arsenal ai due eventi e non sono sostituti di una nuova prova autentica.

Tutti gli indicatori rimangono diagnostic_only=true, ready_for_analysis=false, ready_for_quant=false, statistics_usable_in_production=false.

## Test, CI e file

Si eseguono solo le regressioni pertinenti: pin HTTPS, guardia offline e MCP/CLI, più validazione JSON/schemi/hash e scansione anti-segreti. Il resoconto puntuale è in [first-real-validation.json](reports/first-real-validation.json). Nessuna nuova fixture calcistica per simulare il raggiungimento dell'obiettivo; i test preesistenti mantengono le loro etichette sintetiche.

La CI esistente resta invariata e usa la guardia Linux senza rete. Il pattern del workflow comprende il nuovo branch. **Esito remoto non verificato**: l'API GitHub era già bloccata e non viene ritentata senza una nuova autorizzazione; un risultato locale non viene chiamato CI verde.

File aggiunti soltanto:

- FIRST_REAL_EVIDENCE.md — questo dossier.
- MANUAL_IMPORT_PROPOSAL.md — procedura futura, non implementata.
- reports/first-real-source-check.json — osservazioni locali e precondizioni.
- reports/first-real-existing-event-negative-probes.json — output reali del probe, soltanto negativi.
- reports/first-real-validation.json — verifiche eseguite e classificazione dei dati.

## Limiti e prossimo passo

La raccolta live attraverso il proxy resta incompatibile con l'attestazione di destinazione richiesta dal lettore attuale; non è stata indebolita. Identità ufficiale, termini, robots, licenza e attribuzione del candidato non sono verificati. Nessun evento nuovo o mappatura nuova creato.

Il passo possibile dopo la revisione è ricevere dall'operatore **un documento autentico insieme alle prove dei diritti e della provenienza**, seguendo [MANUAL_IMPORT_PROPOSAL.md](MANUAL_IMPORT_PROPOSAL.md). La procedura è solo progettata; non aggiunge un importer o un tool di rete. Se la documentazione è insufficiente, mantenere il blocco.

Nessuna modifica a main, produzione, server.py, Scout, Analyst, Quant, Railway, istruzioni cloud, cache, dipendenze o workflow. Nessun costo infrastrutturale aggiuntivo, servizio, abbonamento, processo permanente, merge o deployment. Fermarsi dopo la pubblicazione e attendere Antonio.
