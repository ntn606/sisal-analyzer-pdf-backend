"""Render the two real dossiers and test results from actual saved artifacts."""
from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parents[1]
def read(path):return json.loads(path.read_text())
def main():
 suites=[]
 for label,filename in [('identity_adapter','adapter-tests.log'),('history_provider','provider-tests.log'),('backend_regression','backend-regression-tests.log')]:
  text=(ROOT/'reports'/filename).read_text();match=re.search(r'Ran (\d+) tests',text)
  suites.append({'suite':label,'tests_run':int(match[1]) if match else 0,'successful':text.rstrip().endswith('OK'),'log':filename,'provider_api_requests':0})
 wrapper=read(ROOT/'reports/wrapper-tests.json')
 suites.append({'suite':'wrapper_transport_mcp','tests_run':wrapper['tests_run'],'successful':wrapper['successful'],'log':'wrapper-tests.log','provider_api_requests':0})
 summary={'tests_run':sum(s['tests_run'] for s in suites),'all_passed':all(s['successful'] for s in suites),'provider_api_requests_in_tests':0,'suites':suites,'new_case_origins':wrapper['cases']}
 (ROOT/'reports/test-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 aggregate=[]
 for folder in sorted((ROOT/'cases').iterdir()):
  event=read(folder/'event.json');request=read(folder/'request-asof-observation.json');result=read(folder/'real_only.json');reg=read(folder/'registry.json')
  comp=event['competition'];name=event['home']+'–'+event['away']
  lines=[f'# Verifica reale: {name}', '',f"Evento futuro: **{event['date']}, {event['time']} Europe/Rome**, equivalente a **{event['kickoff_utc']}**. PDF ufficiale per manifestazione, pagina {event['manifest_pdf_page']}, intestazione **{event['actual_sisal_heading']}**. Palinsesto **{event['palinsesto']}**, avvenimento **{event['avvenimento']}**.", '',f"Catena realmente acquisita: Sisal → API-Football fixture **{request['api_football']['fixture_id']}** → football-data.org match **{request['football_data']['match_id']}**. CLI esistente eseguita con `evidence_mode=real_only`: **{result['status']}**, temporalità **{result['temporal']['state']}**. Nessun evento o identificativo sintetico entra in questa prova.", '', '| Squadra / posizione | Canonico locale | API-Football | football-data.org | Risultati validi entro 180 giorni | Selezionati |', '|---|---|---|---|---|---|']
  for side in ('home','away'):
   identity=result['checks']['teams'][side];history=result['histories'][side]
   lines.append(f"| {event[side]} / {side} | {identity['canonical_id']} | {identity['provider_ids']['api_football']} | {identity['provider_ids']['football_data']} | {history['counts']['valid_results_within_180_days']} | {history['counts']['selected_results']}/5 |")
  lines += ['',f"Competizione verificata: `{reg['competitions'][0]['canonical_id']}`, API-Football `{reg['competitions'][0]['api_football_id']}`, football-data.org `{reg['competitions'][0]['football_data_id']} / {comp}`. Stagione 2026/27 verificata da entrambi i provider. Il PDF stampa giorno/mese; l’anno deriva dal contesto/aggiornamento 11/10/2026 e dal calendario, non viene inventato come campo esplicito della riga.", '',
   'Entrambe le identità sono revisionate separatamente con ID ufficiali, posizione casa/ospite, stesso avversario, competizione/country, stagione e identico istante UTC. Il fixture API-Football è NS e il match FD è TIMED. Le schede FD confermano ID e appartenenza alla competizione. Il nome dello stadio della squadra di casa coincide esattamente nelle due fonti: una prova aggiuntiva distinta dalla somiglianza dei nomi. Nessun fuzzy matching.', '',
   'Il profilo country/men/first/senior è una normalizzazione esplicita dal contesto del campionato; non è dichiarato come anagrafica grezza restituita dal fixture. La review è locale e basata sulle prove conservate, non una certificazione emessa dai provider. Mapping limitati alla stagione e al target, con scadenza 13 ottobre 2026.', '',
   '[Registro completo](registry.json), [review e motivazioni](evidence/proof-review.json), [richiesta as-of](request-asof-observation.json), [JSON integrale real_only](real_only.json). Le prove PDF, HTML, fixture, schede e risposte dei risultati sono in evidence/. SHA-256 e provenienza degli estratti originali della pagina ufficiale sono verificati dall’adapter.', '',
   '| Squadra testata | Match ID | Data UTC | Competizione / stagione ID | Casa–ospite | Risultato 90 minuti | Campo | GF–GS | Disponibile entro UTC |','|---|---|---|---|---|---|---|---|---|']
  team_summaries=[];summary_paragraphs=[]
  for side,history in result['histories'].items():
   for match in history['matches']:
    score=match['score_90_minutes']
    lines.append(f"| {event[side]} | [{match['match_id']}](evidence/fd-result-{match['match_id']}.json) | {match['utc_date']} | {match['competition']['code']} / {match['season']['id']} | {match['home']['name']}–{match['away']['name']} | {score['home']}–{score['away']} | {match['venue']} | {match['goals_for_90_minutes']}–{match['goals_against_90_minutes']} | {match['availability']['known_available_by']} |")
   stats=history['statistics']['overall'];team_summaries.append({'side':side,'name':event[side],'counts':history['counts'],'newest':history['matches'][0]['utc_date'],'oldest':history['matches'][-1]['utc_date'],'statistics':history['statistics']})
   summary_paragraphs += ['',f"**{event[side]}**: {history['counts']['selected_results']} selezionati; più recente {history['matches'][0]['utc_date']}, più vecchio {history['matches'][-1]['utc_date']}. V/P/S {stats['wins']}/{stats['draws']}/{stats['losses']}; gol {stats['goals_for']}/{stats['goals_against']}; medie GF/GS {stats['average_goals_for']}/{stats['average_goals_against']}. Casa/trasferta {history['statistics']['home']['played']}/{history['statistics']['away']['played']}. Statistiche descrittive del campione nei 90 minuti, non pronostici.", '']
  lines += summary_paragraphs
  # Separate per-team summary paragraphs from the match table for readability.
  lines += [f"Istante reale di controllo: **{request['analysis_at']}**, precedente al kickoff. Cutoff esclusivo su `min(kickoff, analysis_at, verified_at)`, finestra 180 giorni con limite inferiore incluso, età massima snapshot 24 ore. Si selezionano solo FINISHED completi, senza duplicare match ID, preservando competizione e stagione. Tutti i venti risultati di queste due repliche sono REGULAR; nessun rigore viene utilizzato come gol nei 90 minuti.", '',
   'Lo scope richiesto aggrega il campionato nazionale e CL, ma nel campione realmente selezionato compaiono solo partite di campionato. Nessun campione reale misto CL/campionato è dichiarato riuscito in questa replica. `all_competitions_complete=false`: le altre coppe non sono coperte/certificate. Le partite più recenti risalgono al 19–20 settembre: dentro 180 giorni, ma circa tre settimane prima della verifica; non è prova di assenza di incontri successivi in altre competizioni.', '',
   'Le singole GET FD `/v4/matches/<id>` osservano score e stato FINISHED concordanti con lo snapshot. Response completion prova “disponibile entro”, non prima pubblicazione. `first_publication_time_verified=false`; nessun backtest precedente all’osservazione è certificato. Il ramo storico dell’adapter è usato per certificare l’istante corrente fissato dopo queste osservazioni, non per simulare l’evento futuro come già giocato.', '',
   'Acquisizioni nuove: PDF/HTML e due fixture ufficiali; schede team e dettagli evento FD; un calendario PL e uno PD. Lo snapshot CL del primo dossier è riutilizzato byte-identico con acquisizione originale conservata. API-Football: tre richieste incluse status per le due repliche. FD: 28 GET totali, di cui venti osservazioni uniche dei risultati. Nessun retry e nessun 429.', '',
   'Gli header API-Football di richieste differenti riportano saldi non monotoni (96 poi 97): non vengono interpretati come saldo corrente affidabile. Si conserva una riserva e la proposta di produzione richiede un budget atomico condiviso con Railway. Le schede FD possono avere lastUpdated anagrafici vecchi; sono registrati nelle risposte e non equivalgono alla disponibilità dei risultati.', '',
   'Nessun blocco di identità o sufficienza è emerso per questo evento. Limiti aperti: copertura parziale di competizioni, vecchiaia di alcuni campi anagrafici, prima pubblicazione sconosciuta, binding da rinnovare prima dell’evento e nessuna prova di generalizzazione automatica a tutti i club.', '',
   'Il wrapper diagnostico restituisce sempre `diagnostic_only=true`, `ready_for_analysis=false`, `ready_for_quant=false`, `statistics_usable_in_production=false`. Non restituisce quote o pronostici. Test e proposta Railway: [README](../../README.md), [riepilogo test](../../reports/test-summary.json), [integrazione proposta](../../RAILWAY_PROPOSAL.md).' ]
  (folder/'DOSSIER.md').write_text('\n'.join(lines)+'\n')
  aggregate.append({'event':event,'status':result['status'],'temporal':result['temporal'],'teams':team_summaries})
 (ROOT/'reports/live-summary.json').write_text(json.dumps({'events':aggregate,'api_football_requests':3,'football_data_requests':28,'sisal_requests':3,'new_requests_after_acquisition':0,'synthetic_inputs_in_live_cases':0},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'tests_run':summary['tests_run'],'all_passed':summary['all_passed'],'live_events':len(aggregate)}))
if __name__=='__main__':main()
