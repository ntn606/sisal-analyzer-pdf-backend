"""Bounded pattern scan: report counts only, never matching values."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from web_research_scout.security import SECRET_PATTERNS


def main():
    count = 0
    for path in ROOT.rglob("*"):
        if (
            not path.is_file()
            or any(
                p in ("__pycache__", ".venv", ".local", ".ruff_cache")
                for p in path.parts
            )
            or path.suffix == ".pyc"
        ):
            continue
        count += 1
        text = path.read_text(encoding="utf-8")
        if any(re.search(pattern, text) for pattern in SECRET_PATTERNS):
            raise SystemExit("secret_pattern_detected_value_withheld")
    print(
        json.dumps(
            {
                "files_scanned": count,
                "secret_pattern_matches": 0,
                "limitations": "pattern scan cannot prove absence of every possible credential format",
            }
        )
    )


if __name__ == "__main__":
    main()
