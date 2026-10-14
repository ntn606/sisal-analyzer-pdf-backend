# Limiti e dipendenze per le fasi successive

1. Nessuna evidenza calcistica reale è stata acquisita in A1. Esempi e 81 nuovi
   test sono sintetici e riconoscibili tramite data_origin, ID e URI. Non è
   dimostrato un dossier reale completo né una previsione autentica prepartita.
2. verified è una attestazione revisionata fornita dall'operatore. Il prototipo
   verifica schema, riferimenti, identità canoniche e tempi ma non l'autenticità
   di una fonte, l'esattezza delle mappature o il significato di testi liberi.
   Gli hash delle fonti vanno verificati rispetto ai documenti conservati dalla
   procedura di acquisizione, ancora esterna al modulo. Nessun fetch automatico.
3. Orologio locale e directory posseduta da un operatore fidato sono prerequisiti.
   Nessuna autorità di timestamp, firma esterna o prova crittografica del momento
   di registrazione. L'API pubblica non consente backdating; chi controlla
   processo/filesystem/orologio può aggirare queste garanzie. _clock è soltanto
   un seam fidato dei test Python, non un parametro CLI o JSON.
4. Append-only a livello di API, lock POSIX, fsync e catena SHA-256 rilevano
   modifiche e anomalie accidentali. Non sono storage WORM. Eliminare la coda
   lasciando un prefisso valido richiede un checkpoint fidato separato per essere
   rilevato. Riscrivere intera catena e checkpoint locali resta possibile con
   privilegi sufficienti. Il servizio futuro deve ancorare/conservare checkpoint
   indipendenti prima di rivendicare immutabilità contro operatori ostili.
5. Scrittura interrotta/corruzione: blocco, nessuna riparazione o troncamento
   automatico. Directory parent fidata; O_NOFOLLOW protegge il journal, non una
   gerarchia di directory controllata da un avversario. Linux/POSIX, no supporto
   Windows o garanzie su filesystem remoti. Journal limitato a 64 MiB e verificato
   integralmente; rotazione/migrazione/backup devono preservare checkpoint.
6. Ogni richiesta crea un UUID nuovo. Non c'è ancora una chiave idempotency:
   un retry può creare una nuova registrazione separata. Gli esiti corretti sono
   nuovi outcome, non sostituzioni; il consumatore deve risolvere esplicitamente
   eventuali risultati contraddittori.
7. Freschezza quote di un'ora e storico 180 giorni sono policy locali. Non provano
   che una quota sia ancora offerta. Availability e orari originali devono essere
   documentati; un'acquisizione odierna non dimostra la disponibilità in un backtest.
   Nessuna estensione di scadenze/identità o modifica dell'orologio per riuscire.
8. Regole di valutazione sperimentali: manca un corpus revisionato/versionato
   dei regolamenti Sisal per ogni mercato, periodo, rinvio, annullamento e
   combinazione. Non è un settlement ufficiale. Servono dati specifici per
   corner, cartellini, marcatori, primo tempo e altre legs My Combo. Nessun ROI.
9. La CLI legge documenti locali limitati a 2 MB e stampa gli snapshot con show.
   Il contratto non richiede credenziali né header; non inserirli nei testi liberi.
   Non esiste un filtro capace di certificare l'assenza di ogni segreto nei
   documenti di un operatore. Il futuro servizio richiede minimizzazione,
   autorizzazione, tutela dei dati personali e controllo della provenienza.
10. Nessuna integrazione MCP, Railway, backend, Scout, Analyst, History V2 o Quant
    effettuata. Identità, statistiche, notizie e quote reali dovranno essere
    revisionate e normalizzate da adapter esterni, mantenendo i blocchi esistenti.
    Le probabilità e i modelli predittivi appartengono a fasi successive separate.

Prima fase successiva proposta, dopo revisione indipendente: acquisire/importare
legittimamente un dossier reale futuro completo con prove di disponibilità e
regolamenti, registrare una sola decisione manuale, esportare il checkpoint e
valutare separatamente l'esito quando verificato. Non farlo in questo incarico.
