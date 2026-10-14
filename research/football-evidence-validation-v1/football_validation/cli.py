"""JSON-only local CLI; no credentials, API calls, clock override or mutations."""

import argparse
import json

from .common import FLAGS, ValidationError, load
from .register import Registry
from .validation import validate_dossier


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Offline evidence validation; no predictions generated"
    )
    parser.add_argument(
        "--mode", choices=("real_only", "synthetic_test"), default="real_only"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("dossier")
    register = commands.add_parser("register")
    register.add_argument("dossier")
    register.add_argument("--registry", required=True)
    outcome = commands.add_parser("outcome")
    outcome.add_argument("prediction_id")
    outcome.add_argument("result")
    outcome.add_argument("--registry", required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--registry", required=True)
    verify.add_argument("--checkpoint")
    show = commands.add_parser("show")
    show.add_argument("record_id")
    show.add_argument("--registry", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            result = validate_dossier(load(args.dossier), mode=args.mode)
        else:
            registry = Registry(args.registry, mode=args.mode)
            if args.command == "register":
                result = registry.record_prediction(load(args.dossier))
            elif args.command == "outcome":
                result = registry.record_outcome(args.prediction_id, load(args.result))
            elif args.command == "verify":
                result = registry.verify(
                    load(args.checkpoint) if args.checkpoint else None
                )
            else:
                result = registry.get(args.record_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result.get("status") == "blocked" else 0
    except ValidationError as exc:
        print(json.dumps({**FLAGS, "status": "blocked", "reasons": [str(exc)]}))
        return 2
    except (OSError, ValueError, KeyError, TypeError):
        print(
            json.dumps(
                {**FLAGS, "status": "blocked", "reasons": ["local_operation_failed"]}
            )
        )
        return 2
