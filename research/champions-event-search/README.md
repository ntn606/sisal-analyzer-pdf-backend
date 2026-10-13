# Correzione ricerca eventi Champions — 13 ottobre 2026

Branch: research/fix-champions-event-search-20261013.
Base main: 304cb2cf06d9f8f226eb89b701d3ec57beba6a38.

## Difetto riprodotto e causa

Usato il PDF ufficiale Sisal già conservato, acquisito l'11 ottobre 2026:
[fixture PDF](../../tests/fixtures/sisal-base-20261011.pdf),
[provenienza, hash e output precedenti](../../tests/fixtures/sisal-base-20261011-provenance.json).

Non è lo snapshot del 13 ottobre alle 22:06–22:07: quello non è disponibile nel workspace. Il PDF archiviato contiene però tutti e tre i medesimi eventi e consente di riprodurre il difetto, senza inventare eventi/quote o effettuare download.

Nel testo default di pypdf una riga effettiva diventa:

~~~text
EUCHL21.00 7,001,054,101,1836421 7213 Roma Real Madrid ...
~~~

Le quote sono emesse prima delle colonne Pal./Avv. dall'ordine interno degli oggetti PDF; parte dei numeri si concatena al palinsesto. La regex di extract_events pretende invece ORA seguito immediatamente da PALINSESTO AVVENIMENTO. Scarta questa riga valida e molte altre. Non è un filtro senior/giovanile né il limite 100: la selezione testuale era già applicata prima del limite.

Un difetto indipendente impedisce la ricerca per nome della competizione: "Champions" non è una sottostringa di "EUCHL". search_odds cerca il testo grezzo e non usa la regex d'identificazione, quindi trova Roma Real Madrid, Manchester City Paris e Feyenoord Como anche se get_matches li omette.

Nel PDF salvato main riconosceva188 eventi su472 righe valide, zero EUCHL. search_odds trova i tre eventi, una riga ciascuno. Anche pypdf in modalità layout conserva anomalie d'ordine: non è stato adottato come correzione non verificata.

## Modifica

get_matches ora legge le colonne spaziali del PDF Base tramite pdfplumber, separatamente dai prezzi:

- Intestazioni Ora, Manif., Pal., Avv. e le due Squadra identificano le colonne.
- Ricostruisce tempo, codice competizione, ID e nomi stampati; non deduce l'identità dalla somiglianza.
- Accetta anche codici numerici realmente presenti nel documento.
- Deduplica soltanto per coppia Pal./Avv.; identità discordanti bloccano la lettura.
- Legge tutte le pagine prima di filtro e limite. Le 472chiavi coincidono con il transcript spaziale già salvato.
- Non trancia il nome al primo numero interpretabile come quota.
- Unknown layout, PDF corrotto o PDF assente producono uno stato esplicito, senza una lista parziale presentata come completa.
- Indice in memoria limitato agli ultimi due contenuti PDF; testo e bytes letti dalla stessa pubblicazione della cache sotto lock.

Alias esatti "Champions", "Champions League", "UEFA Champions League" e codice EUCHL selezionano solo EUCHL. "Youth League", "UEFA Youth League" ed EUUYL sono separati. Nessuna equivalenza con codici femminili o codici aventi lo stesso prefisso. Una ricerca generica per squadra può mostrare più categorie: nomi stampati e codice restano distinti, senza attribuire automaticamente un nome senza suffisso a una squadra senior.

Firma MCP compatibile: query e limit invariati; nuovo offset opzionale con default 0. Il limite preesistente di 300 rimane. count continua a indicare tutti i risultati filtrati; returned_count, truncated e next_offset rendono visibile la paginazione. I vecchi campi time, manifestazione, match, palinsesto, avvenimento e raw restano; aggiunti competition, home_printed, away_printed e page.

Quando il PDF fisico non è più presente nella cache, get_matches restituisce source_not_ready, anche se resta del testo: evita di ricadere nel parser incompleto. Nessuna modifica al refresh o ai controlli di sicurezza.

## Risultati sul documento archiviato

