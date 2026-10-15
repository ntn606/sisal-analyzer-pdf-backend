import argparse
import json

from .common import Blocked, load_json, result_blocked
from .parser import parse_snapshot


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Offline Sisal Multigol PDF cell reader"
    )
    parser.add_argument("pdf")
    parser.add_argument("--provenance", required=True)
    parser.add_argument("--identity", required=True)
    parser.add_argument(
        "--mode", choices=("real_only", "synthetic_test"), default="real_only"
    )
    args = parser.parse_args(argv)
    try:
        report = parse_snapshot(
            args.pdf, args.provenance, load_json(args.identity), mode=args.mode
        )
    except Blocked as error:
        report = result_blocked(str(error))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
