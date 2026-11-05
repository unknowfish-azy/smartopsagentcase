"""Collect live HTTP, TCP port, and process probes as JSON.

Examples:
    python scripts/collect_probes.py --http http://127.0.0.1:8080/health
    python scripts/collect_probes.py --port 127.0.0.1:8080 --process python
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:  # allow direct execution from the repository root
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.inspector.verifiers.state_verifier import collect_probes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect live SmartOps probes")
    parser.add_argument("--http", action="append", default=[], metavar="URL")
    parser.add_argument("--port", action="append", default=[], metavar="HOST:PORT")
    parser.add_argument("--process", action="append", default=[], metavar="PATTERN")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    probes = collect_probes(
        {"http": args.http, "port": args.port, "process": args.process}
    )
    json.dump(probes, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
