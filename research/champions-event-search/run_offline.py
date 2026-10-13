"""Run only the backend suite, under an inherited native/DNS egress guard."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
env = {
    k: v
    for k, v in os.environ.items()
    if not any(
        w in k.upper()
        for w in ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "FOOTBALL_KEY")
    )
}
env.update(
    SISAL_MATCHES_OFFLINE_TESTS="1",
    PYTHONDONTWRITEBYTECODE="1",
    PYTHONPATH=os.pathsep.join(
        [str(ROOT / "research/champions-event-search/offline_guard"), str(ROOT)]
    ),
)
subprocess.run(
    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
    cwd=ROOT,
    env=env,
    check=True,
    timeout=90,
)
