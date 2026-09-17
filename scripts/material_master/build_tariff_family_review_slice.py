"""Build a narrow tariff-family review queue from a full candidate package."""

from __future__ import annotations

import argparse
from pathlib import Path

from nexterp_agent.item_master.tariff_family_review import build_review_slice


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATES = ROOT / "data/material_master/tariff_family_review_v0_1/tariff_family_candidates.tsv"
DEFAULT_OUTPUT = ROOT / "data/material_master/tariff_family_review_v0_1/fastener_review_v0_1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--prefix", action="append", default=["7317", "7318"], help="税号前缀，可重复传入")
    args = parser.parse_args()
    summary = build_review_slice(args.candidates.resolve(), args.output.resolve(), args.prefix)
    print(f"review slice: {args.output.resolve()}")
    print(f"prefixes: {summary['code_prefixes']}")
    print(f"rows: {summary['row_count']}")
    print(f"statuses: {summary['status_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

