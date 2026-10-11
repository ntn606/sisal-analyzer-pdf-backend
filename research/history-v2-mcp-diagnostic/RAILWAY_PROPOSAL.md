# Proposta precisa di integrazione Railway — non eseguita

Stato attuale: wrapper stdio funzionante e isolato, due nuove catene reali,
162 test offline passati. Nessuna modifica a Railway/server.py e nessun deploy.
Le prove coprono tre eventi di tre campionati includendo Atalanta–Venezia; non
certificano automaticamente tutte le 13 competizioni né completezza di tutte
le coppe. I mapping di questi due nuovi target scadono il 13 ottobre 2026.

## Primo rilascio proposto: servizio diagnostico separato

Dopo revisione del branch, creare un servizio separato nello stesso progetto
Railway, senza importare Scout/Analyst/Quant o modificare il server MCP corrente.
Root directory: research/history-v2-mcp-diagnostic. Python 3.12, installazione da
requirements-mcp.txt (SDK mcp 1.30.0), copie vendor e contratti già inclusi.
Nessuna richiesta live dalle chiamate del tool; usare snapshot e registry
revisionati. Non acquistare Redis o altri servizi per questo prototipo.

Railway richiede un trasporto di rete: l'attuale entrypoint è volutamente solo
stdio e **non va deployato tal quale come server HTTP**. Un successivo commit
revisionabile deve aggiungere un entrypoint streamable-http, porta da PORT,
host 0.0.0.0, percorso /mcp e healthcheck /healthz. Il healthcheck verifica
configurazione/lettura dati, senza consumare API. Il processo non viene avviato
come parte di questo lavoro; nessun URL Railway viene inventato.

Mantenere la protezione DNS rebinding del nuovo FastMCP attiva, con allowlist
esatta dell'host Railway assegnato, e controllo Origin. Aggiungere autenticazione
MCP Bearer per i client autorizzati prima di rendere accessibile il servizio.
Non copiare il setting che disabilita questa protezione nel backend attuale.
Testare inizializzazione/list_tools/call_tool HTTP oltre ai test stdio già eseguiti.

## Configurazione proposta, da applicare soltanto nel rilascio approvato

- HISTORY_V2_DATA_ROOT: percorso del catalogo revisionato, contratti e snapshot.
- PORT: fornita da Railway; nessuna modifica manuale nel backend corrente.
- HISTORY_V2_MCP_TOKEN: nuovo segreto per autenticare l'eventuale servizio HTTP,
  da configurare in modo protetto, mai in Git o nei log.
- API_FOOTBALL_KEY e FOOTBALL_DATA_TOKEN: riusare credenziali protette solo nel
  processo operatore che acquisisce le prove. Il servizio di lettura cache non
  ha bisogno di riceverle. Non copiare valori da Codex o dal repository.

Sono proposte di configurazione, non variabili create o modificate in questa
attività. diagnostic_only=true, ready_for_analysis=false e ready_for_quant=false
restano invarianti del codice e non feature flag modificabili dal client.

## Dati persistenti e rinnovo delle prove

Un volume locale può conservare catalogo, PDF/HTML, snapshot normalizzati,
metadati di completamento e hash. Usare scritture atomiche di un'intera revisione:
il servizio vede la versione precedente o quella nuova, mai un registro a metà
aggiornamento. Registro ed evidenze sono configurazione fidata revisionata,
non payload MCP. I client inviano solo palinsesto, avvenimento e match_date.

Prima del kickoff: acquisire fonte Sisal ufficiale e fixture aggiornati (TTL 1h),
snapshot FD (TTL 24h) e osservazioni dei risultati necessari. Rivedere il mapping
se cambiano squadre, competizione, stagione o kickoff. Non promuovere una
corrispondenza tramite soli nomi. Storie parziali restano etichettate; Conference,
Europa League e altre coppe richiedono prove/copertura aggiuntive, non riempimenti.

Pubblicazione iniziale del risultato rimane sconosciuta finché non esiste una
prova esplicita. known_available_by conserva il completamento reale della GET.
Richieste successive al kickoff sono bloccate e non riutilizzano statistiche in
cache. Le prove salvate oggi non autorizzano backtest anteriori alla loro
osservazione.

## Budget condiviso con il backend attuale

Le letture di quota non bastano a coordinare processi diversi. Prima di abilitare
un acquisitore automatico serve una prenotazione atomica per lo stesso account
API-Football usato da Railway, condivisa anche dal backend: limite minuto/giorno,
riserva 20/giorno e 2/minuto, timeout, Retry-After/reset e conservazione degli
header numerici. Header non monotoni non incrementano il saldo.

L'helper ProviderTransport rifiuta chiamate senza callback di budget. Non è
collegato al tool e non garantisce da solo coordinamento distribuito. Senza
intervenire sul backend corrente, il primo servizio deve pertanto restare
cache-only, con acquisizioni manuali coordinate. Un budget condiviso tramite
infrastruttura già esistente o un file transazionale accessibile a tutti i
processi è un lavoro futuro distinto. Nessun nuovo servizio a pagamento viene
introdotto senza approvazione.

## Criteri per promozione e rollback

Prima dell'attivazione: revisione del mapping/provenienza dei tre casi, prove
aggiuntive su più competizioni, test del nuovo trasporto/autenticazione HTTP,
integrità dei volumi, test di scadenza e concorrenza del catalogo, verifica degli
invarianti diagnostici e assenza di segreti nei log. Copertura parziale mostrata
esplicitamente. Il monitoraggio registra solo stato/categoria, ID pubblici,
latenza e contatori; non token, header auth, raw error body o query arbitrarie.

Rollback: arrestare/rimuovere soltanto il servizio diagnostico e ripristinare
l'ultima revisione del catalogo. Backend, Scout, Analyst e Quant rimangono
indipendenti. L'integrazione di questo tool nel server MCP principale richiede
un successivo cambiamento approvato; non fa parte di questo branch isolato.
