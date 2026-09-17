"""Publish cleaned fastener and rebar variants from an artifact-tool JSON extract.

The source workbook remains read-only.  This command consumes the compact JSON
extract produced during spreadsheet inspection, applies deterministic GPC
boundary rules, removes incomplete or duplicate historical rows, and merges the
result into the local material workbench publication files.  ERPNext is never
called by this script.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import re
import sys
import unicodedata
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.item_master.material_catalog_normalization import (  # noqa: E402
    canonical_material_name,
)
DEFAULT_MATERIALS_PATH = ROOT / ".runtime" / "material-master" / "gpc-material-placements.jsonl"
DEFAULT_PROFILES_PATH = ROOT / ".runtime" / "material-master" / "gpc-procurement-type-profiles.jsonl"
DEFAULT_REPORT_PATH = ROOT / ".runtime" / "material-master" / "historical-fastener-rebar-import-report.json"
PUBLICATION_PREFIX = "REF-HIST-"
PROFILE_PREFIX = "REF-TYPE-"
EXISTING_TYPE_MIGRATIONS = {
    ("10003185", "外六角螺栓"): "100031850101",
}


FASTENER_TYPES: dict[str, dict[str, str]] = {
    "bolt_hex": {
        "node_code": "100031850101",
        "standard_type": "六角螺栓",
        "profile_id": "REF-TYPE-BOLT-HEX",
        "main_template_id": "standard_component",
    },
    "bolt_stud": {
        "node_code": "100031850102",
        "standard_type": "双头螺栓",
        "profile_id": "REF-TYPE-BOLT-STUD",
        "main_template_id": "standard_component",
    },
    "bolt_unidentified_head": {
        "node_code": "100031850103",
        "standard_type": "头型待识别螺栓",
        "profile_id": "REF-TYPE-BOLT-UNIDENTIFIED-HEAD",
        "main_template_id": "standard_component",
    },
    "bolt_reamed_hole": {
        "node_code": "100031850104",
        "standard_type": "绞制孔螺栓",
        "profile_id": "REF-TYPE-BOLT-REAMED-HOLE",
        "main_template_id": "standard_component",
    },
    "bolt_embedded": {
        "node_code": "100031850105",
        "standard_type": "预埋螺栓",
        "profile_id": "REF-TYPE-BOLT-EMBEDDED",
        "main_template_id": "standard_component",
    },
    "bolt_directional_connection": {
        "node_code": "100031850106",
        "standard_type": "环向/纵向连接螺栓",
        "profile_id": "REF-TYPE-BOLT-DIRECTIONAL-CONNECTION",
        "main_template_id": "standard_component",
    },
    "bolt_drilled": {
        "node_code": "100031850107",
        "standard_type": "带孔螺栓",
        "profile_id": "REF-TYPE-BOLT-DRILLED",
        "main_template_id": "standard_component",
    },
    "threaded_rod": {
        "node_code": "100031850201",
        "standard_type": "全螺纹杆",
        "profile_id": "REF-TYPE-THREADED-ROD",
        "main_template_id": "linear_cut_material",
    },
    "screw_general": {
        "node_code": "100031810101",
        "standard_type": "通用螺钉",
        "profile_id": "REF-TYPE-SCREW-GENERAL",
        "main_template_id": "standard_component",
    },
    "screw_self_tapping": {
        "node_code": "100031810102",
        "standard_type": "自攻螺钉",
        "profile_id": "REF-TYPE-SCREW-SELF-TAPPING",
        "main_template_id": "standard_component",
    },
    "screw_machine": {
        "node_code": "100031810103",
        "standard_type": "机螺钉",
        "profile_id": "REF-TYPE-SCREW-MACHINE",
        "main_template_id": "standard_component",
    },
    "screw_socket": {
        "node_code": "100031810104",
        "standard_type": "内六角螺钉",
        "profile_id": "REF-TYPE-SCREW-SOCKET",
        "main_template_id": "standard_component",
    },
    "expansion_anchor": {
        "node_code": "100031790101",
        "standard_type": "膨胀锚栓",
        "profile_id": "REF-TYPE-ANCHOR-EXPANSION",
        "main_template_id": "standard_component",
    },
    "turnbuckle": {
        "node_code": "100031650101",
        "standard_type": "花篮螺丝",
        "profile_id": "REF-TYPE-TURNBUCKLE",
        "main_template_id": "standard_component",
    },
}


REBAR_TYPES: dict[str, dict[str, str]] = {
    "rebar_hot_rolled": {
        "node_code": "100081630101",
        "standard_type": "热轧带肋钢筋",
        "profile_id": "REF-TYPE-REBAR-HOT-ROLLED",
        "main_template_id": "linear_cut_material",
    },
    "rebar_seismic": {
        "node_code": "100081630102",
        "standard_type": "抗震热轧带肋钢筋",
        "profile_id": "REF-TYPE-REBAR-SEISMIC",
        "main_template_id": "linear_cut_material",
    },
    "rebar_prestress": {
        "node_code": "100081630103",
        "standard_type": "精轧螺纹钢",
        "profile_id": "REF-TYPE-REBAR-PRESTRESS",
        "main_template_id": "linear_cut_material",
    },
    "rebar_coil": {
        "node_code": "100081630104",
        "standard_type": "盘螺",
        "profile_id": "REF-TYPE-REBAR-COIL",
        "main_template_id": "linear_cut_material",
    },
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalized(value: Any) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", _text(value)).casefold())


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)


def _source_row(row: Mapping[str, Any]) -> int:
    return int(row.get("source_sheet_row") or row.get("source_row") or 0)


def _source_code(row: Mapping[str, Any]) -> str:
    value = row.get("编码") or row.get("code")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return _text(value)


def _clean_dimensions(value: str) -> str | None:
    text = unicodedata.normalize("NFKC", value)
    text = text.replace("×", "x").replace("*", "x").replace("X", "x")
    match = re.search(
        r"(?:[MmΦφФф]\s*)?(\d+(?:\.\d+)?)\s*(?:mm)?\s*x\s*"
        r"(\d+(?:\.\d+)?)\s*(?:mm|m)?"
        r"(?:\s*x\s*(\d+(?:\.\d+)?)\s*(?:mm)?)?",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    dimensions = [match.group(1), match.group(2)]
    if match.group(3):
        dimensions.append(match.group(3))
    if len(dimensions) == 2 and re.search(r"[ΦφФф]\s*\d+\s*x\s*1\s*m\b", text, re.IGNORECASE):
        dimensions[1] = "1000"
    prefix = "M" if len(dimensions) == 2 else ""
    return f"{prefix}{'×'.join(dimensions)} mm"


def _classify_fastener(name: str, spec: str) -> str | None:
    text = f"{name} {spec}"
    if "膨胀" in text:
        return "expansion_anchor"
    if "花篮" in text:
        return "turnbuckle"
    if "全牙" in text or "螺丝杆" in text or "螺纹杆" in text:
        return "threaded_rod"
    if "自攻" in text:
        return "screw_self_tapping"
    if "元机" in text or "机螺" in text:
        return "screw_machine"
    if "内六角螺丝" in text or "内螺丝" in text:
        return "screw_socket"
    if any(term in text for term in ("双头", "弧形双头")):
        return "bolt_stud"
    if "六角" in text and "螺" in text:
        return "bolt_hex"
    if "绞制孔" in text:
        return "bolt_reamed_hole"
    if "预埋" in text:
        return "bolt_embedded"
    if "环向" in text or "纵向" in text:
        return "bolt_directional_connection"
    if "带孔螺栓" in text:
        return "bolt_drilled"
    if "螺栓" in text:
        return "bolt_unidentified_head"
    if "高强" in text:
        return "bolt_unidentified_head"
    if "螺丝" in text:
        return "screw_general"
    return None


def _surface_finish(source_text: str, type_key: str) -> str:
    if "达克罗" in source_text:
        return "达克罗涂层"
    if "不锈钢" in source_text:
        return "不锈钢"
    if "镀锌" in source_text:
        return "镀锌"
    if "复合涂层" in source_text:
        return "复合涂层"
    if "本色" in source_text:
        return "碳钢本色"
    if type_key == "expansion_anchor":
        return "镀锌碳钢（常用默认）"
    return "碳钢常规防锈（常用默认）"


def _performance_grade(name: str, spec: str, type_key: str, surface: str) -> str:
    text = f"{name} {spec}"
    match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*级", text)
    if not match:
        match = re.search(r"(?<!\d)(8\.8|10\.9|12\.9|5\.8)(?!\d)", text)
    if match:
        return f"{match.group(1)}级"
    if "不锈钢" in surface:
        return "A2-70（常用默认）"
    if "达克罗" in surface and type_key == "bolt_stud":
        return "5.8级（同系列常用默认）"
    if type_key == "bolt_unidentified_head" and "高强" in text:
        return "8.8级（常用默认）"
    if type_key.startswith("screw_"):
        return "普通工业级（常用默认）"
    return "4.8级（常用默认）"


def _supply_scope(name: str, unit: str) -> str:
    if "两帽两平" in name:
        return "螺栓+2螺母+2平垫"
    if any(term in name for term in ("螺帽", "螺母", "母垫")):
        return "按原表成套供货"
    if unit in {"套", "千套"}:
        return "成套供货"
    return "单件"


def normalize_fastener(row: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str]:
    name = _text(row.get("名称"))
    spec = _text(row.get("规格型号"))
    type_key = _classify_fastener(name, spec)
    if type_key is None:
        return None, "无法归入有效紧固件类型"
    normalized_spec = _clean_dimensions(spec or name)
    if not normalized_spec:
        return None, "规格为空或缺少可识别直径和长度"
    type_meta = FASTENER_TYPES[type_key]
    unit = _text(row.get("单位"))
    surface = _surface_finish(f"{name} {spec}", type_key)
    grade = _performance_grade(name, spec, type_key, surface)
    supply_scope = _supply_scope(name, unit)
    material_id = f"{PUBLICATION_PREFIX}{_source_code(row)}"
    material = {
        "material_id": material_id,
        "procurement_profile_id": type_meta["profile_id"],
        "project": "公司历史参考物料",
        "source_reference": f"土木行业参考物料表｜编码 {_source_code(row)}",
        "source_rows": [_source_row(row)],
        "standard_type": type_meta["standard_type"],
        "material_name": f"{type_meta['standard_type']}｜{normalized_spec}｜{surface}｜{grade}",
        "gpc_brick_code": type_meta["node_code"],
        "classification_source": "nexterp_internal",
        "confidence": "历史规格明确+规则标准化" if "默认" not in f"{surface}{grade}" else "历史规格明确+常用默认补齐",
        "review_status": "已完整录入",
        "completeness_status": "完整",
        "specification_basis": f"历史原名：{name}；原规格：{spec}；默认项已在字段值中明示",
        "stock_uom": "套" if supply_scope != "单件" else "个",
        "purchase_package": unit or "个",
        "procurement_attributes": {
            "规格": normalized_spec,
            "供货范围": supply_scope,
        },
        "price_drivers": {
            "材质/表面处理": surface,
            "性能/质量等级": grade,
        },
        "gpc_notes": [
            "按 GPC 边界归入对应紧固件 Brick 下的 Nexterp 内部标准类型",
            "只录入历史表中真实存在的规格组合，不生成属性笛卡尔积",
        ],
        "questions": [],
    }
    material["material_name"] = canonical_material_name(material)
    key = "|".join(
        _normalized(value)
        for value in (type_meta["node_code"], normalized_spec, supply_scope, surface, grade)
    )
    return {"key": key, "material": material, "type_key": type_key}, ""


def _rebar_grade(name: str, spec: str) -> tuple[str, bool]:
    text = unicodedata.normalize("NFKC", f"{name} {spec}").upper()
    match = re.search(r"\b(HRB(?:335|400E?|500E)|CRB550|PSB\d+)\b", text)
    if match:
        return match.group(1), False
    if "精轧螺纹钢" in name:
        return "PSB830", True
    if name in {"热轧带肋钢筋", "螺纹钢", "螺纹管"}:
        return "HRB400", True
    return "", False


def _rebar_diameter(spec: str) -> str:
    text = unicodedata.normalize("NFKC", spec)
    match = re.search(r"[ΦφФф]\s*(\d+(?:\.\d+)?)", text)
    if not match:
        match = re.search(r"\b(?:HRB(?:335|400E?|500E))\s*(\d+(?:\.\d+)?)\b", text, re.IGNORECASE)
    return f"{match.group(1)} mm" if match else ""


def normalize_rebar(row: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str]:
    if _text(row.get("资源分类")) != "螺纹钢":
        return None, "非螺纹钢资源分类"
    name = _text(row.get("名称"))
    spec = _text(row.get("规格型号"))
    grade, defaulted = _rebar_grade(name, spec)
    diameter = _rebar_diameter(spec)
    if not grade or not diameter:
        return None, "牌号或公称直径不完整"
    if name == "盘螺":
        type_key = "rebar_coil"
        delivery_form = "盘卷"
    elif name == "精轧螺纹钢":
        type_key = "rebar_prestress"
        delivery_form = "直条"
    elif grade.endswith("E"):
        type_key = "rebar_seismic"
        delivery_form = "直条"
    elif grade.startswith("HRB"):
        type_key = "rebar_hot_rolled"
        delivery_form = "直条"
    else:
        return None, "不属于本次启用的螺纹钢标准类型"
    type_meta = REBAR_TYPES[type_key]
    material_id = f"{PUBLICATION_PREFIX}{_source_code(row)}"
    material = {
        "material_id": material_id,
        "procurement_profile_id": type_meta["profile_id"],
        "project": "公司历史参考物料",
        "source_reference": f"土木行业参考物料表｜编码 {_source_code(row)}",
        "source_rows": [_source_row(row)],
        "standard_type": type_meta["standard_type"],
        "material_name": f"{type_meta['standard_type']}｜{grade}｜Φ{diameter.removesuffix(' mm')}｜{delivery_form}",
        "gpc_brick_code": type_meta["node_code"],
        "classification_source": "nexterp_internal",
        "confidence": "历史规格明确+常用默认补齐" if defaulted else "历史规格明确+规则标准化",
        "review_status": "已完整录入",
        "completeness_status": "完整",
        "specification_basis": f"历史原名：{name}；原规格：{spec}；{'牌号采用常用默认并已明示' if defaulted else '牌号和直径来自原表'}",
        "stock_uom": "吨",
        "purchase_package": _text(row.get("单位")) or "吨",
        "procurement_attributes": {
            "牌号": grade,
            "公称直径": diameter,
            "交货形态": delivery_form,
        },
        "price_drivers": {
            "质量要求": "符合相应现行国家标准并提供材质证明",
        },
        "gpc_notes": [
            "归入钢（成型）Brick 下的 Nexterp 钢筋标准类型",
            "以牌号、公称直径和交货形态区分实际 SKU，不生成未出现组合",
        ],
        "questions": [],
    }
    key = "|".join(
        _normalized(value)
        for value in (type_meta["node_code"], grade, diameter, delivery_form)
    )
    return {"key": key, "material": material, "type_key": type_key}, ""


def _merge_duplicate(existing: dict[str, Any], incoming: Mapping[str, Any]) -> None:
    existing["source_rows"] = sorted(set(existing.get("source_rows") or []) | set(incoming.get("source_rows") or []))
    existing["source_reference"] = f"{existing['source_reference']}；{incoming['source_reference'].split('｜')[-1]}"


def build_publication(rows: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    deduplicated: dict[str, dict[str, Any]] = {}
    material_type_keys: dict[str, str] = {}
    excluded: list[dict[str, Any]] = []
    input_counts: Counter[str] = Counter()
    duplicate_count = 0
    for row in rows:
        target = _text(row.get("target"))
        input_counts[target or "unknown"] += 1
        if target == "bolt":
            normalized, reason = normalize_fastener(row)
        elif target == "rebar":
            normalized, reason = normalize_rebar(row)
        else:
            normalized, reason = None, "非本次目标"
        if normalized is None:
            excluded.append({
                "source_sheet_row": _source_row(row),
                "code": _source_code(row),
                "name": _text(row.get("名称")),
                "spec": _text(row.get("规格型号")),
                "reason": reason,
            })
            continue
        key = normalized["key"]
        material = normalized["material"]
        if key in deduplicated:
            _merge_duplicate(deduplicated[key], material)
            duplicate_count += 1
            continue
        deduplicated[key] = material
        material_type_keys[material["material_id"]] = normalized["type_key"]

    materials = sorted(deduplicated.values(), key=lambda item: item["material_id"])
    used_type_keys = sorted({material_type_keys[item["material_id"]] for item in materials})
    all_types = {**FASTENER_TYPES, **REBAR_TYPES}
    profiles: list[dict[str, Any]] = []
    for type_key in used_type_keys:
        meta = all_types[type_key]
        source_ids = [
            material["material_id"]
            for material in materials
            if material["gpc_brick_code"] == meta["node_code"]
        ]
        if type_key.startswith("rebar_"):
            sku_fields = [
                "procurement_attributes.牌号",
                "procurement_attributes.公称直径",
                "procurement_attributes.交货形态",
            ]
            offer_fields = ["price_drivers.质量要求"]
        else:
            sku_fields = [
                "procurement_attributes.规格",
                "procurement_attributes.供货范围",
                "price_drivers.材质/表面处理",
                "price_drivers.性能/质量等级",
            ]
            offer_fields = []
        profiles.append({
            "profile_id": meta["profile_id"],
            "standard_type": meta["standard_type"],
            "gpc_brick_code": meta["node_code"],
            "main_template_id": meta["main_template_id"],
            "constraint_ids": [],
            "sku_identity_fields": sku_fields,
            "transaction_fields": [],
            "offer_fields": offer_fields,
            "status": "confirmed",
            "source_material_ids": source_ids,
        })
    report = {
        "source": "土木行业参考物料表（artifact-tool JSON extract）",
        "input_counts": dict(input_counts),
        "published_material_count": len(materials),
        "published_type_profile_count": len(profiles),
        "duplicate_rows_merged": duplicate_count,
        "published_counts_by_standard_type": dict(Counter(item["standard_type"] for item in materials)),
        "excluded_count": len(excluded),
        "excluded_counts_by_reason": dict(Counter(item["reason"] for item in excluded)),
        "excluded_rows": excluded,
        "erpnext_written": False,
    }
    return materials, profiles, report


def merge_publication(
    generated_materials: Iterable[Mapping[str, Any]],
    generated_profiles: Iterable[Mapping[str, Any]],
    *,
    materials_path: Path,
    profiles_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    existing_materials = [
        row for row in _load_jsonl(materials_path)
        if not _text(row.get("material_id")).startswith(PUBLICATION_PREFIX)
    ]
    existing_profiles = [
        row for row in _load_jsonl(profiles_path)
        if not _text(row.get("profile_id")).startswith(PROFILE_PREFIX)
    ]
    for material in existing_materials:
        migration_key = (_text(material.get("gpc_brick_code")), _text(material.get("standard_type")))
        target_code = EXISTING_TYPE_MIGRATIONS.get(migration_key)
        if not target_code:
            continue
        material["gpc_brick_code"] = target_code
        material["classification_source"] = "nexterp_internal"
        material["internal_category_code"] = target_code
        notes = [
            note for note in (material.get("gpc_notes") or [])
            if "GPC Brick 10003185" not in _text(note)
        ]
        material["gpc_notes"] = [
            "归入螺栓/螺纹杆 Brick 下的 Nexterp 六角螺栓标准类型",
            *notes,
        ][:3]
    for profile in existing_profiles:
        migration_key = (_text(profile.get("gpc_brick_code")), _text(profile.get("standard_type")))
        target_code = EXISTING_TYPE_MIGRATIONS.get(migration_key)
        if target_code:
            profile["gpc_brick_code"] = target_code
    merged_materials = sorted(
        [*existing_materials, *(deepcopy(dict(row)) for row in generated_materials)],
        key=lambda row: _text(row.get("material_id")),
    )
    merged_profiles = sorted(
        [*existing_profiles, *(deepcopy(dict(row)) for row in generated_profiles)],
        key=lambda row: _text(row.get("profile_id")),
    )
    _write_jsonl(materials_path, merged_materials)
    _write_jsonl(profiles_path, merged_profiles)
    return merged_materials, merged_profiles


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Artifact-tool JSON extract")
    parser.add_argument("--materials", type=Path, default=DEFAULT_MATERIALS_PATH)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--dry-run", action="store_true", help="Validate and report without writing publication files")
    args = parser.parse_args()

    rows = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("输入 JSON 必须是行对象数组")
    materials, profiles, report = build_publication(rows)
    if not args.dry_run:
        merged_materials, merged_profiles = merge_publication(
            materials,
            profiles,
            materials_path=args.materials,
            profiles_path=args.profiles,
        )
        report["workbench_material_count"] = len(merged_materials)
        report["workbench_type_profile_count"] = len(merged_profiles)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
