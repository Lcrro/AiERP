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
OUTPUT_DIR = REPO_ROOT / "data" / "material_master" / "governance_v0_2" / "manual_third_layer_mapping"
DEFAULT_MAPPING_OUTPUT = OUTPUT_DIR / "screw_bolt_third_layer_mapping_v0_1.tsv"
DEFAULT_JSON_OUTPUT = OUTPUT_DIR / "material_master_screw_bolt_third_layer_preview.json"

MAPPING_FIELDS = [
    "item_code",
    "current_item_name",
    "current_required_specs",
    "current_uom",
    "target_top_category",
    "target_second_layer_family",
    "target_third_layer_name",
    "decision",
    "confidence",
    "assumed_specs",
    "manual_judgment",
    "next_action",
]


def contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def has_field(row: dict[str, str], field_name: str) -> bool:
    text = "；".join([row.get("required_specs", ""), row.get("optional_specs", "")])
    return f"{field_name}：" in text or f"{field_name}:" in text


def is_screw_bolt_row(row: dict[str, str]) -> bool:
    return row.get("top_group") == "紧固件与连接件" and row.get("material_family") == "螺丝/螺栓"


def is_kit(row: dict[str, str], text: str) -> bool:
    return row.get("item_name") == "螺丝套件" or contains_any(text, ["成套：是", "套件组成", "螺丝套件", "螺丝组件"])


def classify_third_layer(row: dict[str, str]) -> tuple[str, str, str, str]:
    text = "；".join(
        [
            row.get("item_name", ""),
            row.get("required_specs", ""),
            row.get("optional_specs", ""),
            row.get("aliases", ""),
        ]
    )
    kit = is_kit(row, text)

    if "管片" in text:
        return "管片螺栓", "特种螺栓", "high", "出现管片用途，按盾构/管片连接件单独成三级名称。"
    if "鱼尾" in text:
        return "鱼尾螺栓", "特种螺栓", "high", "出现鱼尾类型，按轨道/桥梁等特种鱼尾螺栓处理。"
    if "骑马" in text or "U型" in text or "U 型" in text:
        return "U型螺栓", "特殊功能", "high", "骑马螺丝是 U 型螺栓/管卡俗称。"
    if "钻尾" in text or "燕尾" in text:
        return "钻尾螺丝", "自钻自攻", "high", "出现钻尾类型，尾部自带钻头。"
    if "自攻" in text:
        return "自攻螺丝", "自钻自攻", "high", "出现自攻类型。"
    if "十字" in text:
        return ("十字螺丝套件" if kit else "十字螺丝", "基础紧固", "high", "出现十字头型/驱动。")
    if "T型" in text or "T 型" in text:
        return ("T型螺丝套件" if kit else "T型螺丝", "特殊功能", "high", "出现 T 型类型。")
    if "圆头" in text:
        return ("圆头螺丝套件" if kit else "圆头螺丝", "基础紧固", "high", "出现圆头头型。")
    if "内六角" in text:
        return ("内六角螺丝套件" if kit else "内六角螺丝", "基础紧固", "high", "出现内六角头型/驱动。")
    if contains_any(text, ["六角自攻"]):
        return "自攻螺丝", "自钻自攻", "high", "六角自攻本质仍是自攻螺丝，六角作为头型属性。"
    if "六角" in text:
        return ("外六角螺栓套件" if kit else "外六角螺栓", "基础紧固", "high", "出现六角头型，按外六角螺栓处理。")
    if contains_any(text, ["全牙", "全芽", "全螺纹"]):
        name = "高强度全牙螺栓" if contains_any(text, ["强度等级", "高强度"]) else "全牙螺栓"
        return (name, "基础紧固", "medium", "出现全牙/全螺纹描述，按全牙螺栓处理。")
    if contains_any(text, ["强度等级", "高强度"]):
        return ("高强度螺丝套件" if kit else "高强度螺栓", "基础紧固", "medium", "出现强度等级或高强度描述，但缺头型时先按高强度螺栓。")
    if "不锈钢" in text:
        return ("不锈钢螺丝套件" if kit else "不锈钢螺丝", "基础紧固", "medium", "出现不锈钢材质，但头型缺失。")
    if kit:
        return "螺丝套件", "套件", "medium", "成套信息明确，但头型/组成可能仍需确认。"
    return "普通螺栓", "裸奔近似", "low", "仅有规格尺寸，缺头型/材质/强度；按土建常用普通螺栓近似。"


def default_specs_for(target_name: str) -> list[str]:
    if "内六角" in target_name:
        return ["材质：碳钢", "强度等级：12.9", "表面处理：发黑"]
    if "外六角" in target_name or target_name in {"普通螺栓", "鱼尾螺栓", "U型螺栓", "管片螺栓"}:
        return ["材质：碳钢", "强度等级：8.8", "表面处理：镀锌"]
    if "高强度" in target_name:
        return ["材质：合金钢", "表面处理：发黑"]
    if "自攻" in target_name or "钻尾" in target_name or "十字" in target_name or "圆头" in target_name:
        return ["材质：碳钢", "表面处理：镀锌"]
    if "不锈钢" in target_name:
        return ["材质：不锈钢"]
    if "套件" in target_name:
        return ["材质：碳钢", "强度等级：8.8", "表面处理：镀锌"]
    return []


