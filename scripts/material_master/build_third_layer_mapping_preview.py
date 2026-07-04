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
    split_terms,
    write_json,
)


DEFAULT_INPUT_JSON = (
    REPO_ROOT
    / "data"
    / "material_master"
    / "governance_v0_2"
    / "manual_family_mapping"
    / "material_master_manual_family_preview.json"
)
DEFAULT_MAPPING_PATH = (
    REPO_ROOT
    / "data"
    / "material_master"
    / "governance_v0_2"
    / "manual_third_layer_mapping"
)
DEFAULT_OUTPUT_PATH = (
    REPO_ROOT
    / "data"
    / "material_master"
    / "governance_v0_2"
    / "manual_third_layer_mapping"
    / "material_master_third_layer_preview.json"
)


REQUIRED_FIELDS = [
    "item_code",
    "current_item_name",
    "target_top_category",
    "target_second_layer_family",
    "target_third_layer_name",
    "decision",
    "confidence",
    "manual_judgment",
    "next_action",
]


def mapping_files(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("*_third_layer_mapping_v0_1.tsv"))
    return [path]


def read_mapping(path: Path) -> dict[str, dict[str, str]]:
    mappings: dict[str, dict[str, str]] = {}
    for file_path in mapping_files(path):
        with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        for line_no, row in enumerate(rows, start=2):
            missing = [field for field in REQUIRED_FIELDS if not row.get(field, "").strip()]
            if missing:
                raise ValueError(f"{file_path}:{line_no} missing required fields: {', '.join(missing)}")
            item_code = row["item_code"].strip()
            if item_code in mappings:
                raise ValueError(f"duplicate third-layer mapping for item_code {item_code}")
            mappings[item_code] = {key: (value or "").strip() for key, value in row.items()}
    return mappings


def mapping_sources(path: Path) -> list[str]:
    return [str(file_path) for file_path in mapping_files(path)]


def append_assumed_specs(required_specs: str, assumed_specs: str) -> tuple[str, str]:
    specs = split_terms(required_specs)
    applied_specs: list[str] = []
    for spec in split_terms(assumed_specs):
        if spec and spec not in specs and not has_equivalent_spec_field(specs, spec):
            specs.append(spec)
            applied_specs.append(spec)
    return "；".join(specs), "；".join(applied_specs)


def has_equivalent_spec_field(specs: list[str], candidate: str) -> bool:
    if "：" not in candidate:
        return False
    field_name, _ = candidate.split("：", 1)
    equivalent_fields = {
        "材质": {"材质"},
        "连接方式": {"连接", "连接方式", "连接形式"},
        "表面处理": {"表面", "表面处理"},
        "外部形状": {"结构", "外部形状"},
        "驱动方式": {"驱动", "驱动方式"},
        "特征": {"特征"},
    }.get(field_name, {field_name})
    return any(any(spec.startswith(f"{field}：") or spec.startswith(f"{field}:") for field in equivalent_fields) for spec in specs)


def apply_mapping(row: dict[str, str], mapping: dict[str, dict[str, str]]) -> dict[str, str]:
    rule = mapping.get(row["item_code"])
    if not rule:
        return row

    target_top = rule["target_top_category"]
    target_family = rule["target_second_layer_family"]
    target_name = rule["target_third_layer_name"]
    assumed_specs = rule.get("assumed_specs", "")
    required_specs, applied_specs = append_assumed_specs(row.get("required_specs", ""), assumed_specs)
    note = (
        f"三级物料名称人工预览：{rule['current_item_name']} -> {target_name}；"
        f"{rule['target_top_category']}/{rule['target_second_layer_family']}；"
        f"decision={rule['decision']}；confidence={rule['confidence']}"
    )
    if rule.get("manual_judgment"):
        note = f"{note}；判断：{rule['manual_judgment']}"
    if applied_specs:
        note = f"{note}；推定补全：{applied_specs}"
    if rule.get("next_action"):
        note = f"{note}；下一步：{rule['next_action']}"

    moved_family = target_top != row.get("top_group") or target_family != row.get("material_family")
    family_rule = "manual_third_layer_family_move_v0.1" if moved_family else "manual_third_layer_name_v0.1"

    return {
        **row,
        "item_group": f"{target_top}/{target_family}",
        "top_group": target_top,
        "sub_group": target_family,
        "material_family": target_family,
        "item_name": target_name,
        "required_specs": required_specs,
        "aliases": field_append(row.get("aliases", ""), rule["current_item_name"]),
        "family_rule": field_append(row.get("family_rule", ""), family_rule),
        "family_note": field_append(row.get("family_note", ""), note),
        "governance_note": field_append(row.get("governance_note", ""), note),
        "search_keywords": " ".join(
            part
            for part in [
                row.get("search_keywords", ""),
                target_top,
                target_family,
                target_name,
                rule["current_item_name"],
                applied_specs,
            ]
            if part
        ),
        "search_text": (
            f"{row.get('search_text', '')} {target_top} {target_family} {target_name} {rule['current_item_name']} "
            f"{applied_specs} {rule['decision']} {rule['confidence']}"
        ).lower(),
    }


def build_preview(input_json: Path, mapping_path: Path, output_path: Path, generated_at: str) -> dict[str, object]:
    source_payload = json.loads(input_json.read_text(encoding="utf-8"))
    mapping = read_mapping(mapping_path)
    rows = [apply_mapping(dict(row), mapping) for row in source_payload["rows"]]
    payload = {
        **source_payload,
        "generated_at": generated_at,
        "source": str(output_path),
        "third_layer_mapping_source": str(mapping_path),
        "third_layer_mapping_sources": mapping_sources(mapping_path),
        "third_layer_mapping_count": len(mapping),
        "summary": build_summary(rows),
        "categories": build_categories(rows),
        "family_rule_impacts": build_family_rule_impacts(rows),
        "rows": rows,
    }
    write_json(output_path, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a browser JSON preview from manual third-layer material-name mappings.")
    parser.add_argument("--input-json", type=Path, default=DEFAULT_INPUT_JSON)
    parser.add_argument(
        "--mapping",
        type=Path,
        default=DEFAULT_MAPPING_PATH,
        help="A mapping TSV file or a directory containing *_third_layer_mapping_v0_1.tsv files.",
    )
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
                "third_layer_mapping_count": payload["third_layer_mapping_count"],
                "third_layer_mapping_sources": len(payload["third_layer_mapping_sources"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
