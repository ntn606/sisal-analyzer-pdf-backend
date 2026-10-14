# Contratto V1 e policy

Versione schema: 1.0.0. Schemi chiusi (additionalProperties=false), dimensioni
limitate, FormatChecker effettivo, timestamp ISO 8601 con offset obbligatorio.
Controlli date-time e URI locali espliciti, indipendenti dagli extra opzionali
di jsonschema. Per i timestamp si accetta il sottoinsieme RFC3339 con T/Z
maiuscoli, offset valido e secondi 00–59; leap seconds non supportati.
Gli URI sono assoluti, ASCII/percent-encoded, senza credenziali userinfo.
Nessun riferimento JSON Schema remoto. Rigenerazione riproducibile:
tools/build_schemas.py. Ogni modifica del contratto richiede revisione/versionamento.

## Identità

identity.match_id e gli ID delle squadre sono canonici, stabili e namespaced.
Nomi/abbreviazioni non identificano una squadra. La categoria distingue senior
maschili, femminili, U19, U20, riserve e altro. Le due squadre devono avere ID
distinti e categoria coerente. competition contiene ID, nome e stagione.

match_date è la data locale del kickoff, non la data di analisi. kickoff_utc e
kickoff_local rappresentano lo stesso istante; timezone è un nome IANA.
Offset, data locale e conversione ZoneInfo devono coincidere. Un'ora locale
inesistente durante il cambio DST viene rifiutata. Per un'ora ambigua l'offset
esplicito e la corrispondenza con UTC identificano l'istanza.

verification=verified e proof sono indispensabili. Un ID provider può comparire
soltanto in una mappatura dichiarata verified con prova, ID ufficiali, collegamenti
alle due identità canoniche, competizione canonica, stagione e kickoff coerenti.
I codici delle competizioni dei provider restano distinti da quelli canonici.
sisal è null se la coppia palinsesto/avvenimento non è verificata; analogamente
providers può essere vuoto. Nessun ID ufficiale viene inventato per riempire campi.

La validazione controlla coerenza e attestazioni: non analizza automaticamente il
documento originale né certifica le associazioni dichiarate dall'operatore.

## Provenienza e tempi distinti

Ogni fonte contiene source_id, uri, content_sha256, published_at (anche null),
observed_at obbligatorio, availability_verified, verification e data_origin.
Hash e URI fanno riferimento al documento minimizzato/revisionato nell'archivio
dell'operatore; il modulo non scarica documenti. Negli esempi URI urn:synthetic
e hash identificano fixture sintetiche, non risposte di provider.

published_at è la pubblicazione della specifica informazione, non la creazione
di una pagina generica. observed_at è il primo momento documentato di rilevazione
dell'informazione nel corpus considerato; non va sostituito con la rilettura odierna
di un vecchio file. availability_verified è un'attestazione revisionata, non
deducibile dalla data della partita. Pubblicazione <= rilevazione <= analysis_at.
Se la pubblicazione è sconosciuta, resta null: la rilevazione verificata prova
soltanto che il dato era disponibile a quel momento, non in epoche precedenti.

analysis_at <= orologio effettivo < kickoff. Anche dati esclusi dai fatti
utilizzabili non possono introdurre pubblicazioni/rilevazioni successive all'analisi.
Se il momento di disponibilità non è dimostrabile, non si può utilizzare il dato
per simulare un'analisi passata. Non si genera nessuna data per superare un blocco.

## Quote e mercati

L'evidenza odds contiene market, decimal in stringa decimale (>1) e valid_until
eventualmente null. publication/rilevazione e stato sono nella fonte.

Freschezza V1: massimo 3600 secondi dall'istante più antico fra pubblicazione
conosciuta e rilevazione; verifica all'analisi e all'istante di registrazione.
Una nuova rilevazione non ringiovanisce una pubblicazione vecchia nota. Se noto,
valid_until deve essere successivo alla rilevazione e all'istante del controllo:
non può estendere la policy. Una rilevazione non verificata non rende la quota
aggiornata. La durata di un'ora è una policy prudente del prototipo, non una
garanzia del bookmaker, del prezzo disponibile o della possibilità di esecuzione.

Il valore non viene calcolato, combinato, interpolato o completato quando manca.

| family | selection |
|---|---|
| 1x2 | home, draw, away |
| double_chance | home_draw, home_away, draw_away |
| over_under | direction over/under, line numerica, scope match/home/away |
| btts | yes/no |
| multigoal | min/max interi inclusivi, scope match/home/away |
| combination | legs tipizzate, void_policy esplicita |
| my_combo | legs tipizzate, void_policy esplicita |
| unsupported | label e required_data, per mercati ulteriori non implementati |

