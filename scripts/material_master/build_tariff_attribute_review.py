"""Build source-backed tariff SKU attribute candidates for review."""

from __future__ import annotations

import argparse
from pathlib import Path

from nexterp_agent.item_master.tariff_attribute_review import build_attribute_review


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data/material_master/tariff_family_review_v0_1/fastener_review_v0_2/tariff_family_candidates.tsv"
DEFAULT_OUTPUT = ROOT / "data/material_master/tariff_family_review_v0_1/fastener_review_v0_2"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary = build_attribute_review(args.input.resolve(), args.output.resolve())
    print(f"attribute review: {args.output.resolve()}")
    print(f"rows: {summary['row_count']}")
    print(f"status: {summary['attribute_status_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

