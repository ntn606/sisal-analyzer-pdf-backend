# Matrice delle fonti e copertura reale

Tutte le fonti sono **candidati** a siti ufficiali da sottoporre a verifica, non integrazioni autorizzate. Le prove accesso sono del 2026-10-11 UTC. Nessuna pagina di notizie, terms o robots è stata recuperata. Nessuna delle 13 competizioni è supportata da claim web verificati; copertura parziale di notizie: zero.

| Competizione | Fonte candidata | Accesso realmente provato | Copertura web verificata | Claim reali |
|---|---|---|---|---:|
| Serie A (SA) | [www.legaseriea.it](https://www.legaseriea.it/) | Non testato | Non verificata | 0 |
| Serie B (SB) | [www.legab.it](https://www.legab.it/) | Non testato | Non verificata | 0 |
| Premier League (PL) | [www.premierleague.com](https://www.premierleague.com/) | CONNECT403 del proxy su robots; HTTP del sito sconosciuto | Non verificata | 0 |
| LaLiga (PD) | [www.laliga.com](https://www.laliga.com/) | CONNECT403 del proxy su robots; HTTP del sito sconosciuto | Non verificata | 0 |
| Bundesliga (BL1) | [www.bundesliga.com](https://www.bundesliga.com/) | Non testato | Non verificata | 0 |
| Ligue 1 (FL1) | [www.ligue1.com](https://www.ligue1.com/) | Non testato | Non verificata | 0 |
| Eredivisie (DED) | [eredivisie.nl](https://eredivisie.nl/) | Non testato | Non verificata | 0 |
| Primeira Liga (PPL) | [www.ligaportugal.pt](https://www.ligaportugal.pt/) | Non testato | Non verificata | 0 |
| EFL Championship (ELC) | [www.efl.com](https://www.efl.com/) | Non testato | Non verificata | 0 |
| Belgian Pro League (BPL) | [www.proleague.be](https://www.proleague.be/) | Non testato | Non verificata | 0 |
| UEFA Champions League (CL) | [www.uefa.com](https://www.uefa.com/) | CONNECT403 del proxy su robots; HTTP del sito sconosciuto | Non verificata | 0 |
| UEFA Europa League (EL) | [www.uefa.com](https://www.uefa.com/) | CONNECT403 del proxy su robots; HTTP del sito sconosciuto | Non verificata | 0 |
| UEFA Conference League (ECL) | [www.uefa.com](https://www.uefa.com/) | CONNECT403 del proxy su robots; HTTP del sito sconosciuto | Non verificata | 0 |

## Club dei candidati

| Club / ID canonico | Fonte candidata | Prova reale |
|---|---|---|
| local:team:coventry | [www.ccfc.co.uk](https://www.ccfc.co.uk/) | robots: CONNECT403 del proxy, nessun contenuto |
| local:team:newcastle | [www.newcastleunited.com](https://www.newcastleunited.com/) | robots: CONNECT403 del proxy, nessun contenuto |
| local:team:levante | [www.levanteud.com](https://www.levanteud.com/) | robots: CONNECT403 del proxy, nessun contenuto |
| local:team:sevilla | [sevillafc.es](https://sevillafc.es/) | robots: CONNECT403 del proxy, nessun contenuto |

Sono **7 URL unici** su 7 host: tre siti di competizione e quattro club. UEFA è una sola prova condivisa fra Champions, Europa e Conference, non tre acquisizioni. Una successiva diagnosi singola sul medesimo robots Premier League ha confermato il CONNECT403: **8 tentativi totali**. Gli altri otto campionati non sono stati interrogati dopo il blocco. Nessuna inferenza sulla loro accessibilità.

## Diritti, accesso e conservazione — per tutte le 15 fonti registrate

| Aspetto | Stato verificato in questo incarico | Regola del prototipo |
|---|---|---|
| Gratuito / costo | Nessun pagamento o iscrizione effettuato; condizioni non recuperate | Zero costi nuovi; contenuto pubblico non implica licenza gratuita. |
| Condizioni d’uso e licenza | Non verificate, terms_url=null, license=null | review_state=unverified; vietata raccolta editoriale. |
| Accesso automatico / robots | Non acquisiti; pagina accessibile non avrebbe valore di licenza | Richiesta manuale sola governance; contenuti richiedono robots review fresca e permesso di uso/conservazione. |
| Autenticazione | Nessuna credenziale usata; assenza di requisiti non dimostrata | Non effettuare login, né usare cookie o endpoint privati. |
| Limiti dichiarati dal sito | Non verificati | ≥5s per dominio, o crawl-delay più alto; timeout15s,256KB,429 senza retry. Non chiamarli limiti ufficiali del sito. |
| Attribuzione | Condizioni specifiche non verificate | Come minimo source URL, tipo e data di acquisizione; integrare gli obblighi documentati dopo revisione. |
| Conservazione | Nessuna autorizzazione a copiare articoli ottenuta | Nessun corpo persistito. Metadati/estratti soltanto se il diritto è documentato. |
| Freschezza | Nessun contenuto ricevuto, data di pubblicazione sconosciuta | Mai sostituire pubblicazione con acquisizione. |

## Alternative statistiche e stampa

football-data.org Free è un possibile punto di integrazione con History V2, secondo la ricerca precedente su nove competizioni. Non è stato interrogato in questo incarico e non offre una nuova prova di copertura di notizie/infortuni. Le colonne football_data_prior_declared_free nel JSON sono riferimenti al perimetro precedente, non risultati di nuove richieste o licenze web. Serie B, Belgian Pro League, Europa e Conference non vengono aggiunte alla copertura Free sulla base di queste pagine.

CSV football-data.co.uk e testate sportive pubbliche sono candidati per una revisione successiva: in questa fase nessuna verifica di licenza/accesso/conservazione e nessuna acquisizione. Nessuna fonte di stampa reale è approvata; il caso di stampa nei test è una fixture sintetica. Preferire un comunicato ufficiale con permessi documentati prima di estendere la discovery.

## Valutazione concreta

**Copertura gratuita web utilizzabile oggi: non dimostrata.** Il costo del prototipo è zero, ma accesso e diritti necessari restano bloccati/non verificati. L’output diagnostico conserva il limite senza inventare informazioni. [Ricevute](cache/access-observations.json) e [risultati](RESULTS.md) permettono di controllare esattamente cosa è stato osservato.