Ogni mercato dichiara period. Sono rappresentabili regular_time, first_half,
extra_time e penalties; l'evaluator V1 supporta solo regular_time.
Multigol 2–3 significa 2 <= gol <= 3; non equivale a Over 1.5, perché 4 gol
vincono Over e perdono Multigol. L'identità di un mercato deve coincidere
esattamente con quella della quota, compresi periodo e scope.

Le combinazioni/My Combo ammettono 2–10 legs semplici dello stesso evento.
Non si assumono mercati disponibili: quote_id può essere null.
Un candidate scelto richiede una quota corrente verificata. watch può rimanere
senza quota; no_bet non ha selezione. Il modulo non sceglie uno stato autonomamente.

## Statistiche, notizie e classificazione

statistics: team_id, sample_size, results, sample_start/end, limits.
Ogni risultato conserva match_id namespaced per provider, avversario, competizione,
stagione, venue, kickoff, stato, gol 90 minuti e propria fonte.
Campione e intervallo devono coincidere con i record; solo FINISHED con punteggi
completi. Massimo 180 giorni dall'analisi; nessuna partita al/dopo cutoff.
Duplicati e conflitti bloccano il campione utilizzato: nessuna deduplicazione
silenziosa che possa nascondere disaccordi. Il campione minimo non è fissato a cinque
in A1; un solo risultato non diventa un campione di cinque. Limiti espliciti.

news: team_id, category (absence/suspension/probable_lineup/official_lineup/statement),
basis (official/reported/probable), descrizione breve e player_ids se noti.
Non si sintetizzano identità, informazioni mediche o dichiarazioni mancanti.
Una formazione probabile non può essere confirmed né official_lineup.

Ogni evidenza dichiara assessment confirmed/hypothesis/contradictory/missing.
use_as_evidence=true richiede confirmed, fonte verificata e tempi validi.
Ipotesi/contraddizioni restano contesto escluso; i dati mancanti hanno fonte e
payload null con motivazione obbligatoria. I riferimenti dei mercati candidati
possono utilizzare soltanto evidenze ammesse. Notizie o statistiche facoltative
mancanti sono limiti dichiarati; identità non verificata o quota indispensabile
mancante sono blocchi. Favorable_reasons, risks e reasons restano testi forniti:
la loro fondatezza richiede revisione umana, non viene provata dalla sintassi JSON.

## Esiti e valutazione

result include identità canonica completa, stagione e kickoff, status,
regular_time, extra_time, penalties, finished_at, source, settlement e
settlement_proof. Gol e identità non vengono inferiti da nomi o dai rigori.
Risultato verificato disponibile entro il controllo, completamento noto e coerente.

Regole experimental-90min-v1, autorità diagnostic_not_bookmaker:
1X2, doppia chance, BTTS, Multigol e Over/Under interi/mezzi punti.
Linea intera uguale ai gol => void (push) secondo questa regola sperimentale.
Linee asiatiche a quarti => not_evaluable. Periodi diversi dai 90 minuti =>
not_evaluable. I supplementari/rigori non sostituiscono regular_time mancante.

Combinazioni: congiunzione valutata soltanto se tutte le legs sono valutabili.
Cartellini, corner, marcatori, tempi parziali ecc. richiedono dati ulteriori.
Una leg void necessita di void_policy nota; unknown => not_evaluable.
void_all è una regola di esercizio esplicitamente scelta, non una regola
attribuita a Sisal. Nessun ricalcolo della quota o regolamento del pagamento.

Un rinvio/cancellazione non è automaticamente void; una istruzione di void
verificata richiede settlement_proof separata.

Da A1.1, il valutatore applica le regole del mercato soltanto a candidate.
watch => not_evaluable con watch_not_approved_selection, con o senza quota;
no_bet => not_evaluable con no_bet_decision. Le osservazioni watch restano nel
registro per analisi successive e non sono selezioni approvate. Questi controlli
precedono anche l'istruzione di void. Per no_bet, il motivo no_selection_recorded
di A1 è sostituito da no_bet_decision; nessun campo o firma API cambia.
I controlli preliminari di integrità, fonte, identità e tempi mantengono priorità.
Nessuna valutazione V1 certifica un pagamento ufficiale del bookmaker.
