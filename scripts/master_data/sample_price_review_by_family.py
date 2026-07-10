from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import defaultdict
from datetime import date
from pathlib import Path


DEFAULT_INPUT = Path("data/material_master/price_ready_release_v0_1/material_master_price_ready_release_v0_1.tsv")
DEFAULT_OUTPUT_DIR = Path("data/material_master/price_review_samples")
DEFAULT_SAMPLE_TSV = DEFAULT_OUTPUT_DIR / "price_review_sample_10pct_by_family.tsv"
DEFAULT_SUMMARY_JSON = DEFAULT_OUTPUT_DIR / "price_review_sample_10pct_by_family_summary.json"
DEFAULT_RATE = 0.10
DEFAULT_SEED = 20260708

OUTPUT_FIELDS = [
    "sample_group",
    "family_total_count",
    "family_sample_count",
    "item_code",
    "item_name",
    "sku_name",
    "required_specs",
    "top_group",
    "sub_group",
    "material_family",
    "unit",
    "estimated_rate",
    "currency",
    "price_basis",
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


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sample_count(total: int, rate: float) -> int:
    if total <= 0:
        return 0
    return max(1, math.ceil(total * rate))


def sample_by_family(rows: list[dict[str, str]], rate: float, seed: int) -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    grouped: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row.get("material_family") or "未分物料族"].append(row)

    rng = random.Random(seed)
    sampled_rows: list[dict[str, str]] = []
    family_summary: list[dict[str, object]] = []

    for family, family_rows in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        family_rows = sorted(family_rows, key=lambda row: row.get("item_code", ""))
        count = sample_count(len(family_rows), rate)
        selected = sorted(rng.sample(family_rows, count), key=lambda row: row.get("item_code", ""))
        family_summary.append(
            {
                "material_family": family,
                "total_count": len(family_rows),
                "sample_count": count,
                "sample_rate": rate,
            }
        )
        for row in selected:
            sampled_rows.append(
                {
                    **row,
                    "sample_group": family,
                    "family_total_count": str(len(family_rows)),
                    "family_sample_count": str(count),
                }
            )

    return sampled_rows, family_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Randomly sample material rows for price review by material family.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_SAMPLE_TSV)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_JSON)
    parser.add_argument("--rate", type=float, default=DEFAULT_RATE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 0 < args.rate <= 1:
        raise ValueError("--rate must be between 0 and 1")

    rows = read_tsv(args.input)
    sampled_rows, family_summary = sample_by_family(rows, args.rate, args.seed)
    write_tsv(args.output, sampled_rows, OUTPUT_FIELDS)

    payload = {
        "input": str(args.input),
        "output": str(args.output),
        "generated_at": date.today().isoformat(),
        "seed": args.seed,
        "sample_rate": args.rate,
        "source_count": len(rows),
        "family_count": len(family_summary),
        "sample_count": len(sampled_rows),
        "family_summary": family_summary,
    }
    write_json(args.summary, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
