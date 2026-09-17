"""Create decision templates and freeze explicitly approved tariff mappings."""

from __future__ import annotations

import argparse
from pathlib import Path

from nexterp_agent.item_master.tariff_family_review import (
    build_decision_template,
    freeze_review_package,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = ROOT / "data/material_master/tariff_family_review_v0_1"
DEFAULT_CANDIDATES = DEFAULT_DIR / "tariff_family_candidates.tsv"
DEFAULT_INTERNAL_RELEASE = ROOT / "data/material_master/release_v1_1/material_master_release_v1_1.tsv"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    template = sub.add_parser("template", help="生成空白人工决策模板")
    template.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    template.add_argument("--output", type=Path, default=DEFAULT_DIR / "tariff_family_decisions.tsv")
    freeze = sub.add_parser("freeze", help="冻结显式 approve 的映射")
    freeze.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    freeze.add_argument("--decisions", type=Path, default=DEFAULT_DIR / "tariff_family_decisions.tsv")
    freeze.add_argument("--output", type=Path, default=DEFAULT_DIR / "frozen_release_v0_1")
    freeze.add_argument("--internal-release", type=Path, default=DEFAULT_INTERNAL_RELEASE)
    args = parser.parse_args()
    if args.command == "template":
        metadata = build_decision_template(args.candidates.resolve(), args.output.resolve())
        print(f"decision template: {args.output.resolve()}")
        print(f"candidate rows: {metadata['row_count']}")
        print(f"candidate sha256: {metadata['candidate_sha256']}")
        return 0
    summary = freeze_review_package(
        args.candidates.resolve(),
        args.decisions.resolve(),
        args.output.resolve(),
        args.internal_release.resolve(),
    )
    print(f"frozen review release: {args.output.resolve()}")
    print(f"summary: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

