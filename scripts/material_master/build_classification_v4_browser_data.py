"""Build a browser-friendly snapshot from the ChatGPT V4 classification workbook."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "erpnext"))
from import_classification_v4_workbook import WorkbookData, _text, load_workbook_data  # noqa: E402


DEFAULT_INPUT = Path.home() / "Downloads" / "龙华项目公司标准物料示范清单_第四轮附件治理.xlsx"
DEFAULT_OUTPUT = ROOT / "data" / "material_master" / "chatgpt_classification_v4" / "material_master_chatgpt_browser_data.json"


def _attributes(variant: dict[str, object]) -> dict[str, str]:
    fields = (
        ("规格", "主规格/型号"),
        ("材质", "材质"),
        ("强度/等级", "强度/等级"),
        ("表面处理/颜色", "表面处理/颜色"),
        ("型式/功能", "型式/功能"),
        ("包装规格", "包装规格"),
        ("品牌", "品牌"),
    )
    return {label: _text(variant.get(source)) for label, source in fields if _text(variant.get(source))}


def _required_specs(attributes: dict[str, str]) -> str:
    return "；".join(f"{key}:{value}" for key, value in attributes.items())


def browser_rows(data: WorkbookData) -> list[dict[str, object]]:
    families = {_text(row["物料族编码"]): row for row in data.families}
    rows: list[dict[str, object]] = []
    for variant in data.variants:
        family = families[_text(variant["物料族编码"])]
        attributes = _attributes(variant)
        family_code = _text(family["物料族编码"])
        item_code = _text(variant["规格变体编码"])
        top_group = _text(variant["一级分类"])
        sub_group = _text(variant["二级分类"])
        name = _text(variant["标准物料名称"])
        aliases = _text(variant.get("示例原始描述"))
        search_terms = [item_code, name, _text(variant["物料族"]), top_group, sub_group, aliases, *attributes.values()]
        rows.append({
            "item_code": item_code,
            "item_name": name,
            "sku_name": name,
            "required_specs": _required_specs(attributes),
            "optional_specs": "",
            "item_group": f"{top_group}/{sub_group}",
            "top_group": top_group,
            "sub_group": sub_group,
            "material_family": _text(variant["物料族"]),
            "stock_uom": _text(variant["基本单位"]),
            "purchase_uom": _text(variant["基本单位"]),
            "conversion_factor": "1",
            "aliases": aliases,
            "search_keywords": " ".join(term for term in search_terms if term),
            "brand": _text(variant.get("品牌")),
            "model": _text(variant.get("主规格/型号")),
            "status": "active",
            "quality_level": "standard",
            "agent_use_policy": "confirm_before_use",
            "source_refs": f"{variant['source_workbook']}|{variant['source_sheet']}|row={variant['source_row']}|hash={variant['source_row_hash']}",
            "source_item_codes": item_code,
            "merged_count": "1",
            "governance_note": "ChatGPT 分类 V4；分类和规格来自用户提供的第四轮附件治理工作簿。",
            "updated_at": date.today().isoformat(),
            "classification_key": f"{top_group}|{sub_group}|{family_code}",
            "standard_name": name,
            "required_attribute_keys": "、".join(attributes),
            "missing_required_specs": "",
            "classification_status": "ready",
            "source_item_name": _text(variant["示例原始描述"]),
            "source_sku_name": _text(variant["示例原始描述"]),
            "source_required_specs": _required_specs(attributes),
            "source_item_group": f"{top_group}/{sub_group}",
            "source_material_family": _text(variant["物料族"]),
            "rule_version": "chatgpt-classification-v4",
            "family_rule": "",
            "family_note": "",
            "family_type": "",
            "family_material": "",
            "family_use": "",
            "family_connection": "",
            "family_surface": "",
            "family_attributes": _text(family.get("规格属性模板")),
            "family_split_candidates": "",
            "family_attribute_terms": "",
            "estimated_rate": "",
            "currency": "CNY",
            "price_basis": "待 ERPNext 采购条件维护",
            "default_fill_basis": "",
            "search_text": " ".join(term for term in search_terms if term).lower(),
            "is_likely_hand_glove": "no",
            "source_dataset": "龙华项目公司标准物料示范清单_V4",
            "source_workbook": _text(variant["source_workbook"]),
            "source_sheet": _text(variant["source_sheet"]),
            "source_row": int(variant["source_row"]),
            "source_row_hash": _text(variant["source_row_hash"]),
            # These fields let a future marketplace adapter render attributes
            # without guessing from the display name.
            "family_code": family_code,
            "segment_code": f"CHATGPT-L1-{top_group}",
            "segment_name": top_group,
            "category_code": f"CHATGPT-L2-{top_group}|{sub_group}",
            "standard_type": _text(variant["物料族"]),
            "material_name": name,
            "procurement_attributes": attributes,
            "price_drivers": attributes,
            "classification_path": [{"code": f"CHATGPT-L1-{top_group}", "name": top_group}, {"code": f"CHATGPT-L2-{top_group}|{sub_group}", "name": sub_group}, {"code": family_code, "name": _text(variant["物料族"])}],
        })
    return rows


def build_payload(data: WorkbookData) -> dict[str, object]:
    rows = browser_rows(data)
    family_count = len({_text(row["物料族编码"]) for row in data.families})
    top_count = len({_text(row["一级分类"]) for row in data.families})
    item_groups = len({f"{_text(row['一级分类'])}/{_text(row['二级分类'])}" for row in data.families})
    quality = Counter(str(row["quality_level"]) for row in rows)
    return {
        "generated_at": date.today().isoformat(),
        "source": data.source_path,
        "source_workbook": data.source_workbook,
        "source_hash": data.source_hash,
        "release_hash": data.release_hash,
        "classification_source": "chatgpt_v4",
        "classification_label": "ChatGPT 分类（龙华 V4）",
        "summary": {
            "sku_count": len(rows),
            "item_name_count": len({_text(row["物料族编码"]) for row in data.variants}),
            "material_family_count": family_count,
            "top_group_count": top_count,
            "item_group_count": item_groups,
            "type_count": family_count,
            "status_counts": {"active": len(rows)},
            "quality_counts": dict(quality),
            "agent_use_policy_counts": {"confirm_before_use": len(rows)},
            "classification_status_counts": {"ready": len(rows)},
            "issue_counts": {},
        },
        "categories": [],
        "family_rule_impacts": [],
        "family_rules_count": 0,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build_payload(load_workbook_data(args.input))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "summary": payload["summary"], "release_hash": payload["release_hash"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
