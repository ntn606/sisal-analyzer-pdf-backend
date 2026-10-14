# Football Evidence & Validation V1 — Sisal Analyzer V3, fase A1

Prototipo Python locale, offline, indipendente dal backend. Organizza un dossier
fornito dall'operatore, controlla identità e tempi, registra la decisione ricevuta
prima del kickoff e valuta successivamente una selezione con regole deterministiche.

Non genera decisioni, probabilità, puntate, ROI o valore atteso. Le etichette
candidate, watch e no_bet descrivono una decisione fornita; candidate non autorizza
un'operazione. Tutti gli output mantengono diagnostic_only=true,
ready_for_analysis=false, ready_for_quant=false,
statistics_usable_in_production=false.

Base: main, commit 304cb2cf06d9f8f226eb89b701d3ec57beba6a38.
Nessun cherry-pick da altri branch. La correzione Champions 39f96d8 non è inclusa.
server.py, parser quote, Scout, Analyst, History V2, Quant e Railway sono invariati.

## Installazione e comandi locali

Python 3.12 su POSIX/Linux, senza servizio HTTP o server MCP.

~~~bash
python -m venv /tmp/sisal-a1
/tmp/sisal-a1/bin/pip install -r research/football-evidence-validation-v1/requirements-test.txt
cd research/football-evidence-validation-v1

/tmp/sisal-a1/bin/python -m football_validation validate /percorso/dossier.json
/tmp/sisal-a1/bin/python -m football_validation register /percorso/dossier.json --registry /percorso/registro
/tmp/sisal-a1/bin/python -m football_validation show UUID --registry /percorso/registro
/tmp/sisal-a1/bin/python -m football_validation verify --registry /percorso/registro
/tmp/sisal-a1/bin/python -m football_validation outcome UUID /percorso/risultato.json --registry /percorso/registro
/tmp/sisal-a1/bin/python -m football_validation verify --registry /percorso/registro --checkpoint /percorso/checkpoint.json
~~~

I comandi leggono esclusivamente file locali. Il modo predefinito real_only
rifiuta evidenze sintetiche. --mode synthetic_test è un opt-in esplicito per
esercizi sintetici; i record conservano sia il modo sia l'origine dei dati.
La CLI non offre parametri per impostare l'orologio o recorded_at.

La validazione restituisce status validated oppure blocked e motivazioni
strutturate. La registrazione ricontrolla il dossier sotto lock con l'orologio
effettivo. Un dossier approvato in precedenza può essere bloccato se nel frattempo
è scaduta una quota o è iniziata la partita. Una decisione no_bet può essere
registrata senza selezione o quote; non è valutata come previsione perdente.

## Schemi e interfaccia

I cinque schemi Draft 2020-12 sono in schemas/:

| Schema | Contratto |
|---|---|
| dossier.schema.json | Identità, evidenze, mercati candidati, decisione |
| validation.schema.json | Diagnostica di validazione di un dossier strutturalmente valido |
| record.schema.json | Envelope hash-chain per prediction oppure outcome |
| result.schema.json | Esito separato, identità completa, punteggi distinti |
| evaluation.schema.json | winning, losing, void oppure not_evaluable |

Errori di struttura iniziali producono una diagnostica minima blocked con
data_origin=unvalidated: non un record persistibile né il contratto completo
validation.schema.json. La CLI esce con codice 2 per dossier bloccati/errori
operativi, 0 per operazioni riuscite. Un outcome non valutabile viene conservato
come tentativo diagnostico separato; il comando riuscito non significa vittoria.

SCHEMA_CONTRACT.md documenta campi, mercati, timezone e policy.
LIMITATIONS.md documenta i confini di fiducia e le dipendenze mancanti.
INTEGRATION_PROPOSAL.md descrive la futura interfaccia, non attivata.

Interfaccia Python stabile per il prototipo:

~~~python
from football_validation import Registry, validate_dossier

report = validate_dossier(dossier, mode="real_only")
registry = Registry("/percorso/registro", mode="real_only")
prediction = registry.record_prediction(dossier)
outcome = registry.record_outcome(prediction["record_id"], verified_result)
checkpoint = registry.verify()
~~~

Registry.get verifica l'intero journal prima di restituire una copia del record.
evaluate controlla schema e hash dell'envelope, ma va chiamato con un record
ottenuto dal registro verificato: un hash isolato non certifica la storia.
Nessun metodo update/delete. Una correzione del risultato crea un altro outcome:
gli outcome possono divergere e il consumatore deve sceglierne esplicitamente uno.

## Esempi: tutti sintetici, nessun evento autentico

examples/dossier-synthetic-valid.json è completo: quote, campione dichiarato di
un risultato, formazione probabile esclusa, informazione mancante e contraddittoria,
motivazioni, rischi e decisione. Non contiene squadre, eventi o quote reali.

Il dossier è validato solamente nell'esercizio synthetic_test al clock fisso
2026-10-14T10:00:00Z. La prova è validation-synthetic-valid.json.
Non è una dichiarazione di validità attuale né di registrazione reale prepartita.

examples/dossier-synthetic-blocked.json conserva identità non verificata,
quota scaduta e disponibilità non verificata. Le motivazioni sono salvate in
validation-synthetic-blocked.json.

prediction-synthetic.json e outcome-synthetic.json dimostrano snapshot,
hash, link tra registrazioni e valutazione deterministica sul punteggio sintetico
2–1 nei 90 minuti. Gli orari fissi sono fixture dichiarate dei test.
result-synthetic.json separa esplicitamente 90 minuti, supplementari e rigori.

I test validano questi esempi e verificano gli hash. Il generatore
tools/build_synthetic_examples.py è esclusivamente un generatore di fixture:
non va usato su documenti reali, per acquisire dati o creare timestamp mancanti.

## Test e CI

Per riprodurre anche le regressioni backend, dalla radice del repository:

~~~bash
python -m venv /tmp/sisal-a1-ci
/tmp/sisal-a1-ci/bin/pip install -r research/football-evidence-validation-v1/requirements-ci.txt
/tmp/sisal-a1-ci/bin/python -m pip check
/tmp/sisal-a1-ci/bin/python research/football-evidence-validation-v1/tools/build_schemas.py
git diff --exit-code -- research/football-evidence-validation-v1/schemas
/tmp/sisal-a1-ci/bin/python research/football-evidence-validation-v1/tools/check_offline.py
~~~

Il download delle dipendenze è una fase di setup; schemi e test girano offline.
check_offline.py installa guardie su DNS, socket e curl_cffi prima degli import.
Ogni tentativo di rete causa il fallimento complessivo, anche se intercettato dal
codice. Nessuna credenziale viene letta dal prototipo; le regressioni backend
usano esclusivamente sentinelle sintetiche.

Il workflow .github/workflows/football-evidence-validation-v1.yml usa Python
3.12.14, dipendenze fissate e gli stessi comandi. TEST_REPORT.md riporta i risultati.
Costo infrastrutturale aggiuntivo: zero. Nessuna acquisizione live, nessun database
esterno, servizio, pianificazione, acquisto, merge o deployment.
