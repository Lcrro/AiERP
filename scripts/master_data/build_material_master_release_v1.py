from __future__ import annotations

import argparse
import csv
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = (
    REPO_ROOT
    / "data"
    / "material_master"
    / "price_ready_release_v0_1"
    / "material_master_price_ready_release_v0_1_family_adjusted.tsv"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "material_master" / "release_v1_0"
DEFAULT_OUTPUT = DEFAULT_OUTPUT_DIR / "material_master_release_v1_0.tsv"
DEFAULT_SUMMARY = DEFAULT_OUTPUT_DIR / "material_master_release_v1_0_summary.json"

OUTPUT_FIELDS = [
    "item_code",
    "item_name",
    "sku_name",
    "required_specs",
    "optional_specs",
    "item_group",
    "top_group",
    "sub_group",
    "material_family",
    "stock_uom",
    "purchase_uom",
    "conversion_factor",
    "estimated_rate",
    "currency",
    "price_basis",
    "aliases",
    "search_keywords",
    "brand",
    "model",
    "status",
    "quality_level",
    "agent_use_policy",
    "source_item_codes",
    "merged_count",
    "governance_note",
    "updated_at",
]

# These codes already exist in the independent sandbox with incompatible
# stock units and posted scenario transactions. v1 receives fresh stable
# codes while preserving the old codes in source_item_codes for traceability.
SANDBOX_CODE_CONFLICTS = {
    "ELEC-000006": "ELEC-000006-V1",
    "ELEC-000007": "ELEC-000007-V1",
    "MAT-000159": "MAT-000159-V1",
    "MAT-CEM-000004": "MAT-CEM-000004-V1",
    "METAL-000001": "METAL-000001-V1",
    "SAFE-000006": "SAFE-000006-V1",
    "SAFE-000007": "SAFE-000007-V1",
}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build_search_keywords(row: dict[str, str]) -> str:
    values = [
        row.get("item_code", ""),
        row.get("item_name", ""),
        row.get("sku_name", ""),
        row.get("required_specs", ""),
        row.get("aliases", ""),
        row.get("material_family", ""),
        row.get("brand", ""),
        row.get("model", ""),
    ]
    return " ".join(value.strip() for value in values if value and value.strip())


def normalize_row(row: dict[str, str]) -> dict[str, str]:
    source_item_code = row.get("item_code", "").strip()
    release_item_code = SANDBOX_CODE_CONFLICTS.get(source_item_code, source_item_code)
    stock_uom = row.get("unit", "").strip()
    rate = Decimal(row.get("estimated_rate") or "0")
    governance_notes: list[str] = []

    if row.get("item_code") == "PIPE-000411":
        stock_uom = "根"
        rate = (rate * Decimal("6")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        governance_notes.append("固定长度6m作为一个SKU，单位由米改为根，测试价按6米折算。")

    normalized = {
        "item_code": release_item_code,
        "item_name": row.get("item_name", "").strip(),
        "sku_name": row.get("sku_name", "").strip(),
        "required_specs": row.get("required_specs", "").strip(),
        "optional_specs": "",
        "item_group": row.get("item_group", "").strip(),
        "top_group": row.get("top_group", "").strip(),
        "sub_group": row.get("sub_group", "").strip(),
        "material_family": row.get("material_family", "").strip(),
        "stock_uom": stock_uom,
        "purchase_uom": stock_uom,
        "conversion_factor": "1",
        "estimated_rate": f"{rate.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}",
        "currency": row.get("currency", "CNY").strip() or "CNY",
        "price_basis": row.get("price_basis", "").strip(),
        "aliases": row.get("aliases", "").strip(),
        "search_keywords": "",
        "brand": row.get("brand", "").strip(),
        "model": row.get("model", "").strip(),
        "status": "active",
        "quality_level": "standard",
        "agent_use_policy": "auto_select_allowed",
        "source_item_codes": row.get("source_item_codes", "").strip() or source_item_code,
        "merged_count": row.get("merged_count", "1").strip() or "1",
        "governance_note": "；".join(governance_notes),
        "updated_at": row.get("updated_at", "").strip(),
    }
    normalized["search_keywords"] = build_search_keywords(normalized)
    return normalized


def validate_rows(rows: list[dict[str, str]]) -> dict[str, Any]:
    codes = [row["item_code"] for row in rows]
    duplicate_codes = sorted({code for code in codes if codes.count(code) > 1})
    missing_required = [
        row.get("item_code", "<missing-code>")
        for row in rows
        if not all(row.get(field) for field in ("item_code", "item_name", "sku_name", "stock_uom", "estimated_rate"))
    ]
    if duplicate_codes or missing_required:
        raise ValueError(
            f"Invalid release: duplicate_codes={duplicate_codes}, missing_required={missing_required[:20]}"
        )
    return {
        "row_count": len(rows),
        "unique_item_codes": len(set(codes)),
        "merged_source_rows": sum(int(row.get("merged_count") or "1") for row in rows),
        "fixed_length_unit_overrides": sum(row["item_code"] == "PIPE-000411" for row in rows),
        "sandbox_code_conflict_overrides": len(SANDBOX_CODE_CONFLICTS),
    }


def build_release(input_path: Path, output_path: Path, summary_path: Path) -> dict[str, Any]:
    rows = [normalize_row(row) for row in read_tsv(input_path)]
    summary = validate_rows(rows)
    summary.update(
        {
            "release": "material_master_release_v1_0",
            "source": str(input_path.relative_to(REPO_ROOT)),
            "output": str(output_path.relative_to(REPO_ROOT)),
            "authoritative": True,
        }
    )
    write_tsv(output_path, rows)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the authoritative material master v1.0 release.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()
    summary = build_release(args.input, args.output, args.summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
