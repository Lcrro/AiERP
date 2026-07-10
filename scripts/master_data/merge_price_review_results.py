from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


DEFAULT_SAMPLE = Path("data/material_master/price_review_samples/price_review_sample_10pct_by_family.tsv")
DEFAULT_REVIEW_DIR = Path("data/material_master/price_review_samples/review_outputs")
DEFAULT_OUTPUT_DIR = Path("data/material_master/price_review_samples")
DEFAULT_ROW_COMPARISON = DEFAULT_OUTPUT_DIR / "price_review_comparison_rows.tsv"
DEFAULT_FAMILY_FACTORS = DEFAULT_OUTPUT_DIR / "price_review_family_adjustment_factors.tsv"
DEFAULT_SUMMARY_JSON = DEFAULT_OUTPUT_DIR / "price_review_adjustment_summary.json"

REVIEW_FIELDS = [
    "item_code",
    "reviewed_rate",
    "currency",
    "unit",
    "confidence",
    "price_basis",
    "review_notes",
]

ROW_FIELDS = [
    "item_code",
    "item_name",
    "sku_name",
    "required_specs",
    "top_group",
    "sub_group",
    "material_family",
    "unit",
    "old_estimated_rate",
    "reviewed_rate",
    "ratio",
    "pct_diff",
    "confidence",
    "old_price_basis",
    "review_price_basis",
    "review_notes",
]

FAMILY_FIELDS = [
    "material_family",
    "sample_count",
    "high_count",
    "medium_count",
    "low_count",
    "old_avg_rate",
    "reviewed_avg_rate",
    "mean_ratio",
    "median_ratio",
    "suggested_adjustment_factor",
    "suggested_pct_diff",
    "min_ratio",
    "max_ratio",
    "reliability",
]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


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


def to_float(value: str, *, field: str, item_code: str) -> float:
    try:
        number = float(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"{item_code}: {field} must be numeric, got {value!r}") from exc
    if number <= 0:
        raise ValueError(f"{item_code}: {field} must be positive, got {value!r}")
    return number


def read_reviews(review_dir: Path) -> dict[str, dict[str, str]]:
    reviews: dict[str, dict[str, str]] = {}
    files = sorted(review_dir.glob("price_review_blind_batch_*_review.tsv"))
    if not files:
        raise FileNotFoundError(f"No review output files found under {review_dir}")
    for path in files:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if reader.fieldnames != REVIEW_FIELDS:
                raise ValueError(f"{path}: unexpected fields {reader.fieldnames}, expected {REVIEW_FIELDS}")
            for row in reader:
                item_code = row.get("item_code", "").strip()
                if not item_code:
                    raise ValueError(f"{path}: missing item_code")
                if item_code in reviews:
                    raise ValueError(f"Duplicate reviewed item_code: {item_code}")
                confidence = row.get("confidence", "").strip().lower()
                if confidence not in {"high", "medium", "low"}:
                    raise ValueError(f"{item_code}: invalid confidence {confidence!r}")
                currency = row.get("currency", "").strip().upper()
                if currency != "CNY":
                    raise ValueError(f"{item_code}: currency must be CNY")
                row["confidence"] = confidence
                row["currency"] = currency
                row["reviewed_rate"] = f"{to_float(row.get('reviewed_rate', ''), field='reviewed_rate', item_code=item_code):.2f}"
                reviews[item_code] = row
    return reviews


def reliability_for(sample_count: int, confidence_counts: Counter[str], ratios: list[float]) -> str:
    if sample_count >= 5 and confidence_counts["low"] == 0 and max(ratios) / min(ratios) <= 2.5:
        return "high"
    if sample_count >= 3 and confidence_counts["low"] <= sample_count / 2:
        return "medium"
    return "low"


