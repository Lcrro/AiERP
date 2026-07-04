from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs" / "material_master" / "sku_governance"


INPUT_COLUMNS = [
    "item_code",
    "standard_item_name",
    "standard_sku_name",
    "minimal_required_specs",
    "standard_uom",
    "brand",
    "aliases",
    "removed_default_fields",
    "default_fill_basis",
    "merge_group",
    "merge_reason",
    "source_item_code",
    "governance_reason",
]

UNIQUE_COLUMNS = [
    "canonical_item_code",
    "standard_item_name",
    "standard_sku_name",
    "minimal_required_specs",
    "standard_uom",
    "source_uoms",
    "unit_resolution",
    "brand",
    "aliases",
    "removed_default_fields",
    "default_fill_basis",
    "merged_from_item_codes",
    "merged_count",
    "merge_reasons",
    "governance_reasons",
]

DUPLICATE_COLUMNS = [
    "standard_sku_name",
    "minimal_required_specs",
    "standard_uom",
    "source_uoms",
    "unit_resolution",
    "brand",
    "merged_from_item_codes",
    "merged_count",
    "canonical_item_code",
    "merge_reasons",
]

STANDARD_UOM_PRIORITY = ["个", "套", "把", "支", "只", "根", "米", "卷", "包", "箱", "Kg"]


def latest_rows_file(output_dir: Path) -> Path:
    files = sorted(output_dir.glob("deepseek_sku_governance_rows_*.tsv"), key=lambda path: path.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"No DeepSeek SKU governance row files found in {output_dir}")
    return files[-1]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        missing_columns = [column for column in INPUT_COLUMNS if column not in (reader.fieldnames or [])]
        if missing_columns:
            raise ValueError(f"{path} is missing columns: {missing_columns}")
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def split_semicolon(value: object) -> list[str]:
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            for split_item in split_semicolon(item):
                if split_item not in parts:
                    parts.append(split_item)
        return parts
    if value is None:
        return []
    text = str(value)
    parts: list[str] = []
    for chunk in text.replace(",", "；").split("；"):
        stripped = chunk.strip()
        if stripped and stripped not in parts:
            parts.append(stripped)
    return parts


def join_unique(values: list[str]) -> str:
    merged: list[str] = []
    for value in values:
        for part in split_semicolon(value):
            if part not in merged:
                merged.append(part)
    return "；".join(merged)


