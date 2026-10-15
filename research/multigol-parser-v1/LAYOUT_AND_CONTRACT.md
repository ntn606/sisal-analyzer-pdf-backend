# Layout, contratto e blocchi V1

## Layout effettivamente verificato

Un solo snapshot reale di Calcio Multigoal per Data, hash in README/provenance.
Due pagine 842 × 595 punti PDF; 40 righe evento per pagina. La geometria di tutte
le pagine viene riconosciuta prima di rilasciare le selezioni del target.
Sono controllate manualmente le quote di tre eventi, non tutti i 2400 prezzi/celle.

Coordinate: punti PDF, origine in alto a sinistra, box [x0, top, x1, bottom].
Nel documento osservato:

| Campo | Intervallo x |
|---|---|
| Ora | 13,1906 – 35,0306 |
| Manif. | 35,0306 – 65,0306 |
| Pal. | 65,0306 – 86,0306 |
| Avv. | 86,0306 – 107,0306 |
| Squadra 1 | 107,0306 – 209,0304 |
| Squadra 2 | 209,0304 – 311,0304 |
| 1–2 | 311,0304 – 328,1904 |
| Altro di 1–2 | 328,1904 – 345,4704 |
| 2–4 | 518,0304 – 535,1904 |
| Altro di 2–4 | 535,1904 – 552,4704 |
| 3–6 | 690,4704 – 707,7504 |
| Altro di 3–6 | 707,7504 – 725,0304 |

Questi numeri documentano lo snapshot e i box della prova manuale; il parser
non li usa come costanti per attribuire quote. Le delimitazioni vengono rilevate
dalle linee fisiche che attraversano l'intestazione della pagina in esame.
Le righe di dati vengono delimitate dalle linee orizzontali della tabella.
I separatori verticali di ogni riga devono coincidere con quelli delle colonne
dell'intestazione: un corpo spostato o senza griglia viene bloccato.

L'intestazione supportata richiede:
- titolo esatto CALCIO MULTIGOAL PER DATA;
- colonne identitarie Ora, Manif., Pal., Avv., Squadra 1 e Squadra 2;
- fasce numeriche esplicite nella riga superiore e nella sottocolonna inferiore;
- ogni fascia seguita dalla propria colonna Altro;
- accordo delle due intestazioni e separatori fisici verificabili.

Nel PDF, riga intestazioni inferiore y=73,80–84,24; fascia superiore
y=63,24–73,80. Celle dati di 36421/31108: y=96,72–107,16.
Celle di 36421/6028: y=130,68–141,12. Il box vuoto 1–6 di quest'ultima riga
è x=449,0304–466,1904; 7,50 appartiene alla successiva cella Altro,
x=466,1904–483,4704. Un semplice elenco sequenziale di numeri le confonderebbe.

Una crop può includere frammenti di glifi della riga superiore: il parser usa
contenimento completo dei box delle parole, non testo tagliato sul bordo.
Il controllo indipendente sulle intestazioni usa analogamente glifi originali
interamente contenuti, evitando di leggere i frammenti “Da ...” come nuova fascia.

## Campi delle selezioni

Ogni selezione conserva event_key, market_type=multigol_match, scope=match,
range_min/max, selection=range oppure altro, decimal_original e decimal,
raw_cell_text, stato e motivi, pagina, cell_bbox, word_boxes, header_bbox,
band_bbox, layout_sha256, source_sha256, source_url, retrieved_at,
publisher_timestamp_text e published_at_utc.

range_min/max descrivono la fascia a cui si riferisce il mercato a due esiti.
Per selection=altro NON descrivono un intervallo in cui dovrebbero cadere i gol
di Altro. L'altro esito resta collegato a quella coppia di colonne; non viene
trasformato in Over/Under, in un intervallo arbitrario o in un mercato squadra.

decimal_original preserva la stringa pubblicata, compresi virgola e zeri finali.
decimal sostituisce soltanto la virgola con il punto: nessun float/interpolazione.
Un intero come 12 rimane 12. Un valore <=1, illeggibile, multiplo o che attraversa
un bordo non è una quota accettata: decimal rimane null e viene dato il motivo.

Cella vuota: entrambi i valori decimali null, status missing, motivo empty_cell.
Non si deduce se sia temporaneamente sospesa o mai offerta. Una fascia senza
intestazione non viene inventata; l'elenco dei mercati rispecchia le fasce
pubblicate. Le assenze non provocano lo scorrimento dei prezzi successivi.

## Identità e data

