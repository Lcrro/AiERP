"""Validate hash-bound tariff attribute decisions and compile review-only Item candidates."""

from __future__ import annotations

import argparse
from pathlib import Path

from nexterp_agent.item_master.tariff_attribute_review import (
    build_attribute_decision_template,
    compile_standard_type_sku_candidates,
    freeze_attribute_review_package,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = ROOT / "data/material_master/tariff_family_review_v0_1/fastener_review_v0_2"
DEFAULT_CANDIDATES = DEFAULT_DIR / "tariff_attribute_candidates.tsv"
DEFAULT_DECISIONS = DEFAULT_DIR / "tariff_attribute_decisions.tsv"
DEFAULT_ATTRIBUTE_RELEASE = DEFAULT_DIR / "attribute_frozen_release_v0_1"
DEFAULT_FAMILY_RELEASE = DEFAULT_DIR / "frozen_release_v0_1/tariff_family_release.tsv"
DEFAULT_COMPILED = DEFAULT_DIR / "standard_type_sku_candidates_v0_1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    template = sub.add_parser("template", help="生成哈希绑定的空白属性决定模板")
    template.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    template.add_argument("--output", type=Path, default=DEFAULT_DECISIONS)

    freeze = sub.add_parser("freeze", help="校验明确属性决定并生成 review-only 属性发布包")
    freeze.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    freeze.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS)
    freeze.add_argument("--output", type=Path, default=DEFAULT_ATTRIBUTE_RELEASE)

    compile_parser = sub.add_parser("compile", help="合并物料族和属性发布包为标准类型/SKU候选")
    compile_parser.add_argument("--family-release", type=Path, default=DEFAULT_FAMILY_RELEASE)
    compile_parser.add_argument("--attribute-release", type=Path, default=DEFAULT_ATTRIBUTE_RELEASE / "tariff_attribute_release.tsv")
    compile_parser.add_argument("--output", type=Path, default=DEFAULT_COMPILED)

    args = parser.parse_args()
    if args.command == "template":
        summary = build_attribute_decision_template(args.candidates.resolve(), args.output.resolve())
        print(f"attribute decision template: {args.output.resolve()}")
        print(f"candidate rows: {summary['row_count']}")
        print(f"candidate sha256: {summary['candidate_sha256']}")
        return 0
    if args.command == "freeze":
        summary = freeze_attribute_review_package(
            args.candidates.resolve(), args.decisions.resolve(), args.output.resolve()
        )
        print(f"attribute release: {args.output.resolve()}")
        print(f"summary: {summary}")
        return 0
    summary = compile_standard_type_sku_candidates(
        args.family_release.resolve(), args.attribute_release.resolve(), args.output.resolve()
    )
    print(f"standard type/SKU candidates: {args.output.resolve()}")
    print(f"summary: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