def clean_gongyuan_miswrite(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    text = re.sub(r"公元\s*DN\s*([0-9A-Za-z.]+)", r"公称直径：DN\1", text)
    text = re.sub(r"公元\s*([0-9]+(?:\.[0-9]+)?)", r"规格/口径：\1", text)
    replacements = {
        "品牌：公元→公称误写": "",
        "品牌：公元->公称误写": "",
        "品牌：公元": "",
        "品牌公元，": "",
        "品牌公元": "",
        "“公元”为“公称”误写，非品牌": "公称信息已按口径处理，非品牌",
        "公元为公称误写，非品牌": "公称信息已按口径处理，非品牌",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = text.replace("公元", "公称")
    return "；".join(split_semicolon(text))


def remove_gongyuan_parts(value: str) -> str:
    return "；".join(part for part in split_semicolon(value) if "公元" not in part)


def normalize_for_merge(row: dict[str, str]) -> dict[str, str]:
    normalized = dict(row)
    for field in ("brand", "aliases", "removed_default_fields"):
        normalized[field] = remove_gongyuan_parts(normalized.get(field, ""))
    for field in (
        "standard_sku_name",
        "minimal_required_specs",
        "default_fill_basis",
        "merge_reason",
        "governance_reason",
    ):
        normalized[field] = clean_gongyuan_miswrite(normalized.get(field, ""))
    if not normalized.get("minimal_required_specs", "").strip():
        normalized["minimal_required_specs"] = "规格：通用"
        basis = normalized.get("default_fill_basis", "").strip()
        addition = "后处理补齐：原输出最小规格为空，按初始物料清单口径设为规格：通用"
        normalized["default_fill_basis"] = "；".join(part for part in (basis, addition) if part)
        reason = normalized.get("governance_reason", "").strip()
        normalized["governance_reason"] = "；".join(part for part in (reason, addition) if part)
    return normalized


def governance_key(row: dict[str, str]) -> tuple[str, str]:
    return (
        row["standard_sku_name"].strip(),
        row["minimal_required_specs"].strip(),
    )


def choose_standard_uom(group: list[dict[str, str]]) -> tuple[str, str, str]:
    source_uoms = [row["standard_uom"].strip() for row in group if row["standard_uom"].strip()]
    unique_uoms = []
    for uom in source_uoms:
        if uom not in unique_uoms:
            unique_uoms.append(uom)
    if not unique_uoms:
        return "", "", ""
    for preferred in STANDARD_UOM_PRIORITY:
        if preferred in unique_uoms:
            chosen = preferred
            break
    else:
        chosen = unique_uoms[0]
    source_uoms_text = "；".join(unique_uoms)
    if len(unique_uoms) == 1:
        resolution = "来源单位一致"
    else:
        resolution = f"来源单位不一致，统一为{chosen}"
    return chosen, source_uoms_text, resolution


def merge_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        row = normalize_for_merge(row)
        key = governance_key(row)
        if not all(key):
            raise ValueError(f"Row has incomplete governance key: {row}")
        grouped[key].append(row)

    unique_rows: list[dict[str, str]] = []
    duplicate_rows: list[dict[str, str]] = []

    for key, group in sorted(grouped.items(), key=lambda item: item[0]):
        standard_sku_name, minimal_required_specs = key
        canonical = sorted(group, key=lambda row: row["item_code"])[0]
        item_codes = sorted({row["item_code"] for row in group})
        standard_uom, source_uoms, unit_resolution = choose_standard_uom(group)
        row = {
            "canonical_item_code": canonical["item_code"],
            "standard_item_name": canonical["standard_item_name"],
            "standard_sku_name": standard_sku_name,
            "minimal_required_specs": minimal_required_specs,
            "standard_uom": standard_uom,
            "source_uoms": source_uoms,
            "unit_resolution": unit_resolution,
            "brand": join_unique([row.get("brand", "") for row in group]),
            "aliases": join_unique([row["aliases"] for row in group]),
            "removed_default_fields": join_unique([row["removed_default_fields"] for row in group]),
            "default_fill_basis": join_unique([row["default_fill_basis"] for row in group]),
            "merged_from_item_codes": "；".join(item_codes),
            "merged_count": str(len(item_codes)),
            "merge_reasons": join_unique([row["merge_reason"] for row in group]),
            "governance_reasons": join_unique([row["governance_reason"] for row in group]),
        }
        unique_rows.append(row)
        if len(group) > 1:
            duplicate_rows.append(
                {
                    "standard_sku_name": standard_sku_name,
                    "minimal_required_specs": minimal_required_specs,
                    "standard_uom": standard_uom,
                    "source_uoms": source_uoms,
                    "unit_resolution": unit_resolution,
                    "brand": row["brand"],
                    "merged_from_item_codes": "；".join(item_codes),
                    "merged_count": str(len(item_codes)),
                    "canonical_item_code": canonical["item_code"],
                    "merge_reasons": row["merge_reasons"],
                }
            )

    return unique_rows, duplicate_rows


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge duplicate DeepSeek SKU governance rows into unique SKU records.")
    parser.add_argument("--input", type=Path, default=None, help="DeepSeek governance rows TSV. Defaults to latest rows file.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input or latest_rows_file(args.output_dir)
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")

    rows = read_rows(input_path)
    unique_rows, duplicate_rows = merge_rows(rows)

    unique_path = args.output_dir / f"deepseek_sku_governance_unique_{timestamp}.tsv"
    duplicate_path = args.output_dir / f"deepseek_sku_governance_duplicates_{timestamp}.tsv"
    write_tsv(unique_path, unique_rows, UNIQUE_COLUMNS)
    write_tsv(duplicate_path, duplicate_rows, DUPLICATE_COLUMNS)

    duplicate_source_count = sum(int(row["merged_count"]) for row in duplicate_rows)
    redundant_count = duplicate_source_count - len(duplicate_rows)
    print(
        {
            "input": str(input_path),
            "input_rows": len(rows),
            "unique_rows": len(unique_rows),
            "duplicate_groups": len(duplicate_rows),
            "duplicate_source_rows": duplicate_source_count,
            "redundant_rows_removed": redundant_count,
            "unique_tsv": str(unique_path),
            "duplicates_tsv": str(duplicate_path),
        }
    )


if __name__ == "__main__":
    main()
