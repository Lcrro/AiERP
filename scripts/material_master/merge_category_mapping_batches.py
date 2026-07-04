from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECLASS_DIR = REPO_ROOT / "data" / "material_master" / "reclassification"
DEFAULT_OUTPUT_PATH = DEFAULT_RECLASS_DIR / "material_category_mapping.tsv"
DEFAULT_SUMMARY_PATH = DEFAULT_RECLASS_DIR / "material_category_mapping_summary.json"

INPUT_FIELDS = [
    "group_id",
    "item_name",
    "sku_count",
    "old_groups",
    "stock_uoms",
    "quality_levels",
    "agent_use_policies",
    "sample_skus_specs_aliases",
]

OUTPUT_FIELDS = [
    "group_id",
    "item_name",
    "old_groups",
    "sku_count",
    "suggested_category",
    "suggested_subcategory",
    "needs_split",
    "split_basis",
    "confidence",
    "reason",
]

ALLOWED_CATEGORIES = {
    "建筑材料",
    "金属材料",
    "管材管件阀门",
    "紧固件与连接件",
    "电气电料",
    "弱电安防",
    "劳保防护",
    "安全消防",
    "工具量具",
    "电动气动工具",
    "工具耗材",
    "施工机具设备",
    "设备备件",
    "液压气动",
    "化工胶粘涂料",
    "焊接切割",
    "吊装索具",
    "清洁办公后勤",
    "包装覆盖周转",
    "定制加工件",
    "服务租赁运输",
}

ALLOWED_SPLIT = {"yes", "no"}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}


def read_tsv(path: Path, expected_fields: list[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != expected_fields:
            raise ValueError(f"{path}: unexpected fields {reader.fieldnames}")
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def validate_rows(
    source_rows: list[dict[str, str]],
    mapping_rows: list[dict[str, str]],
) -> list[str]:
    errors: list[str] = []
    source_ids = {row["group_id"] for row in source_rows}
    seen: set[str] = set()

    for row in mapping_rows:
        group_id = row["group_id"]
        if group_id not in source_ids:
            errors.append(f"{group_id}: not found in source groups")
        if group_id in seen:
            errors.append(f"{group_id}: duplicate mapping row")
        seen.add(group_id)

        if not row["item_name"]:
            errors.append(f"{group_id}: missing item_name")
        if row["suggested_category"] not in ALLOWED_CATEGORIES:
            errors.append(f"{group_id}: invalid suggested_category {row['suggested_category']!r}")
        if not row["suggested_subcategory"]:
            errors.append(f"{group_id}: missing suggested_subcategory")
        if row["needs_split"] not in ALLOWED_SPLIT:
            errors.append(f"{group_id}: invalid needs_split {row['needs_split']!r}")
        if row["confidence"] not in ALLOWED_CONFIDENCE:
            errors.append(f"{group_id}: invalid confidence {row['confidence']!r}")
        if row["needs_split"] == "yes" and not row["split_basis"]:
            errors.append(f"{group_id}: needs_split is yes but split_basis is empty")
        if not row["reason"]:
            errors.append(f"{group_id}: missing reason")

    missing = sorted(source_ids - seen)
    if missing:
        preview = ", ".join(missing[:20])
        suffix = "..." if len(missing) > 20 else ""
        errors.append(f"missing mapping rows: {len(missing)} ({preview}{suffix})")

    return errors


def merge_batches(reclass_dir: Path) -> tuple[list[dict[str, str]], dict[str, object]]:
    source_rows = read_tsv(reclass_dir / "item_name_groups_all.tsv", INPUT_FIELDS)
    batch_paths = sorted(reclass_dir.glob("category_mapping_batch_*.tsv"))
    if not batch_paths:
        raise FileNotFoundError(f"No category_mapping_batch_*.tsv files found in {reclass_dir}")

    merged: list[dict[str, str]] = []
    batch_counts: dict[str, int] = {}
    for path in batch_paths:
        rows = read_tsv(path, OUTPUT_FIELDS)
        batch_counts[path.name] = len(rows)
        merged.extend(rows)

    errors = validate_rows(source_rows, merged)
    if errors:
        message = "\n".join(errors[:80])
        suffix = "\n..." if len(errors) > 80 else ""
        raise ValueError(f"Category mapping validation failed with {len(errors)} errors:\n{message}{suffix}")

    merged.sort(key=lambda row: row["group_id"])
    summary = {
        "source_group_count": len(source_rows),
        "mapping_count": len(merged),
        "batch_counts": batch_counts,
        "category_counts": dict(Counter(row["suggested_category"] for row in merged).most_common()),
        "confidence_counts": dict(Counter(row["confidence"] for row in merged).most_common()),
        "needs_split_counts": dict(Counter(row["needs_split"] for row in merged).most_common()),
    }
    return merged, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge and validate material category mapping batches.")
    parser.add_argument("--reclass-dir", type=Path, default=DEFAULT_RECLASS_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows, summary = merge_batches(args.reclass_dir)
    write_tsv(args.output, rows, OUTPUT_FIELDS)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
