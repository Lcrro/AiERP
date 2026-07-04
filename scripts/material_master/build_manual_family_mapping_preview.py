from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "material_master"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from build_material_master_browser_data import (  # noqa: E402
    build_categories,
    build_family_rule_impacts,
    build_summary,
    field_append,
    write_json,
)


DEFAULT_INPUT_JSON = (
    REPO_ROOT
    / "data"
    / "material_master"
    / "governance_v0_2"
    / "screw"
    / "material_master_screw_governed_preview.json"
)
DEFAULT_MAPPING_PATH = (
    REPO_ROOT
    / "data"
    / "material_master"
    / "governance_v0_2"
    / "manual_family_mapping"
)
DEFAULT_OUTPUT_PATH = (
    REPO_ROOT
    / "data"
    / "material_master"
    / "governance_v0_2"
    / "manual_family_mapping"
    / "material_master_manual_family_preview.json"
)


def mapping_files(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("*_family_mapping_batch_*.tsv"))
    return [path]


def read_mapping(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    mappings: dict[tuple[str, str], dict[str, str]] = {}
    for file_path in mapping_files(path):
        with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        for row in rows:
            mappings[(row["current_top_category"], row["current_material_family"])] = row
    return mappings


def mapping_sources(path: Path) -> list[str]:
    return [str(file_path) for file_path in mapping_files(path)]


def read_single_mapping(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    return {(row["current_top_category"], row["current_material_family"]): row for row in rows}


def apply_mapping(row: dict[str, str], mapping: dict[tuple[str, str], dict[str, str]]) -> dict[str, str]:
    rule = mapping.get((row["top_group"], row["material_family"]))
    if not rule:
        return row

    target_top = rule["target_top_category"].strip()
    target_family = rule["target_second_layer_family"].strip()
    decision = rule["decision"].strip()
    confidence = rule["confidence"].strip()
    note = rule["manual_judgment"].strip()
    next_action = rule["next_action"].strip()

    preview_note = f"二级物料族人工预览：{decision} -> {target_top}/{target_family}；置信度：{confidence}"
    if note:
        preview_note = f"{preview_note}；判断：{note}"
    if next_action:
        preview_note = f"{preview_note}；下一步：{next_action}"

    next_row = {
        **row,
        "item_group": f"{target_top}/{target_family}",
        "top_group": target_top,
        "sub_group": target_family,
        "material_family": target_family,
        "family_rule": field_append(row.get("family_rule", ""), "manual_second_layer_family_v0.1"),
        "family_note": field_append(row.get("family_note", ""), preview_note),
        "governance_note": field_append(row.get("governance_note", ""), preview_note),
        "search_text": (
            f"{row.get('search_text', '')} {target_top} {target_family} {decision} "
            f"{rule.get('current_material_family', '')}"
        ).lower(),
    }
    return next_row


def build_preview(input_json: Path, mapping_path: Path, output_path: Path, generated_at: str) -> dict[str, object]:
    source_payload = json.loads(input_json.read_text(encoding="utf-8"))
    mapping = read_mapping(mapping_path)
    rows = [apply_mapping(dict(row), mapping) for row in source_payload["rows"]]
    payload = {
        **source_payload,
        "generated_at": generated_at,
        "source": str(mapping_path),
        "manual_mapping_source": str(mapping_path),
        "manual_mapping_sources": mapping_sources(mapping_path),
        "manual_mapping_count": len(mapping),
        "summary": build_summary(rows),
        "categories": build_categories(rows),
        "family_rule_impacts": build_family_rule_impacts(rows),
        "rows": rows,
    }
    write_json(output_path, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a browser JSON preview from manual second-layer family mappings.")
    parser.add_argument("--input-json", type=Path, default=DEFAULT_INPUT_JSON)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING_PATH, help="A mapping TSV file or a directory containing *_family_mapping_batch_*.tsv files.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--generated-at", default=date.today().isoformat())
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_preview(args.input_json, args.mapping, args.output, args.generated_at)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "sku_count": payload["summary"]["sku_count"],
                "top_group_count": payload["summary"]["top_group_count"],
                "material_family_count": payload["summary"]["material_family_count"],
                "manual_mapping_count": payload["manual_mapping_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
