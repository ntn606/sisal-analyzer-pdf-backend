"""CLI with JSON-only results and safe fixed error codes; no network support."""
import argparse
import json
from pathlib import Path
import sys

from .provider import InputError, build_history, load_snapshots


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # Do not reflect unknown arguments or file contents into logs.
        print(json.dumps({'status': 'input_error', 'error': 'invalid_cli_arguments'}))
        raise SystemExit(2)


def main(argv=None) -> int:
    parser = Parser(description='Offline History Provider V2: five real final results, no API calls.')
    parser.add_argument('--snapshots', type=Path, default=Path(__file__).resolve().parents[1] / 'fixtures/real')
    parser.add_argument('--team-id', required=True, help='Exact canonical ID, e.g. football-data.org:team:57')
    parser.add_argument('--competitions', required=True, help='Explicit comma-separated scope, e.g. PL,CL')
    parser.add_argument('--event-kickoff', required=True, help='ISO-8601 with UTC offset')
    parser.add_argument('--verified-at', required=True, help='ISO-8601 with UTC offset; no implicit current time')
    parser.add_argument('--timezone', default='UTC')
    parser.add_argument('--max-source-age-hours', type=float, default=24)
    args = parser.parse_args(argv)
    try:
        result = build_history(load_snapshots(args.snapshots), team_id=args.team_id,
                               competitions=args.competitions.split(','), event_kickoff=args.event_kickoff,
                               verified_at=args.verified_at, display_timezone=args.timezone,
                               max_source_age_hours=args.max_source_age_hours)
    except InputError as error:
        print(json.dumps({'status': 'input_error', 'error': str(error)}))
        return 2
    except OSError:
        print(json.dumps({'status': 'input_error', 'error': 'local_io_error'}))
        return 2
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write('\n')
    return 0
