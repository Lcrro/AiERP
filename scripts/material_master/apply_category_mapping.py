from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MASTER_PATH = REPO_ROOT / "data" / "material_master" / "material_master.tsv"
DEFAULT_MAPPING_PATH = REPO_ROOT / "data" / "material_master" / "reclassification" / "material_category_mapping.tsv"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "data" / "material_master" / "reclassification" / "material_master_reclassified.tsv"
DEFAULT_SUMMARY_PATH = (
    REPO_ROOT / "data" / "material_master" / "reclassification" / "material_master_reclassified_summary.json"
)

MASTER_FIELDS = [
    "item_code",
    "item_name",
    "required_specs",
    "optional_specs",
    "item_group",
    "stock_uom",
    "purchase_uom",
    "conversion_factor",
    "aliases",
    "search_keywords",
    "brand",
    "model",
    "status",
    "quality_level",
    "agent_use_policy",
    "source_refs",
    "governance_note",
    "updated_at",
]

MAPPING_FIELDS = [
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


def append_text(existing: str, addition: str) -> str:
    if not existing:
        return addition
    if addition in existing:
        return existing
    return f"{existing}；{addition}"


def build_mapping(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    mapping: dict[str, dict[str, str]] = {}
    for row in rows:
        item_name = row["item_name"]
        if item_name in mapping:
            raise ValueError(f"Duplicate item_name in mapping: {item_name}")
        mapping[item_name] = row
    return mapping


def apply_mapping(
    master_rows: list[dict[str, str]],
    mapping_rows: list[dict[str, str]],
    updated_at: str,
) -> tuple[list[dict[str, str]], dict[str, object]]:
    mapping = build_mapping(mapping_rows)
    missing_names = sorted({row["item_name"] for row in master_rows} - set(mapping))
    if missing_names:
        preview = ", ".join(missing_names[:20])
        suffix = "..." if len(missing_names) > 20 else ""
        raise ValueError(f"Missing category mapping for {len(missing_names)} item names: {preview}{suffix}")

    output: list[dict[str, str]] = []
    changed = 0
    unchanged = 0
    split_review_rows = 0
    category_counts: Counter[str] = Counter()
    subcategory_counts: Counter[str] = Counter()

    for row in master_rows:
        result = dict(row)
        mapping_row = mapping[row["item_name"]]
        old_group = row["item_group"]
        new_group = f"{mapping_row['suggested_category']}/{mapping_row['suggested_subcategory']}"
        result["item_group"] = new_group
        result["updated_at"] = updated_at

        if old_group == new_group:
            unchanged += 1
        else:
            changed += 1
            result["search_keywords"] = append_text(result["search_keywords"], old_group)
            note = (
                f"重分类：{old_group} -> {new_group}；"
                f"分类置信度：{mapping_row['confidence']}；{mapping_row['reason']}"
            )
            result["governance_note"] = append_text(result["governance_note"], note)

        if mapping_row["needs_split"] == "yes":
            split_review_rows += 1
            split_note = f"分类拆分待复核：{mapping_row['split_basis']}；{mapping_row['reason']}"
            result["governance_note"] = append_text(result["governance_note"], split_note)

        category_counts[mapping_row["suggested_category"]] += 1
        subcategory_counts[new_group] += 1
        output.append(result)

    summary = {
        "source_rows": len(master_rows),
        "mapping_rows": len(mapping_rows),
        "output_rows": len(output),
        "changed_item_group_rows": changed,
        "unchanged_item_group_rows": unchanged,
        "split_review_rows": split_review_rows,
        "category_counts": dict(category_counts.most_common()),
        "top_subcategory_counts": dict(subcategory_counts.most_common(40)),
        "updated_at": updated_at,
    }
    return output, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply item-name category mapping to material master TSV.")
    parser.add_argument("--master", type=Path, default=DEFAULT_MASTER_PATH)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--updated-at", default=date.today().isoformat())
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_rows, summary = apply_mapping(
        read_tsv(args.master, MASTER_FIELDS),
        read_tsv(args.mapping, MAPPING_FIELDS),
        args.updated_at,
    )
    write_tsv(args.output, output_rows, MASTER_FIELDS)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
