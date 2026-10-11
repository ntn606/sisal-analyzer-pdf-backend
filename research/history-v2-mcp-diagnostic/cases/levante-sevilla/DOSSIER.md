# Verifica reale: Levante–Siviglia

Evento futuro: **2026-10-12, 21:00:00 Europe/Rome**, equivalente a **2026-10-12T19:00:00+00:00**. PDF ufficiale per manifestazione, pagina 2, intestazione **ESP Liga**. Palinsesto **36411**, avvenimento **2282**.

Catena realmente acquisita: Sisal → API-Football fixture **1570407** → football-data.org match **564704**. CLI esistente eseguita con `evidence_mode=real_only`: **diagnostic_available**, temporalità **verified_as_of_observation**. Nessun evento o identificativo sintetico entra in questa prova.

| Squadra / posizione | Canonico locale | API-Football | football-data.org | Risultati validi entro 180 giorni | Selezionati |
|---|---|---|---|---|---|
| Levante / home | local:team:levante | 539 | 88 | 6 | 5/5 |
| Siviglia / away | local:team:sevilla | 536 | 559 | 7 | 5/5 |

Competizione verificata: `local:competition:PD`, API-Football `140`, football-data.org `2014 / PD`. Stagione 2026/27 verificata da entrambi i provider. Il PDF stampa giorno/mese; l’anno deriva dal contesto/aggiornamento 11/10/2026 e dal calendario, non viene inventato come campo esplicito della riga.

Entrambe le identità sono revisionate separatamente con ID ufficiali, posizione casa/ospite, stesso avversario, competizione/country, stagione e identico istante UTC. Il fixture API-Football è NS e il match FD è TIMED. Le schede FD confermano ID e appartenenza alla competizione. Il nome dello stadio della squadra di casa coincide esattamente nelle due fonti: una prova aggiuntiva distinta dalla somiglianza dei nomi. Nessun fuzzy matching.

Il profilo country/men/first/senior è una normalizzazione esplicita dal contesto del campionato; non è dichiarato come anagrafica grezza restituita dal fixture. La review è locale e basata sulle prove conservate, non una certificazione emessa dai provider. Mapping limitati alla stagione e al target, con scadenza 13 ottobre 2026.

[Registro completo](registry.json), [review e motivazioni](evidence/proof-review.json), [richiesta as-of](request-asof-observation.json), [JSON integrale real_only](real_only.json). Le prove PDF, HTML, fixture, schede e risposte dei risultati sono in evidence/. SHA-256 e provenienza degli estratti originali della pagina ufficiale sono verificati dall’adapter.

| Squadra testata | Match ID | Data UTC | Competizione / stagione ID | Casa–ospite | Risultato 90 minuti | Campo | GF–GS | Disponibile entro UTC |
|---|---|---|---|---|---|---|---|---|
| Levante | [564696](evidence/fd-result-564696.json) | 2026-09-20T16:30:00+00:00 | PD / 2518 | Villarreal CF–Levante UD | 3–1 | away | 1–3 | 2026-10-11T20:25:03.506078+00:00 |
| Levante | [564675](evidence/fd-result-564675.json) | 2026-09-13T14:15:00+00:00 | PD / 2518 | Levante UD–FC Barcelona | 2–4 | home | 2–4 | 2026-10-11T20:25:11.845996+00:00 |
| Levante | [564666](evidence/fd-result-564666.json) | 2026-09-06T16:30:00+00:00 | PD / 2518 | Málaga CF–Levante UD | 0–0 | away | 0–0 | 2026-10-11T20:25:20.005690+00:00 |
| Levante | [564655](evidence/fd-result-564655.json) | 2026-08-29T15:00:00+00:00 | PD / 2518 | Levante UD–Real Betis Balompié | 5–2 | home | 5–2 | 2026-10-11T20:25:28.214826+00:00 |
| Levante | [564639](evidence/fd-result-564639.json) | 2026-08-24T17:30:00+00:00 | PD / 2518 | CA Osasuna–Levante UD | 0–0 | away | 0–0 | 2026-10-11T20:25:36.612596+00:00 |
| Siviglia | [564690](evidence/fd-result-564690.json) | 2026-09-19T19:00:00+00:00 | PD / 2518 | Sevilla FC–FC Barcelona | 1–3 | home | 1–3 | 2026-10-11T20:25:44.782161+00:00 |
| Siviglia | [564679](evidence/fd-result-564679.json) | 2026-09-16T17:00:00+00:00 | PD / 2518 | RC Deportivo La Coruña–Sevilla FC | 0–1 | away | 1–0 | 2026-10-11T20:25:53.220981+00:00 |
| Siviglia | [564669](evidence/fd-result-564669.json) | 2026-09-11T19:00:00+00:00 | PD / 2518 | Sevilla FC–Valencia CF | 1–0 | home | 1–0 | 2026-10-11T20:26:01.510924+00:00 |
| Siviglia | [564661](evidence/fd-result-564661.json) | 2026-09-06T19:00:00+00:00 | PD / 2518 | RCD Espanyol de Barcelona–Sevilla FC | 1–1 | away | 1–1 | 2026-10-11T20:26:09.732794+00:00 |
| Siviglia | [564649](evidence/fd-result-564649.json) | 2026-08-29T19:30:00+00:00 | PD / 2518 | Sevilla FC–Club Atlético de Madrid | 1–3 | home | 1–3 | 2026-10-11T20:26:17.900218+00:00 |

