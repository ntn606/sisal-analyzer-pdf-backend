# Web Research Scout V1 — prototipo isolato

Prototipo diagnostico cache-only; parte da main, senza importare i motori History V2 o il backend di produzione. Tutti gli indicatori di operatività restano disabilitati.

**Esito reale:** i siti candidati provati sono stati bloccati dal proxy prima del recupero dei contenuti. La cache contiene riferimenti d'identità precedentemente conservati e ricevute d'accesso negato; nessuna notizia verificata. Gli esempi positivi sono sintetici e identificati come tali.

## Avvio locale senza servizi

Python 3.12. Da questa directory, in un ambiente virtuale dedicato:

~~~bash
python -m pip install -r requirements-ci.lock
python -m web_research_scout probe --palinsesto 36411 --avvenimento 1885 --match-date 2026-10-12
python -m web_research_scout probe --palinsesto 36411 --avvenimento 2282 --match-date 2026-10-12
python -m web_research_scout mcp
~~~

L'ultimo comando avvia solo MCP su **stdio**, da terminare alla fine della sessione; non apre porte o servizi cloud. Il client locale deve usare questa directory come cwd. Nessuna credenziale provider è necessaria. Non configurare token reali.

~~~json
{
  "mcpServers": {
    "web-research-scout-v1-local": {
      "command": "/percorso/venv/bin/python",
      "args": ["-m", "web_research_scout", "mcp"],
      "cwd": "/percorso/repository/research/web-research-scout-v1",
      "env": {"API_FOOTBALL_KEY": "", "FOOTBALL_DATA_TOKEN": ""}
    }
  }
}
~~~

La sintassi della configurazione cwd dipende dal client; quando manca, usare un lanciatore locale che imposti la directory. Nessun collegamento remoto da ChatGPT o Railway è attivato.

## Riproduzione offline

~~~bash
python scripts/run_offline.py --include-backend-regression
python scripts/generate_examples.py
python scripts/validate_artifacts.py
~~~

Il runner richiede Linux x86_64/aarch64 e applica seccomp ai subprocess di test. Blocca DNS, socket Internet nativi e connessioni, mantenendo gli IPC stdio/asyncio. Fallisce se non riesce a installare il filtro. La fase pip precede il blocco; i test non scaricano pacchetti o contenuti. Su altri sistemi è disponibile unittest, senza la stessa garanzia di egress; non equivale al controllo CI.

Gli esempi conservati usano il clock dichiarato **2026-10-11T22:00:00Z**. Il probe CLI/MCP usa l'ora corrente: al kickoff restituisce temporal_unverified, e dopo la scadenza della mappatura identity_unverified. Non estendere artificialmente le scadenze per riprodurre uno stato positivo.

## Raccolta separata

~~~bash
python -m web_research_scout collect --source newcastle --resource robots
~~~

Senza --live, restituisce live_disabled senza DNS o HTTP. L'opzione --live è esclusivamente un'azione manuale separata, da usare solo con accesso consentito. Non è esposta nel tool MCP. Nel cloud corrente non eseguirla: l'accesso è stato negato e il collector definitivo rifiuta un proxy di cui non può attestare l'IP finale, senza aggirarlo.

Per contenuti editoriali servono prima revisione documentata delle condizioni, permesso di conservazione dei metadati, regole robots aggiornate e URL esatto approvato. Tutte le fonti consegnate hanno permessi **non verificati**. Il collector restituisce JSON a stdout; non archivia HTML o verifica automaticamente fatti. L'operatore salva solo ricevute minimizzate, rivede le singole affermazioni e attiva una revisione locale completa con EvidenceCache.activate. scripts/prepare_cache.py rigenera soltanto il bundle locale consegnato.

Leggere [ARCHITECTURE.md](ARCHITECTURE.md), [SOURCE_MATRIX.md](SOURCE_MATRIX.md), [RESULTS.md](RESULTS.md), [SECURITY_REPORT.md](SECURITY_REPORT.md), [LIMITATIONS.md](LIMITATIONS.md) e [CHANGED_FILES.md](CHANGED_FILES.md).
