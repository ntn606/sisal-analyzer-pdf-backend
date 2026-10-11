"""Validate local contracts/examples/cache integrity and scan publishable JSON."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from jsonschema import Draft202012Validator, FormatChecker

from web_research_scout.cache import EvidenceCache
from web_research_scout.security import SafeError, load_json, unsafe_content


def main():
    schemas = {
        p.name.replace(".schema.json", ""): load_json(p.read_bytes())
        for p in (ROOT / "contracts").glob("*.schema.json")
    }
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
    checked = 0
    scanned = 0

    def validate(path, name):
        nonlocal checked
        Draft202012Validator(schemas[name], format_checker=FormatChecker()).validate(
            load_json(path.read_bytes())
        )
        checked += 1

    for path in (ROOT / "cache").rglob("*.json"):
        if path.name == "ACTIVE.json":
            name = "active"
        elif path.name == "manifest.json":
            name = "manifest"
        else:
            name = path.stem
        validate(path, name)
    for path in (ROOT / "examples").glob("*.json"):
        name = {
            "request": "request",
            "synthetic-claim": "claim",
            "synthetic-proof": "reviewed-proof",
        }.get(path.stem, "response")
        validate(path, name)
    for path in [
        *(ROOT / "cache").rglob("*.json"),
        *(ROOT / "examples").glob("*.json"),
        *(ROOT / "reports").glob("*.json"),
    ]:
        value = load_json(path.read_bytes())
        scanned += 1
        # Article/injection/credential shapes must never survive publication.
        if unsafe_content(value):
            raise SafeError("publishable_artifact_security_scan_failed")
    EvidenceCache(ROOT / "cache").read()
    sources = load_json((ROOT / "cache/sources.json").read_bytes())["sources"]
    matrix = load_json((ROOT / "cache/source-matrix.json").read_bytes())
    if len({row["competition"] for row in matrix}) != 13:
        raise SafeError("competition_matrix_incomplete")
    if any(
        row["source_id"] not in sources or row["real_web_claims_verified"] != 0
        for row in matrix
    ):
        raise SafeError("matrix_claim_not_evidenced")
    print(
        json.dumps(
            {
                "schemas_checked": len(schemas),
                "json_documents_validated": checked,
                "publishable_json_scanned": scanned,
                "cache_integrity": "passed",
                "new_web_requests": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
