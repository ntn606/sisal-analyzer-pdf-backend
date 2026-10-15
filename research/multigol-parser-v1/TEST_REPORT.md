# Verifica A2.1 — Multigol V1

Base main: 304cb2cf06d9f8f226eb89b701d3ec57beba6a38.
Ambiente: Python 3.12.14/Linux. Prove reali limitate allo snapshot archiviato;
nessuna dichiarazione di quote correnti o di identità verificata fra provider.

## Fonte effettivamente acquisita

Una richiesta pubblica al PDF ufficiale per Data, HTTP 200,
completata il 2026-10-15T20:42:15.875743Z (22:42:15.875743 Europe/Madrid).
Hash 71122a3a521047659941ff400f699db8b38471dd616b6c509c2f3542d0db7b4e.
115745 byte, due pagine, pubblicazione stampata 15/10/2026 22:08:15
senza timezone esplicita. Manifest originale e PDF inclusi nei fixture.

Nessun PDF per Manifestazione acquisito o dichiarato supportato.
Nessuna acquisizione durante test o CI. Nessuna API a pagamento/quota.

## Suite finale

| Gruppo | Test | Dati | Esito |
|---|---:|---|---|
| Layout, identità, celle, input corrotti/provenienza | 37 | PDF sintetici dichiarati | superati |
| Quote e box del documento originale | 7 | snapshot reale archiviato | superati |
| Contratto JSON e CLI | 3 | esempi reali archiviati + input negativo locale | superati |
| Regressioni backend preesistenti | 13 | mock sintetici dei provider | superati |
| Totale | 60 | nessuna chiamata live | superati |

Sono conteggiati i metodi test, non i subTest interni. Il runner intercetta
DNS, socket e richieste curl_cffi prima degli import; anche una chiamata
intercettata fa fallire il run. Risultato: OK, Network attempts: 0,
Live acquisitions during tests: 0.

Comando eseguito:
python research/multigol-parser-v1/tools/check_offline.py

Ulteriori verifiche: pip check senza incompatibilità; Ruff 0.14.0,
formattazione e controlli F/E9 superati; schema Draft 2020-12 compilato e
output parsed/partial/blocked validati. Rigenerazione riproducibile dello schema.

## Dimostrazione sulle celle, non solo sui numeri

1. PDF originale incluso e identificato da hash e timestamp.
2. Intestazioni, griglia e righe ispezionate sul documento renderizzato.
3. Trascritti 90 prezzi/null per tre eventi stampati, con box fissi in
   tests/fixtures/manual-cell-golden.json, senza usare l'output del parser.
4. Verificata ogni associazione fascia/Altro/valore, con box del parser
   confrontato con il box annotato e crop diretto dell'originale.
5. Verificata la fascia sovrastante ogni coppia di quote sull'originale.
6. Generati proof/original-page-1.png, original-page-2.png e 90-cell-audit.json,
   tutti riferiti allo stesso hash. Soli contorni sovrapposti, nessun testo aggiunto.

Reviewer delle trascrizioni: Codex; revisione umana indipendente ancora da fare.
Copertura manuale: tre eventi su 80 righe riconosciute, non tutti i prezzi del
PDF. Verificati 40 record per pagina durante la scansione geometrica; il
controllo manuale delle quote rimane sui 90 valori/vuoti indicati.

Casi reali principali:

| Evento | Cella originale | Risultato |
|---|---|---|
| 36421/31108 | 1–2 = 1,72; Altro = 1,80 | associazione corretta |
| 36421/31108 | 2–4 = 1,52; Altro = 2,05 | associazione corretta |
| 36421/31108 | 3–6 = 2,45; Altro = 1,38 | associazione corretta |
| 36421/31108 | 5–6 = 12; Altro vuoto | 12 e null, nessuno spostamento |
| 36421/6028 | 1–6 vuoto; Altro = 7,50 | null e 7,50, nessuno spostamento |
| 36421/6071, pagina 2 | 2–4 = 1,47; Altro = 2,25 | seconda pagina corretta |

## Casi sintetici distinti

- Fasce riordinate, griglia traslata e layout riconosciuto separatamente per
  pagina: prezzi associati alle nuove intestazioni fisiche.
- Fascia non pubblicata: nessuna selezione inventata.
- Cella vuota, Altro vuoto, quota illeggibile, più token, quota <=1 o prezzo
  che attraversa il separatore: null/stato esplicito; nessuna interpolazione.
- Griglia del corpo assente o traslata rispetto all'intestazione: blocco
  body_columns_disagree_with_header. Non basta avere numeri plausibili.
- Intestazioni sconosciute, tiers discordanti, titolo per Manifestazione,
  layout squadra o seconda pagina non riconosciuta: blocco.
- Pal./Avv. non presenti, nomi invertiti/simili, U19/Women/B, competizione/data/ora
  discordanti, nomi casa e ospite identici: nessuna associazione automatica.
- Duplicati/conflitti della coppia evento: blocco.
- PDF non accessibile, corrotto/non riconosciuto/privo di testo: blocco.
- Hash errato, coordinate di snapshot diversi, metadati di provenienza falsi,
  acquisizione futura, timestamp stampati discordanti: blocco.

## Compatibilità e limiti

Sola identità stampata in Sisal e confronto esatto con l'attesa; nessuna
certificazione canonica della squadra, categoria o calendario esterno.
La categoria resta null; pretenderne verifica dal layout attuale blocca.
Periodo di settlement e timezone non stampati restano null.
Nessuna mappatura automatica di Altro o dei mercati squadra.

Possibile futura proiezione delle fasce in A1.1 solo dopo verifica di identità,
regole del mercato, disponibilità temporale e freschezza. Nessuna integrazione
o modifica A1.1 effettuata. Snapshot e codici non vengono usati per pilot reali.

## CI e preservazione

Workflow dedicato .github/workflows/multigol-parser-v1.yml: dipendenze fissate,
Python 3.12.14, schema rigenerato senza drift e stesso runner offline.
Il download iniziale delle dipendenze è separato dalla fase di test.

Il risultato locale non certifica l'esito remoto: un risultato GitHub Actions
viene dichiarato solo se effettivamente leggibile dall'ambiente alla consegna.

server.py, requirements.txt, README.md e tests/test_api_football_errors.py
identici a main. I riferimenti Champions 39f96d8 e A1.1 dd7d851 restano invariati.
Nessun merge, cherry-pick, deployment, modifica Railway o produzione.
diagnostic_only=true; ready_for_analysis=false; ready_for_quant=false;
statistics_usable_in_production=false. Nessuna probabilità o consiglio.