def append_missing_specs(row: dict[str, str], target_name: str) -> tuple[str, str]:
    specs = split_terms(row.get("required_specs", ""))
    assumed: list[str] = []
    for spec in default_specs_for(target_name):
        field_name = spec.split("：", 1)[0]
        if not has_field(row, field_name) and spec not in specs:
            specs.append(spec)
            assumed.append(spec)
    return "；".join(specs), "；".join(assumed)


def mapping_row(row: dict[str, str]) -> dict[str, str]:
    target, category, confidence, reason = classify_third_layer(row)
    normalized_required_specs, assumed_specs = append_missing_specs(row, target)
    decision = "三级名称修正"
    if confidence == "low":
        decision = "裸奔数据近似"
    elif "套件" in target:
        decision = "套件归名"

    next_action = "后续采购前确认真实材质、强度等级、表面处理和执行标准。"
    if not assumed_specs:
        next_action = "保留现有规格，后续进入同名 SKU 去重和单位治理。"
    if "套件" in target:
        next_action = "采购前确认套件组成是否含螺母、平垫、弹垫及数量。"
    if target == "管片螺栓":
        next_action = "采购前补图纸号、执行标准、材质、强度和完整规格。"

    return {
        "item_code": row["item_code"],
        "current_item_name": row["item_name"],
        "current_required_specs": row["required_specs"],
        "current_uom": row["stock_uom"],
        "target_top_category": "紧固件与连接件",
        "target_second_layer_family": "螺丝/螺栓",
        "target_third_layer_name": target,
        "decision": decision,
        "confidence": confidence,
        "assumed_specs": assumed_specs,
        "manual_judgment": f"{category}：{reason}",
        "next_action": next_action,
    }


def write_mapping(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MAPPING_FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def apply_mapping(row: dict[str, str], mapping: dict[str, dict[str, str]]) -> dict[str, str]:
    mapped = mapping.get(row["item_code"])
    if not mapped:
        return row
    normalized_required_specs, assumed_specs = append_missing_specs(row, mapped["target_third_layer_name"])
    note = (
        f"螺丝/螺栓三级预览：{mapped['current_item_name']} -> {mapped['target_third_layer_name']}；"
        f"decision={mapped['decision']}；confidence={mapped['confidence']}；{mapped['manual_judgment']}"
    )
    if assumed_specs:
        note = f"{note}；推定补全：{assumed_specs}"

    return {
        **row,
        "item_name": mapped["target_third_layer_name"],
        "required_specs": normalized_required_specs,
        "aliases": field_append(row.get("aliases", ""), mapped["current_item_name"]),
        "search_keywords": " ".join(
            part
            for part in [
                row.get("search_keywords", ""),
                mapped["target_third_layer_name"],
                mapped["current_item_name"],
                mapped["assumed_specs"],
            ]
            if part
        ),
        "family_note": field_append(row.get("family_note", ""), note),
        "governance_note": field_append(row.get("governance_note", ""), note),
        "search_text": f"{row.get('search_text', '')} {mapped['target_third_layer_name']} {mapped['assumed_specs']}".lower(),
    }


def build_preview(input_json: Path, mapping_output: Path, json_output: Path, generated_at: str) -> dict[str, object]:
    source_payload = json.loads(input_json.read_text(encoding="utf-8"))
    source_rows = source_payload["rows"]
    mapping_rows = [mapping_row(row) for row in source_rows if is_screw_bolt_row(row)]
    write_mapping(mapping_output, mapping_rows)
    mapping = {row["item_code"]: row for row in mapping_rows}
    rows = [apply_mapping(dict(row), mapping) for row in source_rows]
    payload = {
        **source_payload,
        "generated_at": generated_at,
        "source": str(mapping_output),
        "third_layer_mapping_source": str(mapping_output),
        "third_layer_mapping_count": len(mapping_rows),
        "summary": build_summary(rows),
        "categories": build_categories(rows),
        "family_rule_impacts": build_family_rule_impacts(rows),
        "rows": rows,
    }
    write_json(json_output, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build screw/bolt third-layer material-name preview.")
    parser.add_argument("--input-json", type=Path, default=DEFAULT_INPUT_JSON)
    parser.add_argument("--mapping-output", type=Path, default=DEFAULT_MAPPING_OUTPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--generated-at", default=date.today().isoformat())
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_preview(args.input_json, args.mapping_output, args.output, args.generated_at)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "mapping_output": str(args.mapping_output),
                "sku_count": payload["summary"]["sku_count"],
                "material_family_count": payload["summary"]["material_family_count"],
                "third_layer_mapping_count": payload["third_layer_mapping_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
