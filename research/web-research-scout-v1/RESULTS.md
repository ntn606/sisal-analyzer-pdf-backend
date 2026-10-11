# Risultati e prove effettive

## Esito dell'incarico

Prototipo eseguibile, isolato e offline. **102 test del prototipo +13 regressioni del backend, tutti superati**, senza nuove richieste ai provider. Non è stata ripetuta la suite History V2. SDK MCP reale1.30.0, client stdio e subprocess locali, Python3.12.14 su Linux x86_64.

Gli esempi reali riguardano limiti d'accesso e riferimenti d'identità già conservati. **Zero claim web reali verificati**. Non si dichiara ottenuta una notizia, un infortunio o una formazione. Il criterio di completamento ammette limiti espliciti quando le fonti impediscono la raccolta: questa consegna documenta tale caso.

## Accesso realmente osservato

Il 2026-10-11 intorno alle21:48:51UTC sono stati tentati GET HTTPS ai robots di Premier League, LaLiga, UEFA, Coventry, Newcastle, Levante e Siviglia. Tutti sono stati bloccati dal proxy: tunnel CONNECT403, prima di qualsiasi corpo/risposta del sito. Una diagnosi successiva sullo stesso URL Premier League ha confermato il tipo di blocco. Totale8tentativi,7URL/host unici; nessun ciclo di retry.

Le [sette ricevute minimizzate](cache/access-observations.json) conservano URL e acquisizione, reason, origin, content_retrieved=false, http_status=null e proxy_tunnel_status=403. Il timestamp dell'ulteriore diagnosi non è stato conservato: resta null in [access-summary.json](reports/access-summary.json). Non viene attribuito HTTP403 al sito finale.

Nessun robots, terms, contenuto editoriale o articolo ottenuto. Non sono state effettuate richieste API-Football, football-data.org, endpoint Sisal, login o download di PDF. Gli otto altri campionati non testati restano non verificati. Nessun percorso alternativo al proxy tentato. Il collector finale aggiunge pinning diretto e rifiuto fail-closed dei proxy non verificabili; le osservazioni iniziali sono prove manuali precedenti alla sua implementazione, non test live del suo trasporto finale.

## Candidati diagnostici

Clock dichiarato degli esempi: **2026-10-11T22:00:00Z**. Kickoff e ID ripresi esclusivamente dal dossier precedente al commit History68a704878a42c58920ce9294798406a1eacddbcb. Non costituiscono una ricertificazione attuale del calendario.

| Candidato | Sisal | API-Football / football-data.org | Kickoff conservato UTC | Esito | Claim reali |
|---|---|---|---|---|---:|
| Coventry–Newcastle |36411/1885,2026-10-12|1557420 /560597|2026-10-12T19:00:00Z|source_blocked|0|
| Levante–Siviglia |36411/2282,2026-10-12|1570407 /564704|2026-10-12T19:00:00Z|source_blocked|0|

Identità conservate:

| Squadra | ID canonico | API-Football team ID | football-data team ID |
|---|---|---:|---:|
|Coventry|local:team:coventry|1346|1076|
|Newcastle|local:team:newcastle|34|67|
|Levante|local:team:levante|539|88|
|Siviglia|local:team:sevilla|536|559|

[Coventry JSON](examples/coventry-newcastle.json), [Levante JSON](examples/levante-sevilla.json), [riferimenti con hash originali](cache/identity-references.json). Le risposte separano canonical_mapping_reference_verified=true da current_event_verified=false. Nessuno storico, risultato sportivo o forma recente è importato.

Per entrambe le squadre di ciascun candidato, tutte le9categorie risultano source_blocked con claims=[] e ricevute pertinenti alla competizione/club. not_found significherebbe soltanto assenza nella cache, non assenza di notizie o indisponibilità.

## Prove MCP e test automatici

| Gruppo | Dati e modalità | Verifica |
|---|---|---|
| Identità e cutoff su candidati | Riferimenti salvati + ricevute reali, nessuna rete | Entrambi source_blocked, zero claim reali; identità attuale non ricertificata. |
| Conferme, rumor, date sconosciute, formazioni e conflitti | Claim e review interamente sintetici | verified solo per conferma ufficiale revisionata; reported_unconfirmed per rumor/probabile; conflitto conservato. |
| Mapping errato, assente, omonimo, fixture errato | Mutazioni sintetiche di riferimenti salvati | identity_unverified, nessuna riparazione per nome; identità futura non disponibile in backtest. |
| Temporalità | Timestamp e clock sintetici dichiarati | Unknown/date-only non inventati; pubblicazione/acquisizione/review future e kickoff bloccati; vecchia pubblicazione non ringiovanita. |
| Cache | JSON sintetici e file temporanei | Hash/mancanze/traversal/symlink/duplicati; attivazione concorrente coerente e snapshot materializzato. |
| Collector | HTTP e DNS simulati | Live off, terms/robots gating,429/backoff, rate limit, risposta grande, parsing, redirect, DNS privato/mapped, pin TLS, proxy fail-closed. |
| MCP/CLI | **SDK reale** su stdio e subprocess locali | initialize, list_tools solo football_web_research_v1_probe, schemi rigorosi, call_tool positivo su cache e input errati sanitizzati; raccolta off. |
| Egress CI | Tentativi sintetici negati senza invio | DNS e socket libc impediti, guardia ereditata dal processo MCP. |
| Backend invariato |13test esistenti con provider mock | Errori API-Football, diagnostica, cache e controlli conservati. |

Il [rapporto test](reports/test-results.json) elenca ciascun test con esito e origine dei dati. [Esempio positivo sintetico](examples/synthetic-verified.json), [claim](examples/synthetic-claim.json) e [prova](examples/synthetic-proof.json) dichiarano origin=synthetic e execution_mode=synthetic_offline_fixture. Non descrivono un giocatore reale. La modalità sintetica è un'opzione Python riservata ai test, non esposta dal tool o dalla CLI diagnostica.

I11schemi Draft2020-12 sono controllati; i18documenti di cache/esempio validati e la cache attiva verificata per hash. I report sono ulteriormente sottoposti a scansione di contenuti/segreti. La scansione pattern dei file pubblicabili non ha trovato corrispondenze; non equivale a una prova universale DLP.

## CI, branch e costi

Workflow dedicato [.github/workflows/web-research-scout-v1.yml](../../.github/workflows/web-research-scout-v1.yml): Ubuntu24.04, Python3.12, dipendenze pin, nessun segreto, offline guard attiva prima dei test, schemi e scansione. Usa soltanto le risorse GitHub già disponibili; non abilita piani a pagamento. L'installazione dei pacchetti precede la fase offline.

**Esito CI remota non verificabile:** il tentativo di lettura con gh api è stato negato dal proxy su api.github.com. Non viene riportata come verde. Controllare la pagina Actions del branch durante la revisione.

Branch nuovo: [research/web-research-scout-v1-20261011](https://github.com/ntn606/sisal-analyzer-pdf-backend/tree/research/web-research-scout-v1-20261011). Base main304cb2cf06d9f8f226eb89b701d3ec57beba6a38. Il commit finale è fornito nel messaggio di consegna e risolvibile dal branch.

Nessun costo nuovo, servizio, sottoscrizione, deployment, merge, modifica di produzione o istruzioni cloud. [Elenco completo dei file](CHANGED_FILES.md), [architettura](ARCHITECTURE.md), [matrice](SOURCE_MATRIX.md), [sicurezza](SECURITY_REPORT.md), [limiti e prossimo passo](LIMITATIONS.md). Attendere la revisione di Antonio prima di integrare.
