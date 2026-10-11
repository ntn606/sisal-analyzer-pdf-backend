# Architettura e integrazioni proposte

## Componenti implementati

| Fase | Implementazione | Comportamento |
|---|---|---|
| Source Discovery | cache/sources.json, cache/source-matrix.json | Registro manuale di candidati; nessun crawler, pagina menzionata ≠ copertura verificata. |
| Evidence Collection | collect.py, extract.py, comando collect --live | Un URL preapprovato, con gating di permessi e sicurezza; soltanto metadati, nessun fatto verificato automaticamente. |
| Verification | probe.py, claim.schema.json, reviewed-proof.schema.json | Controlli deterministici su revisione, identità, integrità, disponibilità temporale e conflitti; nessun LLM. |
| Evidence Cache | cache.py | Bundle versionato per hash, attivazione atomica del puntatore, lettura coerente e limitata in memoria. |
| Diagnostic Probe | CLI e mcp_server.py | Consultazione della sola cache; un tool stdio football_web_research_v1_probe. |

La discovery è curata dall'operatore. Non inferisce licenze dal fatto che una pagina sia accessibile. Non esistono crawling, ricerca su motori esterni, fetch periodici o servizi permanenti.

## Contratti e revisione

Input pubblico: palinsesto, avvenimento, match_date (data Sisal Europe/Rome). Nessun URL, percorso cache, comando, chiave o override del clock è ricevuto dal tool.

Ogni claim contiene canonical team ID, chiave evento, categoria, ambito claim_key/effective_at, valore limitato, descrizione sintetica, source ID, URL esatto, pubblicazione, acquisizione, scadenza, origine e hash della prova. Le nove categorie sono contenitori: risultati, classifica, infortuni, squalifiche, disponibilità, formazioni probabili/ufficiali, calendario, notizie. Nessuna di queste categorie ha dati web reali verificati nella consegna.

Una prova revisionata lega tutti i campi sostanziali dell'affermazione tramite SHA-256; identifica revisore e momento di revisione, e richiede prova esplicita per la formazione ufficiale. Una revisione è un'attestazione dell'operatore, non una firma del sito o un certificato indipendente. Una mera stringa simile al nome di una squadra non crea associazioni.

Il collector non genera questi claim. Estrarre un titolo o datePublished non dimostra il significato, la squadra citata o l'attualità della notizia. Il passaggio da metadati a claim necessita revisione umana del contenuto consentito e dell'identità; non è automatizzato.

La cache attiva include manifest e cinque documenti locali. Nuove prove revisionate aggiungono evidence/<id>.json. Per prepararle, costruire un dizionario completo di documenti JSON, validare i contratti e chiamare EvidenceCache.activate(documents) da un processo locale fidato. Nessun upload o modifica della cache è esposto via MCP. Le revisioni storiche non si sovrascrivono. Se manca un file o cambia un hash, il probe blocca l'uso delle prove.

## Stati e tempo

- verified: affermazione ufficiale, espressamente confermata, revisionata e valida per identità/tempo; nei test positivi è sintetica.
- reported_unconfirmed: indiscrezione, stampa, probabile formazione o data di pubblicazione sconosciuta.
- conflicting: valori diversi per lo stesso team, categoria, oggetto e data; entrambe le fonti restano visibili.
- not_found: assenza nella cache consultata, non prova che non esistano infortuni o notizie.
- source_stale: scadenza superata o pubblicazione più vecchia di 24 ore.
- source_blocked: accesso negato, permessi di conservazione/uso non verificati.
- identity_unverified, temporal_unverified, data_unverified: blocchi separati su mappatura, evento iniziato o integrità/contratto.

Gli input temporali richiedono fuso orario e sono normalizzati in UTC. Date di sola giornata restano publication_date, mai mezzanotte inventata. published_at=null resta sconosciuto e impedisce la verifica prepartita. Cutoff min(ora_verifica, kickoff) strettamente esclusivo: acquisizione e pubblicazione devono precederlo; anche la revisione deve precedere la verifica e seguire l'acquisizione. Pubblicazione successiva all'acquisizione viene respinta. Anche ricevute di accesso acquisite dopo il cutoff non vengono presentate come disponibili nel passato.

Finestra iniziale conservativa: massimo 24 ore dalla pubblicazione e dall'acquisizione, con scadenza esplicita anche più breve. Una nuova acquisizione non ringiovanisce una vecchia pubblicazione. Nessuna affermazione è utilizzabile al kickoff o dopo. Le probabili formazioni restano non ufficiali anche con fonte ufficiale. eligible_pre_match è solo un controllo temporale per confrontare i claim; **non** autorizza Analyst o produzione.

Conflitti fra versioni con oggetti/ambiti diversi non sono risolti semanticamente. Duplicati con identico ID/contenuto sono contati una volta; stesso ID con contenuto diverso blocca la richiesta.

## Confine con History V2

Studiato il commit **68a704878a42c58920ce9294798406a1eacddbcb**, senza cherry-pick, merge, importare motori o ripetere la suite History. identity-references.json conserva soltanto le proiezioni di identità, percorsi e hash dei tre artefatti originali per candidato. Sono riferimenti alla revisione precedente, consultabili nel branch History; non nuove prove di calendario e non statistiche importate.

Il controllo locale lega evento e riferimenti tramite hash. Non rilegge il branch remoto, non può certificare autonomamente la revisione precedente. L'output dichiara current_event_verified=false e upstream_statistics_imported=false.

Interfaccia futura proposta, **non implementata**:

1. Identity Adapter restituisce attestazione revisionata di evento e di entrambe le squadre, canonical ID, provider ID, competizione, UTC kickoff, riferimenti e validità.
2. History Provider fornisce risultati/forma con match ID, competizione, punteggio nei 90 minuti, fonte e disponibilità temporale.
3. Uno strato diagnostico separato presenta history e claim web in sezioni distinte, senza trasformare indiscrezioni in conferme né dedurre indisponibilità dall'assenza di notizie.
4. Una revisione successiva stabilisce criteri specifici per categorie, mapping giocatori, scope degli aggiornamenti e disponibilità per backtest.

MCP SDK effettivamente testato: **mcp==1.30.0**. Schemi JSON Draft 2020-12 locali; input/output pubblici pubblicati da list_tools, output validato a ogni probe. Trasporto stdio soltanto; nessun HTTP autenticato, installazione in Railway o collegamento ad Analyst implementato. Costi nuovi: zero; usare il workspace esistente e interrompere il processo al termine.