def build_comparison(sample_rows: list[dict[str, str]], reviews: dict[str, dict[str, str]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    sample_by_code = {row["item_code"]: row for row in sample_rows}
    missing = sorted(set(sample_by_code) - set(reviews))
    extra = sorted(set(reviews) - set(sample_by_code))
    if missing:
        raise ValueError(f"Missing review rows: {missing}")
    if extra:
        raise ValueError(f"Unexpected review rows: {extra}")

    comparison_rows: list[dict[str, object]] = []
    grouped: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for item_code, sample in sample_by_code.items():
        review = reviews[item_code]
        old_rate = to_float(sample["estimated_rate"], field="estimated_rate", item_code=item_code)
        reviewed_rate = to_float(review["reviewed_rate"], field="reviewed_rate", item_code=item_code)
        ratio = reviewed_rate / old_rate
        row = {
            "item_code": item_code,
            "item_name": sample.get("item_name", ""),
            "sku_name": sample.get("sku_name", ""),
            "required_specs": sample.get("required_specs", ""),
            "top_group": sample.get("top_group", ""),
            "sub_group": sample.get("sub_group", ""),
            "material_family": sample.get("material_family", ""),
            "unit": sample.get("unit", ""),
            "old_estimated_rate": f"{old_rate:.2f}",
            "reviewed_rate": f"{reviewed_rate:.2f}",
            "ratio": f"{ratio:.4f}",
            "pct_diff": f"{(ratio - 1) * 100:.2f}%",
            "confidence": review["confidence"],
            "old_price_basis": sample.get("price_basis", ""),
            "review_price_basis": review.get("price_basis", ""),
            "review_notes": review.get("review_notes", ""),
        }
        comparison_rows.append(row)
        grouped[row["material_family"]].append(row)

    family_rows: list[dict[str, object]] = []
    for family, rows in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        ratios = [float(row["ratio"]) for row in rows]
        old_rates = [float(row["old_estimated_rate"]) for row in rows]
        reviewed_rates = [float(row["reviewed_rate"]) for row in rows]
        confidence_counts = Counter(str(row["confidence"]) for row in rows)
        median_ratio = statistics.median(ratios)
        family_rows.append(
            {
                "material_family": family,
                "sample_count": len(rows),
                "high_count": confidence_counts["high"],
                "medium_count": confidence_counts["medium"],
                "low_count": confidence_counts["low"],
                "old_avg_rate": f"{statistics.mean(old_rates):.2f}",
                "reviewed_avg_rate": f"{statistics.mean(reviewed_rates):.2f}",
                "mean_ratio": f"{statistics.mean(ratios):.4f}",
                "median_ratio": f"{median_ratio:.4f}",
                "suggested_adjustment_factor": f"{median_ratio:.4f}",
                "suggested_pct_diff": f"{(median_ratio - 1) * 100:.2f}%",
                "min_ratio": f"{min(ratios):.4f}",
                "max_ratio": f"{max(ratios):.4f}",
                "reliability": reliability_for(len(rows), confidence_counts, ratios),
            }
        )
    return comparison_rows, family_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge blind price reviews and compute family-level adjustment factors.")
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--review-dir", type=Path, default=DEFAULT_REVIEW_DIR)
    parser.add_argument("--row-output", type=Path, default=DEFAULT_ROW_COMPARISON)
    parser.add_argument("--family-output", type=Path, default=DEFAULT_FAMILY_FACTORS)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_JSON)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sample_rows = read_tsv(args.sample)
    reviews = read_reviews(args.review_dir)
    comparison_rows, family_rows = build_comparison(sample_rows, reviews)
    write_tsv(args.row_output, comparison_rows, ROW_FIELDS)
    write_tsv(args.family_output, family_rows, FAMILY_FIELDS)
    summary = {
        "sample": str(args.sample),
        "review_dir": str(args.review_dir),
        "row_output": str(args.row_output),
        "family_output": str(args.family_output),
        "generated_at": date.today().isoformat(),
        "reviewed_count": len(comparison_rows),
        "family_count": len(family_rows),
        "overall_median_ratio": f"{statistics.median([float(row['ratio']) for row in comparison_rows]):.4f}",
        "overall_mean_ratio": f"{statistics.mean([float(row['ratio']) for row in comparison_rows]):.4f}",
    }
    write_json(args.summary, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
