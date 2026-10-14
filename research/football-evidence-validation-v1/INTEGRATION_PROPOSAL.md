# Interfaccia futura — proposta non implementata

Nessuna dipendenza o modifica a server.py. Componenti sperimentali:
schema/validator -> registro -> esito separato/evaluator.
Gli adapter esistenti resteranno responsabili di identità e raccolta revisionata.

Una futura interfaccia MCP autorizzata potrebbe esporre:

| Operazione | Input | Output | Effetto |
|---|---|---|---|
| football_evidence_validate_v1 | dossier schema 1.0.0 | diagnostica, motivi, evidenze ammesse/escluse | sola lettura |
| football_prediction_record_v1 | dossier revisionato, idempotency key futura | prediction ID, recorded_at effettivo, hash, checkpoint | append locale autorizzato |
| football_prediction_read_v1 | prediction ID | snapshot originale verificato | sola lettura |
| football_prediction_outcome_v1 | prediction ID, result schema 1.0.0 | outcome ID, valutazione, link/hash | append separato autorizzato |

Nessun parametro remoto now/recorded_at, nessuna sovrascrittura, nessun campo
probabilità, size/stake o valore atteso. La funzione di record non genera
candidate/watch/no_bet: riceve la decisione esplicita. Ogni operazione mantiene
diagnostic_only=true, ready_for_analysis=false, ready_for_quant=false e
statistics_usable_in_production=false.

Per l'eventuale fase di servizio: schema validation prima di ogni scrittura,
autenticazione e autorizzazione per registro, quote/request-size/concorrenza,
clock fidato, volume POSIX persistente, checkpoint esterni versionati, backup,
idempotenza e procedura esplicita per rettifiche degli esiti. Non leggere o
trasferire automaticamente segreti/provider key nei dossier.

Le quote devono preservare mercato/selezione, precisione decimale e timestamp
originari del PDF verificato. History V2 fornisce partite distinte per competizione,
ID e disponibilità temporale; Web Research Scout deve fornire notizie revisionate,
senza promuovere ipotesi a fatti. Le incompatibilità si traducono in blocchi,
non in completamenti inventati. Questa fase non include adapter di produzione.

Costo richiesto ora: zero. Nessun servizio aggiuntivo, deploy o configurazione
Railway. Un eventuale servizio futuro richiederà stima e approvazione separata.
