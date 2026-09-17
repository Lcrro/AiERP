"""Build the review-only tariff to Nexterp material-family package."""

from __future__ import annotations

import argparse
from pathlib import Path

from nexterp_agent.item_master.tariff_family_review import build_review_package


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / ".runtime/tariff-extraction"
DEFAULT_OUTPUT = ROOT / "data/material_master/tariff_family_review_v0_1"
DEFAULT_INTERNAL_RELEASE = ROOT / "data/material_master/release_v1_1/material_master_release_v1_1.tsv"


def latest_tariff_nodes() -> Path:
    candidates = sorted(DEFAULT_INPUT.glob("*/tariff-nodes.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError("未找到 tariff-nodes.jsonl，请先完成全量税则提取任务")
    return candidates[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=None, help="tariff-nodes.jsonl 路径")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--internal-release", type=Path, default=DEFAULT_INTERNAL_RELEASE)
    args = parser.parse_args()
    input_path = (args.input or latest_tariff_nodes()).resolve()
    summary = build_review_package(input_path, args.output.resolve(), args.internal_release.resolve())
    print(f"review package: {args.output.resolve()}")
    print(f"rows: {summary['row_count']}")
    print(f"statuses: {summary['status_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