| Ricerca | Prima | Dopo | Identità verificata nel PDF |
|---|---:|---:|---|
|Champions|0|18|Solo EUCHL|
|EUCHL|0|18|Solo EUCHL|
|Roma|0|2|Include 36421/7213; altra Roma distinta 36421/1159|
|Roma Real Madrid|0|1|EUCHL 36421/7213,21:00, Roma / Real Madrid|
|Manchester City Paris|0|1|EUCHL 36421/7210,21:00, Manchester City / Paris Saint-germain|
|Feyenoord Como|0|1|EUCHL 36421/7214,18:45, Feyenoord / Como|
|Tutti, mediante paginazione|188 riconosciuti|472|Nessuna chiave omessa o duplicata|

[Output corretti](corrected-results.json) e [test/report](test-results.json). Non si tratta di risultati live o di una verifica dell'app in produzione.

## Regressioni

**31 test passati, zero falliti o saltati**, di cui 13 regressioni API-Football preesistenti. Tre metodi di test eseguiti sul precedente server.py riproducono 5 fallimenti di asserzione attesi; sul codice corretto passano.

Copertura:

- PDF originale verificato per hash, tre eventi/nome/orario/ID e 18 EUCHL.
- Parità con search_odds; query Roma, nomi completi, alias e ID.
- Paginazione di tutte le 472 chiavi, copie delle risposte e codici numerici.
- Righe reali U20 e femminili preservate con nomi/codici originali.
- EUCHL/EUUYL/prefissi femminili distinti tramite test di classificazione dei soli codici: **nessun evento Youth League inventato**. La fixture non contiene righe EUUYL.
- MCP SDK 1.30.0 effettivamente usato: list_tools e call_tool accettano ancora query/limit senza offset.
- Tre output completi del parser Base coincidono con quelli prodotti da main, tranne il naturale cache_age_seconds.
- Extra e Combinate assenti: verificato il rifiuto source_not_ready, senza fabbricare prezzi.
- Scout continua a bloccare PDF vecchi e fogli mancanti. Il replay storico esplicito della politica resta blocked perché mancano Extra/Combinate.
- Fingerprint AST identici per **tutte** le funzioni preesistenti tranne get_matches, inclusi parser quote, aggregatore, Scout, Analyst e funzioni Football/History.
- Guardia Python e seccomp Linux: DNS e socket Internet nativi negati; nessun traffico esterno durante i test.

I PDF Extra/Combinate e lo snapshot aggiornato del 13 ottobre non sono disponibili: non si dichiara riprodotto uno Scout ready con tutti e tre i fogli o verificato il valore attuale di una quota. I parser di questi fogli non sono stati modificati.

## Riproduzione offline e CI

Python 3.12, dipendenze pin nello specifico lock CI:

~~~bash
python -m pip install -r research/champions-event-search/requirements-ci.lock
python research/champions-event-search/run_offline.py
~~~

Installazione precedente ai test; durante i test la guardia Linux viene ereditata dai subprocess. Fail-closed se non installabile. Nessuna credenziale reale richiesta o usata. I 13 test precedenti simulano il provider; i nuovi test calcistici usano il PDF autentico salvato. Non viene ripetuta la suite History V2.

Workflow dedicato [.github/workflows/champions-event-search.yml](../../.github/workflows/champions-event-search.yml), senza deployment o segreti. **CI remota non verificabile:** il tentativo autorizzato di leggere Actions tramite api.github.com è stato negato dal proxy (Forbidden). Non viene dichiarata verde sulla base dei soli test locali.

## File e vincoli

- server.py — solo import cache, nuovi helper di indice/ricerca e get_matches.
- tests/test_match_search.py — regressioni.
- tests/fixtures/sisal-base-20261011.pdf — documento originale archiviato.
- tests/fixtures/sisal-base-20261011-provenance.json — hash, provenienza, output main e chiavi indipendenti.
- research/champions-event-search/README.md — questo dossier.
- research/champions-event-search/corrected-results.json — risultati offline.
- research/champions-event-search/test-results.json — elenco dei test e classificazione.
- research/champions-event-search/run_offline.py — runner.
- research/champions-event-search/offline_guard/os_guard.py — seccomp.
- research/champions-event-search/offline_guard/sitecustomize.py — guardia Python.
- research/champions-event-search/requirements-ci.lock — dipendenze del controllo CI.
- .github/workflows/champions-event-search.yml — workflow offline.

main, Railway e produzione non modificati. Nessuna modifica a Scout, parser quote, Analyst, Quant o History V2; nessun nuovo servizio o costo infrastrutturale, acquisizione live, merge o deploy. Pubblicare solo il branch e fermarsi per la revisione.
