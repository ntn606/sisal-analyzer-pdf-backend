# Verifica reale: Coventry–Newcastle

Evento futuro: **2026-10-12, 21:00:00 Europe/Rome**, equivalente a **2026-10-12T19:00:00+00:00**. PDF ufficiale per manifestazione, pagina 2, intestazione **ENG Premier League**. Palinsesto **36411**, avvenimento **1885**.

Catena realmente acquisita: Sisal → API-Football fixture **1557420** → football-data.org match **560597**. CLI esistente eseguita con `evidence_mode=real_only`: **diagnostic_available**, temporalità **verified_as_of_observation**. Nessun evento o identificativo sintetico entra in questa prova.

| Squadra / posizione | Canonico locale | API-Football | football-data.org | Risultati validi entro 180 giorni | Selezionati |
|---|---|---|---|---|---|
| Coventry / home | local:team:coventry | 1346 | 1076 | 5 | 5/5 |
| Newcastle / away | local:team:newcastle | 34 | 67 | 5 | 5/5 |

Competizione verificata: `local:competition:PL`, API-Football `39`, football-data.org `2021 / PL`. Stagione 2026/27 verificata da entrambi i provider. Il PDF stampa giorno/mese; l’anno deriva dal contesto/aggiornamento 11/10/2026 e dal calendario, non viene inventato come campo esplicito della riga.

Entrambe le identità sono revisionate separatamente con ID ufficiali, posizione casa/ospite, stesso avversario, competizione/country, stagione e identico istante UTC. Il fixture API-Football è NS e il match FD è TIMED. Le schede FD confermano ID e appartenenza alla competizione. Il nome dello stadio della squadra di casa coincide esattamente nelle due fonti: una prova aggiuntiva distinta dalla somiglianza dei nomi. Nessun fuzzy matching.

Il profilo country/men/first/senior è una normalizzazione esplicita dal contesto del campionato; non è dichiarato come anagrafica grezza restituita dal fixture. La review è locale e basata sulle prove conservate, non una certificazione emessa dai provider. Mapping limitati alla stagione e al target, con scadenza 13 ottobre 2026.

[Registro completo](registry.json), [review e motivazioni](evidence/proof-review.json), [richiesta as-of](request-asof-observation.json), [JSON integrale real_only](real_only.json). Le prove PDF, HTML, fixture, schede e risposte dei risultati sono in evidence/. SHA-256 e provenienza degli estratti originali della pagina ufficiale sono verificati dall’adapter.

| Squadra testata | Match ID | Data UTC | Competizione / stagione ID | Casa–ospite | Risultato 90 minuti | Campo | GF–GS | Disponibile entro UTC |
|---|---|---|---|---|---|---|---|---|
| Coventry | [560589](evidence/fd-result-560589.json) | 2026-09-19T16:30:00+00:00 | PL / 2502 | Nottingham Forest FC–Coventry City FC | 0–1 | away | 1–0 | 2026-10-11T20:23:40.797699+00:00 |
| Coventry | [560578](evidence/fd-result-560578.json) | 2026-09-13T13:00:00+00:00 | PL / 2502 | Coventry City FC–Brighton & Hove Albion FC | 0–5 | home | 0–5 | 2026-10-11T20:23:49.063632+00:00 |
| Coventry | [560563](evidence/fd-result-560563.json) | 2026-09-05T14:00:00+00:00 | PL / 2502 | Manchester City FC–Coventry City FC | 1–0 | away | 0–1 | 2026-10-11T20:23:57.456742+00:00 |
| Coventry | [560561](evidence/fd-result-560561.json) | 2026-08-29T14:00:00+00:00 | PL / 2502 | Coventry City FC–Hull City AFC | 0–1 | home | 0–1 | 2026-10-11T20:24:05.715793+00:00 |
| Coventry | [560542](evidence/fd-result-560542.json) | 2026-08-21T19:00:00+00:00 | PL / 2502 | Arsenal FC–Coventry City FC | 3–0 | away | 0–3 | 2026-10-11T20:24:14.161328+00:00 |
| Newcastle | [560588](evidence/fd-result-560588.json) | 2026-09-19T14:00:00+00:00 | PL / 2502 | Newcastle United FC–Hull City AFC | 2–1 | home | 2–1 | 2026-10-11T20:24:22.408252+00:00 |
| Newcastle | [560579](evidence/fd-result-560579.json) | 2026-09-14T19:00:00+00:00 | PL / 2502 | Leeds United FC–Newcastle United FC | 4–1 | away | 1–4 | 2026-10-11T20:24:30.653716+00:00 |
| Newcastle | [560571](evidence/fd-result-560571.json) | 2026-09-05T11:30:00+00:00 | PL / 2502 | Newcastle United FC–AFC Bournemouth | 2–2 | home | 2–2 | 2026-10-11T20:24:38.936516+00:00 |
| Newcastle | [560558](evidence/fd-result-560558.json) | 2026-08-29T16:30:00+00:00 | PL / 2502 | Tottenham Hotspur FC–Newcastle United FC | 0–2 | away | 2–0 | 2026-10-11T20:24:47.134954+00:00 |
| Newcastle | [560550](evidence/fd-result-560550.json) | 2026-08-23T15:30:00+00:00 | PL / 2502 | Newcastle United FC–Liverpool FC | 2–2 | home | 2–2 | 2026-10-11T20:24:55.320644+00:00 |