La selezione del target usa esclusivamente Palinsesto + Avvenimento. Poi controlla
nomi distinti e ordinati casa/ospite, codice competizione, data e ora stampati.
Solo gli spazi dei nomi sono normalizzati; mai somiglianza, alias o rimozione
di U19/U20, Women, B o Futuro. Eventi omonimi con ID diversi restano distinti.
Un evento non trovato non viene sostituito con una riga dal nome simile.

Duplicati della coppia ID: blocco duplicate_event_key. Disaccordi su identità,
data o prezzi: conflicting_event_records. Nessuna scelta automatica del primo.
Una riga identitaria illeggibile blocca il documento: potrebbe nascondere una
collisione del target. Una quota illeggibile blocca soltanto la cella interessata.

La categoria non è una colonna stampata: category=null, not_explicitly_printed.
Non si deduce “senior” dal solo codice/nome. Una richiesta che pretenda la
verifica di category viene bloccata come category_not_verifiable_from_this_layout.
competition_code preserva esattamente Manif.; nessun mapping automatico verso
UEFA/API-Football/football-data.org o una competizione dal nome simile.

Le intestazioni di data riportano giorno della settimana, giorno e mese.
L'anno, quando omesso, è risolto esplicitamente dal contesto della pubblicazione:
un solo candidato compatibile con weekday e finestra -2/+120 giorni.
year_explicit=false e basis dichiarano l'inferenza contestuale, che non è una
certificazione esterna del calendario. Ambiguità/giorno incoerente: blocco.
La finestra limita il riconoscimento, non estende la validità di quote o identità.

L'ora è preservata come local_time, con timezone/kickoff_utc null: il PDF non
documenta la timezone nel corpo. Il footer stampato non viene convertito in UTC.
Acquisizione, pubblicazione e data di svolgimento sono tre informazioni diverse.

## Casi supportati e blocchi

Supportati per il profilo per Data: box e ordine delle fasce rilevati su ciascuna
pagina, sottocolonne range/Altro, celle vuote, prezzi interi e decimali,
riordino/spostamento di colonne riconoscibile dalle intestazioni. Gli spostamenti
sono coperti da PDF sintetici; non si afferma di avere più layout reali verificati.

Non supportati:
- Multigoal per Manifestazione: non acquisito/non validato. Può richiedere
  un profilo proprio; il titolo diverso non eredita quello per Data.
- mercati Multigol squadra, casa/ospite o layout misti: blocco esplicito,
  nessuna attribuzione delle quote partita;
- PDF scansionati, OCR, righe multilinea, griglie senza separatori,
  intestazioni sconosciute/discordanti o range duplicati;
- categoria/identità canonica multi-provider e timezone non stampate;
- regolamento del periodo di settlement o significato contrattuale di Altro
  non presenti nel documento; period=null;
- quotazioni correnti/freschezza di un archivio: la lettura non certifica
  che un prezzo sia ancora disponibile.

Limiti di risorse: massimo 8 MB, 40 pagine e 15000 parole per pagina.
Non si tronca silenziosamente il documento quando un limite viene superato.
PDF assente/corrotto/non riconosciuto, timestamp di acquisizione futuro,
hash non corrispondente, coordinate di hash diversi, timestamp publisher
discordanti tra pagine o identità attesa incompleta producono blocked.

Il manifest è un'attestazione locale della provenienza, non una firma esterna.
Un proprietario che sostituisca sia PDF sia hash può falsificarli: le evidenze
pubblicate e la revisione indipendente restano necessarie.
Il parser non si connette a URL, non esegue contenuti PDF e non legge segreti.

## Compatibilità futura con Football Evidence A1.1

Riferimento A1.1: dd7d85116b0698e69b8e61b73d053fc723634238.
Nessuna dipendenza/importazione/copia di codice o schema da quel branch.

Per selection=range, un adapter futuro potrebbe costruire la struttura
A1.1 family=multigoal, selection={min,max,scope:match}, usando i limiti estratti.
Prima deve però verificare period, identità canoniche e categoria, fonte,
disponibilità temporale e freschezza della quota. Il prezzo letto non promuove
automaticamente una evidenza a confirmed/verified nel dossier A1.1.

Altro non ha una conversione automatica in una selezione Multigol delimitata
dello schema A1.1: serve un contratto/regolamento revisionato. Nessuna integrazione
diretta o modifica dello schema A1.1 in questa fase.

Una cella vuota/illeggibile non produce una evidenza odds utilizzabile:
l'eventuale adapter deve preservare lo stato mancante/bloccato e le sue ragioni.
Stati diagnostici e ready_for_* false restano obbligatori.
