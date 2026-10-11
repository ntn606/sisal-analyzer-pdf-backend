"""CLI: probe is always offline; collection requires an explicit --live flag."""

import argparse
import json
from pathlib import Path

from .probe import DiagnosticProbe

ROOT = Path(__file__).resolve().parents[1]


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise SystemExit("invalid_cli_arguments")


def main(argv=None):
    parser = Parser()
    commands = parser.add_subparsers(dest="command", required=True)
    probe = commands.add_parser("probe")
    probe.add_argument("--palinsesto", required=True)
    probe.add_argument("--avvenimento", required=True)
    probe.add_argument("--match-date", required=True)
    probe.add_argument("--cache", default=str(ROOT / "cache"))
    collect = commands.add_parser("collect")
    collect.add_argument("--source", required=True)
    collect.add_argument("--resource", default="robots")
    collect.add_argument("--live", action="store_true")
    commands.add_parser("mcp")
    args = parser.parse_args(argv)
    if args.command == "probe":
        output = DiagnosticProbe(args.cache).football_web_research_v1_probe(
            args.palinsesto, args.avvenimento, args.match_date
        )
    elif args.command == "collect":
        from .collect import Collector, DomainBudget

        documents = DiagnosticProbe(ROOT / "cache").cache.read()[1]
        output = Collector(
            documents["sources.json"]["sources"],
            DomainBudget(ROOT / ".local/budget"),
            live=args.live,
        ).collect(args.source, args.resource)
    else:
        from .mcp_server import main as serve

        return serve()
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