**Levante**: 5 selezionati; più recente 2026-09-20T16:30:00+00:00, più vecchio 2026-08-24T17:30:00+00:00. V/P/S 1/2/2; gol 8/9; medie GF/GS 1.6/1.8. Casa/trasferta 2/3. Statistiche descrittive del campione nei 90 minuti, non pronostici.


**Siviglia**: 5 selezionati; più recente 2026-09-19T19:00:00+00:00, più vecchio 2026-08-29T19:30:00+00:00. V/P/S 2/1/2; gol 5/7; medie GF/GS 1.0/1.4. Casa/trasferta 3/2. Statistiche descrittive del campione nei 90 minuti, non pronostici.

Istante reale di controllo: **2026-10-11T20:26:18.083084+00:00**, precedente al kickoff. Cutoff esclusivo su `min(kickoff, analysis_at, verified_at)`, finestra 180 giorni con limite inferiore incluso, età massima snapshot 24 ore. Si selezionano solo FINISHED completi, senza duplicare match ID, preservando competizione e stagione. Tutti i venti risultati di queste due repliche sono REGULAR; nessun rigore viene utilizzato come gol nei 90 minuti.

Lo scope richiesto aggrega il campionato nazionale e CL, ma nel campione realmente selezionato compaiono solo partite di campionato. Nessun campione reale misto CL/campionato è dichiarato riuscito in questa replica. `all_competitions_complete=false`: le altre coppe non sono coperte/certificate. Le partite più recenti risalgono al 19–20 settembre: dentro 180 giorni, ma circa tre settimane prima della verifica; non è prova di assenza di incontri successivi in altre competizioni.

Le singole GET FD `/v4/matches/<id>` osservano score e stato FINISHED concordanti con lo snapshot. Response completion prova “disponibile entro”, non prima pubblicazione. `first_publication_time_verified=false`; nessun backtest precedente all’osservazione è certificato. Il ramo storico dell’adapter è usato per certificare l’istante corrente fissato dopo queste osservazioni, non per simulare l’evento futuro come già giocato.

Acquisizioni nuove: PDF/HTML e due fixture ufficiali; schede team e dettagli evento FD; un calendario PL e uno PD. Lo snapshot CL del primo dossier è riutilizzato byte-identico con acquisizione originale conservata. API-Football: tre richieste incluse status per le due repliche. FD: 28 GET totali, di cui venti osservazioni uniche dei risultati. Nessun retry e nessun 429.

Gli header API-Football di richieste differenti riportano saldi non monotoni (96 poi 97): non vengono interpretati come saldo corrente affidabile. Si conserva una riserva e la proposta di produzione richiede un budget atomico condiviso con Railway. Le schede FD possono avere lastUpdated anagrafici vecchi; sono registrati nelle risposte e non equivalgono alla disponibilità dei risultati.

Nessun blocco di identità o sufficienza è emerso per questo evento. Limiti aperti: copertura parziale di competizioni, vecchiaia di alcuni campi anagrafici, prima pubblicazione sconosciuta, binding da rinnovare prima dell’evento e nessuna prova di generalizzazione automatica a tutti i club.

Il wrapper diagnostico restituisce sempre `diagnostic_only=true`, `ready_for_analysis=false`, `ready_for_quant=false`, `statistics_usable_in_production=false`. Non restituisce quote o pronostici. Test e proposta Railway: [README](../../README.md), [riepilogo test](../../reports/test-summary.json), [integrazione proposta](../../RAILWAY_PROPOSAL.md).
