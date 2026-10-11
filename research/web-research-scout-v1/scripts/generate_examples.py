"""Offline reproducible examples. Fixture clock is explicit, never an MCP option."""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from support import NOW, claim_bundle

from web_research_scout.cache import EvidenceCache
from web_research_scout.probe import DiagnosticProbe


def save(name, value):
    (ROOT / "examples" / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    )


for name, avv in [("coventry-newcastle", "1885"), ("levante-sevilla", "2282")]:
    output = DiagnosticProbe(
        ROOT / "cache", clock=lambda: NOW
    ).football_web_research_v1_probe("36411", avv, "2026-10-12")
    save(name + ".json", output)
save(
    "request.json",
    {"palinsesto": "36411", "avvenimento": "1885", "match_date": "2026-10-12"},
)
docs, claim = claim_bundle()
save("synthetic-claim.json", claim)
save("synthetic-proof.json", docs[claim["evidence_file"]])
with tempfile.TemporaryDirectory() as directory:
    EvidenceCache(directory).activate(docs)
    save(
        "synthetic-verified.json",
        DiagnosticProbe(
            directory, clock=lambda: NOW, allow_synthetic=True
        ).football_web_research_v1_probe("36411", "1885", "2026-10-12"),
    )
