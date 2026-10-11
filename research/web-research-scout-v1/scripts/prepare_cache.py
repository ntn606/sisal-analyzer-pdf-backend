"""Materialize only existing local documents; no acquisition or provider imports."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from web_research_scout.cache import EvidenceCache

if __name__ == "__main__":
    docs = {
        name: json.loads((ROOT / "cache" / name).read_text())
        for name in (
            "sources.json",
            "claims.json",
            "identity-references.json",
            "access-observations.json",
            "source-matrix.json",
        )
    }
    revision = EvidenceCache(ROOT / "cache").activate(docs)
    print(json.dumps({"revision": revision, "new_web_requests": 0}))
