# Revisione A1.1 — idoneità della decisione alla valutazione

Branch di partenza: research/football-evidence-validation-v1-a1-20261014.
Commit verificato: 07c198bbfa9fdbdc9139dff2dbb12e49097e2d72.
La revisione indipendente ha confermato la CI remota verde di A1 (informazione
fornita dall'operatore). Tale risultato non certifica la nuova revisione A1.1.

## Correzione e compatibilità

Soltanto candidate accede alle regole del mercato. watch, con o senza quota,
restituisce not_evaluable / watch_not_approved_selection. no_bet restituisce
not_evaluable / no_bet_decision: motivo distinto dall'osservazione watch.

Per no_bet il precedente motivo generico no_selection_recorded è quindi
sostituito; no_selection_recorded resta per una selezione candidate mancante.
Nessun campo JSON, versione dello schema o firma API cambia. Integrità,
provenienza, identità e controlli temporali mantengono la precedenza: un esito
non verificato continua a riportare il relativo blocco preliminare.

Il registro non è modificato: watch resta conservabile, inclusi mercato e quota
se presenti. Gli outcome diagnostici sono separati e non alterano lo snapshot.
Non vengono conteggiati come selezioni approvate; non esiste un nuovo contatore
o un calcolo di performance.

## Risultati A1.1

Esecuzione locale del 14 ottobre 2026, Python 3.12.14/Linux:

| Gruppo | Test | Esito |
|---|---:|---|
| Contratto, schemi, CLI ed esempi | 8 | superati |
| Valutatore (tre nuove regressioni) | 23 | superati |
| Registro | 19 | superati |
| Dossier e validazioni | 34 | superati |
| Regressioni backend | 13 | superati |
| Totale | 97 | superati, nessun fallimento |

Runner invariato:
python research/football-evidence-validation-v1/tools/check_offline.py

Network attempts: 0. Live provider acquisitions: 0.
Tutti i nuovi casi sono sintetici e dichiarati come tali.

I test nuovi, eseguiti prima della modifica del valutatore, riproducono winning,
losing e void per watch sia con quota sia senza alcuna evidenza odds. Dopo la
correzione questi casi restituiscono sempre not_evaluable con il motivo specifico.
Le stesse regressioni verificano la conservazione di watch nel registro, la
persistenza degli outcome diagnostici e l'integrità dello snapshot originale.
La terza regressione conferma winning/losing per candidate con quota valida.
Il test no_bet preesistente verifica ora il suo motivo distinto.

Regole Multigol, Over/Under, BTTS, combinazioni e My Combo: suite preesistente
superata e AST di _settle identico al commit di partenza. Schemi JSON,
generatori, registro, validator, CLI, esempi e API invariati. Cinque schemi
rigenerati senza diff; Ruff F/E9 e formattazione superati; pip check superato.

## CI e isolamento

Workflow ereditato invariato:
.github/workflows/football-evidence-validation-v1.yml

Il nome del nuovo branch rientra nel filtro push del workflow, che usa gli
stessi 97 test offline e dipendenze fissate. Un esito remoto della nuova revisione
non va dedotto da quello di A1: sarà dichiarato soltanto se verificabile.
Nessuna modifica di produzione, server.py, Railway, parser quote, Scout,
Analyst, History V2 o Quant. Nessuna acquisizione live, credenziale reale,
servizio aggiunto, merge o deployment.

---

## Rapporto storico A1, conservato per riferimento

# Rapporto di verifica A1

Esecuzione locale del 14 ottobre 2026 su Python 3.12.14/Linux.
Base main: 304cb2cf06d9f8f226eb89b701d3ec57beba6a38.
Nessuna prova live. Tutti i nuovi casi usano dati sintetici esplicitamente marcati.

## Risultati finali locali

| Gruppo | Test | Esito |
|---|---:|---|
| Contratto, schemi, CLI ed esempi salvati | 8 | superati |
| Valutatore mercati e limiti di settlement | 20 | superati |
| Registro, integrità, concorrenza e clock | 19 | superati |
| Dossier, identità, cutoff e freschezza | 34 | superati |
| Regressioni backend preesistenti | 13 | superati |
| Totale | 94 | superati, nessun fallimento |

Conteggi verificati dalla suite, non numero di subTest interni.
Ulteriori verifiche: pip check senza dipendenze incompatibili; Ruff 0.14.0
controlli F/E9 e formattazione superati; cinque schemi compilati con
Draft202012Validator.check_schema e FormatChecker attivo nei validator, con controlli locali espliciti per date-time e URI
anche in assenza delle dipendenze opzionali di jsonschema.

Comando:
python research/football-evidence-validation-v1/tools/check_offline.py

Risultato:
Ran 94 tests; OK; Network attempts: 0; Live provider acquisitions: 0.

Le guardie coprono risoluzione DNS, socket e Session.request di curl_cffi
(che usa libcurl). Un tentativo rilevato fa fallire il runner anche se il modulo
lo intercetta. Nessuna acquisizione API-Football, football-data.org o Sisal.

## Casi dimostrati

- Quota mancante: candidate bloccato, watch senza quota rappresentabile.
- Quota scaduta, vecchia pubblicazione con rilevazione nuova, finestra estesa
  artificialmente: bloccate; pubblicazione ignota rimane null.
- Informazione rilevata/pubblicata dopo analisi o kickoff: esclusione/blocco;
  anche il contesto futuro non può entrare in snapshot.
- Identità mancanti, squadre senior/giovanili, ID canonici e mappature invertite,
  competizione/stagione, offset errato e ora DST inesistente: blocchi.
- Formazione probabile promossa a ufficiale o confirmed: blocco.
- Storico duplicato/conflittuale, rinviato, incompleto e futuro: blocco.
- Multigol vs Over/Under: 4 gol perdono il range 2–3, vincono Over 1.5.
- Valutazioni 1X2, doppia chance, BTTS, O/U, Multigol squadra/partita,
  combinazioni e My Combo; corner mancanti, primo tempo e linee asiatiche
  non implementate: not_evaluable, senza inferenze dai gol finali.
- Pareggio nei 90 minuti e vittoria ai rigori: 1X2 sui 90 minuti rimane pareggio.
- Rinvio/cancellazione non implicano void; istruzione di void richiede prova.
- Snapshot alterato, JSON ambiguo, scrittura parziale e symlink: rifiuto.
- Dodici scrittori concorrenti: UUID distinti e catena sequenziale coerente.
- Esito e sua rettifica: nuovi record collegati, originale invariato.
- Cancellazione della coda: rilevata con checkpoint fidato separato.
- Registrazione al/dopo kickoff, quota scaduta durante attesa e clock che
  raggiunge kickoff durante preparazione: nessun record di previsione creato.

## Esempi e provenienza

Set completo in examples/: sette JSON, tutti sintetici.
Validation-synthetic-valid è validated solo al clock di fixture dichiarato.
Validation-synthetic-blocked conserva identity_unverified, quota scaduta e
disponibilità non verificata. I record prediction/outcome mantengono snapshot,
UUID, modo synthetic_test e hash concatenati. Nessun caso è una partita reale.

## CI

Workflow dedicato, pubblicato con il branch:
.github/workflows/football-evidence-validation-v1.yml

Stesso runner, Python 3.12.14 e dipendenze completamente fissate.
Installazione dipendenze separata dai test offline; riproducibilità degli schemi
controllata con rigenerazione e git diff --exit-code.

L'esito locale non costituisce un esito remoto GitHub Actions. Il risultato
remoto sarà riportato alla consegna solo se verificabile dall'ambiente; non è
dedotto dalla CI della correzione Champions o di altri branch.

## Ambito preservato

Nessuna modifica a file preesistenti di produzione, requirements.txt o test
backend. Nessun merge, deployment, acquisizione live, segreto reale, modello
predittivo o costo aggiuntivo. Test e documenti non abilitano Analysis/Quant.
Scansione euristica dei file pubblicabili: nessun formato di credenziale rilevato;
non equivale a una certificazione generale di assenza di segreti.
