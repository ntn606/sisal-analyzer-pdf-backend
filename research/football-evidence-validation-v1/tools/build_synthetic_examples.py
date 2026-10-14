"""Developer fixture generation ONLY. Not a production registration path.

Explicitly fixed synthetic clocks cannot be passed to the public CLI. Never
use this script to label archived-real data or manufacture acquisition times.
"""

import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from fixtures import AFTER, NOW, dossier, result
from football_validation import Registry, validate_dossier


def main():
    output = ROOT / "examples"
    data = dossier()
    blocked = copy.deepcopy(data)
    blocked["identity"]["verification"] = "identity_unverified"
    blocked["identity"]["proof"] = None
    blocked["evidence"][0]["source"]["availability_verified"] = False
    blocked["evidence"][0]["payload"]["valid_until"] = "2026-10-14T09:56:00Z"
    documents = {
        "dossier-synthetic-valid": data,
        "dossier-synthetic-blocked": blocked,
        "result-synthetic": result(),
    }
    for label, example in (("valid", data), ("blocked", blocked)):
        documents["validation-synthetic-" + label] = validate_dossier(
            example, mode="synthetic_test", _clock=lambda: NOW
        )
    with tempfile.TemporaryDirectory() as directory:
        prediction = Registry(
            directory, mode="synthetic_test", _clock=lambda: NOW
        ).record_prediction(data)
        outcome = Registry(
            directory, mode="synthetic_test", _clock=lambda: AFTER
        ).record_outcome(prediction["record_id"], result())
    documents["prediction-synthetic"] = prediction
    documents["outcome-synthetic"] = outcome
    for label, document in documents.items():
        (output / (label + ".json")).write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        )
    print("Generated 7 synthetic fixture documents, not real evidence or predictions")


if __name__ == "__main__":
    main()
