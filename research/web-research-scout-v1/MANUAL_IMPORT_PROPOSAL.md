# Importazione manuale legittima — proposta, non implementata

Il documento dell'operatore può evitare una raccolta di rete, ma il solo possesso del file non prova autenticità, diritto di conservarlo o permesso di ripubblicare estratti. Nessun file autentico è stato fornito o importato nell'attività corrente.

## 1. Pacchetto minimo dell'operatore

Richiedere, tramite caricamento legittimo del documento:

- Documento originale proveniente dalla fonte ufficiale, senza copie sintetiche, modifiche editoriali o credenziali.
- URL originale e identità del titolare/publisher. Se il documento è privato o richiede autenticazione, fornire prova che l'uso richiesto è autorizzato; non tentare autonomamente accessi.
- Condizioni d'uso/licenza applicabili, versione/data e riferimenti oppure autorizzazione scritta verificabile, inclusi limiti di conservazione, estrazione, pubblicazione e attribuzione.
- Data di pubblicazione, solo quando dimostrabile dal documento o da una prova attendibile; per una data di sola giornata conservare la precisione di giornata.
- Data dell'accesso originale dell'operatore e metodo di acquisizione, con indicazione di quali elementi siano attestati e quali incerti.
- Obiettivo di minimizzazione: singolo fatto consentito, metadati necessari, ambito squadra e nessun dato medico dedotto.

Non mettere credenziali, cookie, header o account personali nel pacchetto. Una licenza deve essere rivedibile per il progetto; non sostituirla con l'affermazione «la pagina è pubblica». robots riguarda eventuali raccolte automatiche, non concede copyright o diritti di riuso. L'import offline non effettua crawling; se robots è sconosciuto, annotarlo e non trasformare l'import in autorizzazione a scaricare altre pagine.

## 2. Ingresso in quarantena, nessuna rete

Un eventuale importer futuro dovrà essere separato dal backend e dalla cache approvata:

1. Trattare il file e il manifest come input non attendibili; limiti di dimensione, nomi di percorso confinati, controlli MIME/magic e niente symlink/traversal.
2. Non seguire link, immagini, riferimenti esterni, redirect o risorse incorporate. Nessuna esecuzione di JS, macro, script o istruzioni della pagina.
3. Calcolare SHA-256 del file realmente ricevuto e registrare l'orario reale d'ingresso nel workspace. Tale orario non sostituisce la pubblicazione o la disponibilità precedente.
4. Scandire contenuti e metadati per segreti e injection, riportando solo categorie d'errore. Rifiutare o mettere in quarantena dati sensibili senza copiarli nei log.
5. Non conservare un articolo integrale nel repository. Il file originale rimane fuori dagli artefatti pubblicabili, solo per il tempo e negli spazi consentiti; se la conservazione non è autorizzata, non trattenerlo.
6. Prima di estrarre/salvare metadati o una sintesi fattuale, rivedere l'autorizzazione relativa a queste operazioni. Hash, URL e riassunto non sostituiscono una licenza.
7. Salvare solo il minimo consentito: fonte, URL, tipo, sintesi fattuale breve, pubblicazione con precisione dichiarata, acquisizione, hash, revisore, riferimento ai diritti e limiti/attribuzione.

L'autenticità deve essere controllata con elementi indipendenti disponibili legittimamente: firma del documento se presente, identità della fonte, URL/provenienza revisionata, confronto con una copia ufficiale consentita o altra attestazione verificabile. PDF/screenshot e dichiarazione del caricante, da soli, possono lasciare lo stato non confermato.

## 3. Identità e significato

Verificare separatamente la fonte, la squadra citata e l'eventuale giocatore. Una similarità di nome, stemma o abbreviazione non crea una mappatura. Usare ID ufficiali e mapping esplicitamente revisionati quando disponibili; in loro assenza non inventare ID o presentare identità verificata.

Distinguere il testo effettivo: «in dubbio», «assente», «ritorno previsto» e «disponibile» non sono sinonimi. Non diagnosticare lesioni, gravità, tempi di recupero o intenzioni del club. La comunicazione di una testata resta una notizia riportata anche se allegata dall'operatore.

Valore sconosciuto, pubblicazione sconosciuta o solo una data rimangono espliciti; non usare mtime del file, data del caricamento o data della partita per completarli.

## 4. Documento standalone e disponibilità temporale

Il contratto corrente dello Scout richiede un evento identificato. Un eventuale documento autentico senza un nuovo evento futuro verificato deve restare **standalone**, fuori da claims.json e dal probe per evento. Il contratto standalone è da progettare/revisionare prima di implementare l'import; non usare event_key inventate o vecchi eventi come placeholder.

Conservare i tre livelli distinti:

- Documento autentico acquisito con diritti dimostrabili: provenienza verificata, senza automatica verifica dei singoli claim.
- Claim revisionato: fonte, identità, fatto, precisione temporale e licenza soddisfano il contratto applicabile.
- Disponibilità prepartita: nuovo evento verificato, pubblicazione/acquisizione/revisione realmente disponibili prima del cutoff, freschezza e identità valide.

Un documento ricevuto oggi non dimostra che il backend lo avesse prima di una partita passata. Anche una pubblicazione datata prima del kickoff non certifica la precedente disponibilità interna del dato. Senza prove sufficienti mantenere reported_unconfirmed, identity_unverified o temporal_unverified secondo il problema; verified solo se il contratto e tutte le sue condizioni sono soddisfatti.

## 5. Eventuale promozione dopo una nuova revisione

Soltanto quando fonte, diritti, identità ed evento soddisfano i requisiti:

- Preparare prova minimizzata e revisione umana; conservare hash, riferimento dei diritti, origine manuale e orari distinti.
- Concordare prima il contratto per l'origine manuale: non rinominare un documento sintetico o non revisionato in real_saved.
- Validare input, prova e output; deduplicare e rendere visibili versioni/conflitti.
- Costruire una revisione completa e coerente della cache, attivarla atomicamente con il componente esistente e verificare il probe senza rete.
- Lasciare diagnostic_only=true e tutte le readiness false; nessuna promozione in Analyst/Quant o produzione.

Nessuna di queste operazioni di import/promozione viene implementata o eseguita ora. Richiedono un documento autentico e la revisione di Antonio; non comportano automaticamente merge, deployment, servizi cloud o costi.
