from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.master_data.build_price_ready_material_release import (
    browser_rows,
    build_categories,
    build_summary,
    duplicate_rows,
)


DEFAULT_RELEASE = Path("data/material_master/price_ready_release_v0_1/material_master_price_ready_release_v0_1.tsv")
DEFAULT_FACTORS = Path("data/material_master/price_review_samples/price_review_family_adjustment_factors.tsv")
DEFAULT_OUTPUT = Path("data/material_master/price_review_samples/material_master_price_adjusted_by_family.tsv")
DEFAULT_ADJUSTED_RELEASE = Path("data/material_master/price_ready_release_v0_1/material_master_price_ready_release_v0_1_family_adjusted.tsv")
DEFAULT_BROWSER_JSON = Path("data/material_master/price_ready_release_v0_1/material_master_price_ready_browser_data.json")
DEFAULT_SUMMARY = Path("data/material_master/price_review_samples/material_master_price_adjusted_by_family_summary.json")
MONEY_QUANT = Decimal("0.01")

OUTPUT_FIELDS = [
    "item_code",
    "item_name",
    "sku_name",
    "required_specs",
    "top_group",
    "sub_group",
    "material_family",
    "unit",
    "old_estimated_rate",
    "adjustment_factor",
    "adjusted_estimated_rate",
    "currency",
    "factor_sample_count",
    "factor_reliability",
    "factor_pct_diff",
    "price_basis",
    "adjustment_basis",
    "default_fill_basis",
    "aliases",
    "brand",
    "model",
    "source_item_codes",
    "merged_count",
]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def read_tsv_with_fields(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader), list(reader.fieldnames or [])


def write_tsv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def to_decimal(value: str, default: str = "1") -> Decimal:
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return Decimal(default)


def load_factors(path: Path) -> dict[str, dict[str, str]]:
    return {row["material_family"]: row for row in read_tsv(path)}


def money(value: Decimal) -> str:
    return str(value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP))


def adjusted_rate(old_rate: Decimal, factor: Decimal) -> str:
    return money(old_rate * factor)


def append_basis(value: str, note: str) -> str:
    value = (value or "").strip()
    if not value:
        return note
    if note in value:
        return value
    return f"{value}；{note}"


def build_adjusted_rows(
    release_rows: list[dict[str, str]],
    factors: dict[str, dict[str, str]],
) -> tuple[list[dict[str, object]], list[dict[str, str]], dict[str, object]]:
    output_rows: list[dict[str, object]] = []
    adjusted_release_rows: list[dict[str, str]] = []
    reliability_counts: Counter[str] = Counter()
    sample_count_counts: Counter[str] = Counter()
    factor_values: list[Decimal] = []

    for row in release_rows:
        family = row.get("material_family", "")
        factor_row = factors.get(family, {})
        factor = to_decimal(factor_row.get("suggested_adjustment_factor", "1"), default="1")
        old_rate = to_decimal(row.get("estimated_rate", "0"), default="0")
        new_rate = adjusted_rate(old_rate, factor)
        reliability = factor_row.get("reliability", "missing")
        sample_count = factor_row.get("sample_count", "0")
        reliability_counts[reliability] += 1
        sample_count_counts[sample_count] += 1
        factor_values.append(factor)
        basis = (
            f"按物料族“{family}”抽样复核中位数调整；"
            f"样本数={sample_count}；可靠性={reliability}；"
            f"调整系数={factor:.4f}；金额按四舍五入保留两位小数。"
        )

        output_rows.append(
            {
                **row,
                "old_estimated_rate": row.get("estimated_rate", ""),
                "adjustment_factor": f"{factor:.4f}",
                "adjusted_estimated_rate": new_rate,
                "factor_sample_count": sample_count,
                "factor_reliability": reliability,
                "factor_pct_diff": factor_row.get("suggested_pct_diff", "0.00%"),
                "adjustment_basis": basis,
            }
        )
        adjusted_release_row = dict(row)
        adjusted_release_row["estimated_rate"] = new_rate
        adjusted_release_row["price_basis"] = append_basis(row.get("price_basis", ""), basis)
        adjusted_release_rows.append(adjusted_release_row)

    summary = {
        "row_count": len(output_rows),
        "family_count": len({row.get("material_family", "") for row in release_rows}),
        "factor_family_count": len(factors),
        "generated_at": date.today().isoformat(),
        "reliability_row_counts": dict(reliability_counts),
        "sample_count_row_counts": dict(sample_count_counts),
        "min_factor": f"{min(factor_values):.4f}" if factor_values else None,
        "max_factor": f"{max(factor_values):.4f}" if factor_values else None,
        "rounding": "Decimal ROUND_HALF_UP, 2 decimal places",
    }
    return output_rows, adjusted_release_rows, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply family-level price review adjustment factors to the material master.")
    parser.add_argument("--release", type=Path, default=DEFAULT_RELEASE)
    parser.add_argument("--factors", type=Path, default=DEFAULT_FACTORS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--adjusted-release", type=Path, default=DEFAULT_ADJUSTED_RELEASE)
    parser.add_argument("--browser-json", type=Path, default=DEFAULT_BROWSER_JSON)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    release_rows, release_fields = read_tsv_with_fields(args.release)
    factors = load_factors(args.factors)
    output_rows, adjusted_release_rows, summary = build_adjusted_rows(release_rows, factors)
    write_tsv(args.output, output_rows, OUTPUT_FIELDS)
    write_tsv(args.adjusted_release, adjusted_release_rows, release_fields)
    browser_ready_rows = browser_rows(adjusted_release_rows)
    browser_summary = build_summary(browser_ready_rows, duplicate_rows(adjusted_release_rows), args.adjusted_release)
    browser_summary.update(
        {
            "price_adjusted_by_family": "yes",
            "price_adjustment_factors": str(args.factors),
            "rounding": "Decimal ROUND_HALF_UP, 2 decimal places",
        }
    )
    write_json(
        args.browser_json,
        {
            "generated_at": date.today().isoformat(),
            "source": str(args.adjusted_release),
            "price_ready_source": str(args.release),
            "price_adjustment_factors": str(args.factors),
            "family_rules_source": "",
            "family_rules_count": 0,
            "summary": browser_summary,
            "categories": build_categories(browser_ready_rows),
            "family_rule_impacts": [],
            "rows": browser_ready_rows,
        },
    )
    summary.update(
        {
            "release": str(args.release),
            "factors": str(args.factors),
            "output": str(args.output),
            "adjusted_release": str(args.adjusted_release),
            "browser_json": str(args.browser_json),
        }
    )
    write_json(args.summary, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
