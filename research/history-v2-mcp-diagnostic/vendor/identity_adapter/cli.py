"""Local JSON CLI. No secrets, HTTP calls or production imports."""
import argparse
import json
from pathlib import Path

from history_provider_v2 import load_snapshots
from history_provider_v2.provider import InputError
from .core import VERSION, probe, read_json


class Parser(argparse.ArgumentParser):
    def error(self, message):
        print(json.dumps({'schema_version': VERSION, 'status':'input_error', 'ready_for_quant':False, 'error':'invalid_cli_arguments'}))
        raise SystemExit(2)


def main(argv=None):
    parser = Parser(description='Isolated diagnostic identity adapter: no API calls.')
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--snapshots', type=Path, default=Path(__file__).resolve().parents[1]/'fixtures/real')
    args = parser.parse_args(argv)
    try:
        output = probe(read_json(args.request), read_json(args.registry), load_snapshots(args.snapshots), args.evidence)
    except InputError as error:
        print(json.dumps({'schema_version': VERSION, 'status':'input_error', 'ready_for_quant':False, 'error':str(error)}))
        return 2
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0