**Coventry**: 5 selezionati; più recente 2026-09-19T16:30:00+00:00, più vecchio 2026-08-21T19:00:00+00:00. V/P/S 1/0/4; gol 1/10; medie GF/GS 0.2/2.0. Casa/trasferta 2/3. Statistiche descrittive del campione nei 90 minuti, non pronostici.


**Newcastle**: 5 selezionati; più recente 2026-09-19T14:00:00+00:00, più vecchio 2026-08-23T15:30:00+00:00. V/P/S 2/2/1; gol 9/9; medie GF/GS 1.8/1.8. Casa/trasferta 3/2. Statistiche descrittive del campione nei 90 minuti, non pronostici.

Istante reale di controllo: **2026-10-11T20:26:17.907540+00:00**, precedente al kickoff. Cutoff esclusivo su `min(kickoff, analysis_at, verified_at)`, finestra 180 giorni con limite inferiore incluso, età massima snapshot 24 ore. Si selezionano solo FINISHED completi, senza duplicare match ID, preservando competizione e stagione. Tutti i venti risultati di queste due repliche sono REGULAR; nessun rigore viene utilizzato come gol nei 90 minuti.

Lo scope richiesto aggrega il campionato nazionale e CL, ma nel campione realmente selezionato compaiono solo partite di campionato. Nessun campione reale misto CL/campionato è dichiarato riuscito in questa replica. `all_competitions_complete=false`: le altre coppe non sono coperte/certificate. Le partite più recenti risalgono al 19–20 settembre: dentro 180 giorni, ma circa tre settimane prima della verifica; non è prova di assenza di incontri successivi in altre competizioni.

Le singole GET FD `/v4/matches/<id>` osservano score e stato FINISHED concordanti con lo snapshot. Response completion prova “disponibile entro”, non prima pubblicazione. `first_publication_time_verified=false`; nessun backtest precedente all’osservazione è certificato. Il ramo storico dell’adapter è usato per certificare l’istante corrente fissato dopo queste osservazioni, non per simulare l’evento futuro come già giocato.

Acquisizioni nuove: PDF/HTML e due fixture ufficiali; schede team e dettagli evento FD; un calendario PL e uno PD. Lo snapshot CL del primo dossier è riutilizzato byte-identico con acquisizione originale conservata. API-Football: tre richieste incluse status per le due repliche. FD: 28 GET totali, di cui venti osservazioni uniche dei risultati. Nessun retry e nessun 429.

Gli header API-Football di richieste differenti riportano saldi non monotoni (96 poi 97): non vengono interpretati come saldo corrente affidabile. Si conserva una riserva e la proposta di produzione richiede un budget atomico condiviso con Railway. Le schede FD possono avere lastUpdated anagrafici vecchi; sono registrati nelle risposte e non equivalgono alla disponibilità dei risultati.

Nessun blocco di identità o sufficienza è emerso per questo evento. Limiti aperti: copertura parziale di competizioni, vecchiaia di alcuni campi anagrafici, prima pubblicazione sconosciuta, binding da rinnovare prima dell’evento e nessuna prova di generalizzazione automatica a tutti i club.

Il wrapper diagnostico restituisce sempre `diagnostic_only=true`, `ready_for_analysis=false`, `ready_for_quant=false`, `statistics_usable_in_production=false`. Non restituisce quote o pronostici. Test e proposta Railway: [README](../../README.md), [riepilogo test](../../reports/test-summary.json), [integrazione proposta](../../RAILWAY_PROPOSAL.md).
