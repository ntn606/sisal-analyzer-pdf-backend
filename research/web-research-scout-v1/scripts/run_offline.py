"""Reproducible subprocess run; guard loaded at startup and inherited by MCP."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-backend-regression", action="store_true")
    args = parser.parse_args()
    env = {
        k: v
        for k, v in os.environ.items()
        if not any(
            w in k.upper()
            for w in ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "FOOTBALL_KEY")
        )
    }
    env.update(
        WEB_SCOUT_OFFLINE_TESTS="1",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONPATH=os.pathsep.join([str(ROOT / "scripts/offline_guard"), str(ROOT)]),
    )

    def run(argv, cwd=ROOT):
        subprocess.run(
            [sys.executable, *argv], cwd=cwd, env=env, check=True, timeout=90
        )

    run(["-m", "unittest", "discover", "-s", "tests", "-v"])
    run(["scripts/validate_artifacts.py"])
    run(["scripts/scan_secrets.py"])
    if args.include_backend_regression:
        run(["-m", "unittest", "discover", "-s", "tests", "-v"], REPO)
    print(
        json.dumps(
            {
                "offline_guard": True,
                "new_web_requests": 0,
                "backend_regression_requested": args.include_backend_regression,
            }
        )
    )


if __name__ == "__main__":
    main()
