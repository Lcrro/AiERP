"""Rebuild the material master from the published v1.0 SKU catalog.

This is deliberately a deterministic, standard-library-only rebuild.  It does
not call ERPNext and it never invents a factual value that is absent from the
source catalog.  Values that are needed for a complete SKU are surfaced as
``missing_required_specs`` and routed to ``clarify_specs_before_use``.

The input and output paths are intentionally explicit so that a new release
can be regenerated without mutating the previous release.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data/material_master/release_v1_0/material_master_release_v1_0.tsv"
DEFAULT_OUTPUT = ROOT / "data/material_master/release_v1_1"
RELEASE_NAME = "material_master_release_v1_1"
RULE_VERSION = "material-entry-rules-v1.1"

SOURCE_COLUMNS = [
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

RELEASE_COLUMNS = SOURCE_COLUMNS + [
    "classification_key",
    "standard_name",
    "required_attribute_keys",
    "missing_required_specs",
    "classification_status",
    "source_item_name",
    "source_sku_name",
    "source_required_specs",
    "source_item_group",
    "source_material_family",
    "rule_version",
]

TOP_GROUPS = {
    "管材管件阀门",
    "紧固件与连接件",
    "电气电料",
    "工具量具",
    "液压气动",
    "定制加工件",
    "清洁办公后勤",
    "化工胶粘涂料",
    "工具耗材",
    "吊装索具",
    "劳保防护",
    "设备备件",
    "建筑材料",
    "金属材料",
    "包装覆盖周转",
    "焊接切割",
    "安全消防",
    "施工机具设备",
    "电动气动工具",
    "弱电安防",
}

# Values in these families should never be silently selected by an agent,
# even when the source row happens to have a complete set of attributes.
HIGH_RISK_GROUPS = {
    "安全消防",
    "吊装索具",
    "劳保防护",
    "化工胶粘涂料",
    "焊接切割",
    "液压气动",
}

KEY_ALIASES = {
    "规格/口径": "specification",
    "规格型号": "specification",
    "规格": "specification",
    "口径": "nominal_diameter",
    "公称直径": "nominal_diameter",
    "外径": "outer_diameter",
    "内径": "inner_diameter",
    "尺寸": "size",
    "长度": "length",
    "宽度": "width",
    "高度": "height",
    "厚度": "thickness",
    "直径": "diameter",
    "容量": "capacity",
    "重量": "weight",
    "材质": "material",
    "材料": "material",
    "品牌": "brand",
    "型号": "model",
    "强度等级": "strength_grade",
    "强度": "strength_grade",
    "表面处理": "surface_treatment",
    "螺纹形式": "thread_form",
    "连接方式": "connection_type",
    "连接形式": "connection_type",
    "套件组成": "kit_contents",
    "包装规格": "package_specification",
    "包装": "package_specification",
    "颜色": "color",
    "额定电压": "rated_voltage",
    "电压": "rated_voltage",
    "额定电流": "rated_current",
    "电流": "rated_current",
    "功率": "power",
    "额定功率": "rated_power",
    "压力": "pressure",
    "工作压力": "working_pressure",
    "流量": "flow_rate",
    "精度": "accuracy",
    "适用范围": "application",
    "用途": "application",
    "工艺": "process",
    "层数": "layer_count",
    "数量": "quantity",
    "等级": "grade",
    "防护等级": "protection_rating",
}

KEY_DISPLAY_NAMES = {
    "specification": "规格",
    "nominal_diameter": "公称直径",
    "outer_diameter": "外径",
    "inner_diameter": "内径",
    "size": "尺寸",
    "length": "长度",
    "width": "宽度",
    "height": "高度",
    "thickness": "厚度",
    "diameter": "直径",
    "capacity": "容量",
    "weight": "重量",
    "material": "材质",
    "brand": "品牌",
    "model": "型号",
    "strength_grade": "强度等级",
    "surface_treatment": "表面处理",
    "thread_form": "螺纹形式",
    "connection_type": "连接方式",
    "kit_contents": "套件组成",
    "package_specification": "包装规格",
    "color": "颜色",
    "rated_voltage": "额定电压",
    "rated_current": "额定电流",
    "power": "功率",
    "rated_power": "额定功率",
    "pressure": "压力",
    "working_pressure": "工作压力",
    "flow_rate": "流量",
    "accuracy": "精度",
    "application": "适用范围",
    "process": "工艺",
    "layer_count": "层数",
    "quantity": "数量",
    "grade": "等级",
    "protection_rating": "防护等级",
}

# These fields describe a thing but do not, on their own, identify a SKU.
NON_IDENTITY_KEYS = {"application", "kit_contents", "quantity", "grade"}
KEY_ORDER = [
    "specification",
    "size",
    "nominal_diameter",
    "outer_diameter",
    "inner_diameter",
    "length",
    "width",
    "height",
    "thickness",
    "diameter",
    "material",
    "strength_grade",
    "surface_treatment",
    "thread_form",
    "connection_type",
    "capacity",
    "weight",
    "rated_voltage",
    "rated_current",
    "power",
    "rated_power",
    "pressure",
    "working_pressure",
    "flow_rate",
    "accuracy",
    "protection_rating",
    "package_specification",
    "color",
    "brand",
    "model",
    "process",
    "layer_count",
    "application",
    "kit_contents",
    "quantity",
    "grade",
]

STRENGTH_RE = re.compile(r"(?<![A-Za-z0-9])(?P<grade>\d+(?:\.\d+)?)\s*级")
DIMENSION_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:M\s*\d+(?:\s*[×xX*]\s*\d+)?|DN\s*\d+|\d+(?:\.\d+)?\s*(?:mm|厘米|cm|ml|mL|L|kg|千克|V|A|W|kW))"
)
PAREN_PACKAGE_RE = re.compile(r"[（(][^（）()]{0,20}(?:装|瓶|盒|包|卷|桶|袋|支|只)[）)]")
WHITESPACE_RE = re.compile(r"\s+")


def _clean(value: object) -> str:
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = value.replace("；", ";").replace("：", ":").replace("×", "×")
    return WHITESPACE_RE.sub(" ", value).strip()


def _strip_family(value: str) -> tuple[str, bool]:
    value = _clean(value)
    candidate = "候选" in value
    value = re.sub(r"\s*[（(]候选(?:新增)?[）)]", "", value)
    value = re.sub(r"\s*候选新增?\s*$", "", value)
    return value.strip() or "待治理", candidate


def _clean_standard_name(source_name: str, brand: str = "") -> tuple[str, list[str]]:
    """Remove only explicit SKU-level tokens; retain the source as an alias."""
    raw = _clean(source_name)
    notes: list[str] = []
    value = raw
    value = PAREN_PACKAGE_RE.sub("", value)
    value = re.sub(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?\s*级(?:高强度)?", "", value)
    value = re.sub(r"(?<![A-Za-z0-9])(?:M\s*\d+(?:\s*[×xX*]\s*\d+)?|DN\s*\d+|\d+(?:\.\d+)?\s*(?:mm|厘米|cm|ml|mL|L|kg|千克|V|A|W|kW))", "", value)
    if brand:
        brand_clean = _clean(brand)
        if brand_clean and brand_clean in value and len(brand_clean) > 1:
            value = value.replace(brand_clean, "")
            notes.append("brand_removed_from_standard_name")
    value = re.sub(r"^[\-_/|·、,，\s]+|[\-_/|·、,，\s]+$", "", value)
    value = WHITESPACE_RE.sub(" ", value).strip()
    if value != raw:
        notes.append("sku_level_token_removed_from_standard_name")
    return value or raw or "未命名物料", notes


def _canonical_key(key: str) -> str:
    key = _clean(key).strip(" -_/")
    return KEY_ALIASES.get(key, key.lower().replace(" ", "_"))


def _parse_specs(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in re.split(r"[;|]\s*", _clean(value)):
        part = part.strip(" ;")
        if not part:
            continue
        if ":" in part:
            raw_key, raw_value = part.split(":", 1)
        elif "=" in part:
            raw_key, raw_value = part.split("=", 1)
        else:
            # Keep unstructured evidence instead of losing it.
            raw_key, raw_value = "specification", part
        key = _canonical_key(raw_key)
        raw_value = _clean(raw_value)
        if not raw_value:
            continue
        if key in result and result[key] != raw_value:
            values = [v.strip() for v in result[key].split(" / ") if v.strip()]
            if raw_value not in values:
                values.append(raw_value)
            result[key] = " / ".join(values)
        else:
            result[key] = raw_value
    return result


def _add_attr(attrs: dict[str, str], key: str, value: str) -> None:
    value = _clean(value)
    if value and key not in attrs:
        attrs[key] = value


def _attributes(row: dict[str, str], standard_name: str) -> dict[str, str]:
    attrs = _parse_specs(row.get("required_specs", ""))
    for key in ("brand", "model"):
        _add_attr(attrs, key, row.get(key, ""))
    # A strength grade in the old item name is factual source evidence.  Move
    # it into a SKU attribute when it was not already present in specs.
    strength_match = STRENGTH_RE.search(f"{row.get('item_name', '')} {row.get('sku_name', '')}")
    if strength_match:
        _add_attr(attrs, "strength_grade", strength_match.group("grade"))
    if "specification" not in attrs:
        dimension = DIMENSION_RE.search(row.get("sku_name", ""))
        if dimension:
            _add_attr(attrs, "specification", dimension.group(0))
    if not attrs:
        _add_attr(attrs, "specification", "")
    return attrs


def _ordered_keys(keys: Iterable[str]) -> list[str]:
    rank = {key: i for i, key in enumerate(KEY_ORDER)}
    return sorted(set(keys), key=lambda key: (rank.get(key, len(KEY_ORDER)), key))


def _format_specs(attrs: dict[str, str], keys: Iterable[str] | None = None) -> str:
    selected = _ordered_keys(keys if keys is not None else attrs)
    return "; ".join(f"{KEY_DISPLAY_NAMES.get(key, key)}: {attrs[key]}" for key in selected if attrs.get(key))


def _type_id(classification_key: str) -> str:
    return "MT-" + hashlib.sha1(classification_key.encode("utf-8")).hexdigest()[:12].upper()


def _source_hash(row: dict[str, str]) -> str:
    raw = "\x1f".join(row.get(col, "") for col in SOURCE_COLUMNS)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _attribute_description(key: str, family: str) -> str:
    descriptions = {
        "specification": "用于区分同类物料的规格或型号，必须保留原始证据。",
        "size": "物料尺寸，按来源记录填写。",
        "nominal_diameter": "管件或阀门的公称直径。",
        "material": "物料材质，按来源记录填写，不得凭空推断。",
        "strength_grade": "强度等级；属于 SKU 属性，不得放入标准物料名称。",
        "surface_treatment": "表面处理方式。",
        "brand": "品牌；缺失时保持为空并进入补录。",
        "model": "制造商型号；缺失时保持为空并进入补录。",
        "capacity": "容量或包装容量。",
        "package_specification": "包装规格，不得建立为物料分类。",
        "rated_voltage": "额定电压。",
        "rated_current": "额定电流。",
        "pressure": "压力等级或工作压力。",
        "working_pressure": "工作压力。",
        "connection_type": "连接方式或接口形式。",
    }
    return descriptions.get(key, f"{KEY_DISPLAY_NAMES.get(key, key)}（{family}）按来源证据填写。")


def _unsafe_reason(top_group: str, family: str, standard_name: str) -> str:
    reasons: list[str] = []
    if top_group in HIGH_RISK_GROUPS:
        reasons.append(f"高风险分类:{top_group}")
    if any(term in f"{family}{standard_name}" for term in ("压力", "吊带", "安全带", "灭火", "防毒", "化学")):
        reasons.append("安全/压力/化学相关物料")
    return "；".join(reasons)


def _write_tsv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows({key: "" if value is None else value for key, value in row.items()} for row in rows)


def _reported_path(path: Path) -> str:
    """Keep release metadata portable when tests write to a temp directory."""

    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(resolved)


def rebuild(input_path: Path = DEFAULT_INPUT, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, object]:
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle, delimiter="\t"))
    missing_columns = [column for column in SOURCE_COLUMNS if column not in (source_rows[0] if source_rows else {})]
    if missing_columns:
        raise ValueError(f"input catalog is missing columns: {missing_columns}")

    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    prepared: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []
    for source in source_rows:
        source = {key: _clean(value) for key, value in source.items()}
        top_group = source["top_group"] if source["top_group"] in TOP_GROUPS else "待治理"
        family, family_candidate = _strip_family(source["material_family"] or source["sub_group"])
        standard_name, name_notes = _clean_standard_name(source["item_name"], source.get("brand", ""))
        attrs = _attributes(source, standard_name)
        classification_key = "|".join((top_group, family, standard_name))
        record: dict[str, object] = {
            "source": source,
            "top_group": top_group,
            "family": family,
            "family_candidate": family_candidate,
            "standard_name": standard_name,
            "name_notes": name_notes,
            "attrs": attrs,
            "classification_key": classification_key,
        }
        grouped[classification_key].append(record)
        prepared.append(record)

    type_rows: list[dict[str, object]] = []
    template_rows: list[dict[str, object]] = []
    mapping_rows: list[dict[str, object]] = []
    type_meta: dict[str, dict[str, object]] = {}
    for classification_key, records in sorted(grouped.items()):
        first = records[0]
        type_id = _type_id(classification_key)
        all_keys = set().union(*(record["attrs"].keys() for record in records))
        # Only source-backed keys become required.  This is the central rule
        # preventing a generated value from pretending to be user evidence.
        required_keys = _ordered_keys(key for key in all_keys if key not in NON_IDENTITY_KEYS)
        if not required_keys:
            required_keys = ["specification"]
        missing_by_code: dict[str, list[str]] = {}
        for record in records:
            attrs = record["attrs"]
            missing_by_code[record["source"]["item_code"]] = [key for key in required_keys if not attrs.get(key)]
        unsafe_reason = _unsafe_reason(first["top_group"], first["family"], first["standard_name"])
        has_missing = any(missing_by_code.values())
        has_candidate = any(record["family_candidate"] for record in records) or first["family"] == "待治理"
        governance_status = "needs_review" if has_candidate or unsafe_reason else "frozen"
        type_meta[classification_key] = {
            "type_id": type_id,
            "required_keys": required_keys,
            "missing_by_code": missing_by_code,
            "unsafe_reason": unsafe_reason,
            "governance_status": governance_status,
        }
        type_rows.append(
            {
                "type_id": type_id,
                "top_group": first["top_group"],
                "material_family": first["family"],
                "standard_name": first["standard_name"],
                "classification_key": classification_key,
                "definition": f"{first['standard_name']} 的标准物料类型；分类层级为 {first['top_group']} / {first['family']}。",
                "includes": "来源发布 SKU 的标准名称归一化结果；原始名称保留在 aliases/source_item_name。",
                "excludes": "品牌、型号、规格、强度、包装等 SKU 属性不得新建为分类。",
                "governance_status": governance_status,
                "revision": "1",
                "source_hash": hashlib.sha256(classification_key.encode("utf-8")).hexdigest(),
                "prompt_version": RULE_VERSION,
                "generator_model": "deterministic-rule-engine",
                "reviewer_model": "human_required_for_flagged_rows",
                "required_attribute_keys": ",".join(required_keys),
                "sku_count": len(records),
                "unsafe_reason": unsafe_reason,
            }
        )
        for order, key in enumerate(required_keys, 1):
            template_rows.append(
                {
                    "type_id": type_id,
                    "attribute_key": key,
                    "display_name": KEY_DISPLAY_NAMES.get(key, key),
                    "requirement": "required",
                    "value_type": "text",
                    "unit": "",
                    "enum_values": "",
                    "affects_sku_identity": "true",
                    "display_order": order,
                    "description": _attribute_description(key, first["family"]),
                    "source_evidence": "source_required_specs/brand/model",
                }
            )

    release_rows: list[dict[str, object]] = []
    for record in prepared:
        source = record["source"]
        meta = type_meta[record["classification_key"]]
        attrs = record["attrs"]
        required_keys = meta["required_keys"]
        missing = meta["missing_by_code"][source["item_code"]]
        unsafe_reason = meta["unsafe_reason"]
        family_candidate = record["family_candidate"]
        notes = list(record["name_notes"])
        if family_candidate:
            notes.append("source_family_was_candidate")
        if record["top_group"] == "待治理":
            notes.append("source_top_group_missing_or_unrecognized")
        if missing:
            notes.append("missing_required_specs:" + ",".join(missing))
        if unsafe_reason:
            notes.append(unsafe_reason)
        if not notes and source.get("governance_note"):
            notes.append(source["governance_note"])
        classification_status = "needs_input" if missing else ("needs_review" if family_candidate or unsafe_reason else "ready")
        quality_level = "needs_review" if classification_status != "ready" else "standard"
        policy = "clarify_specs_before_use" if missing else ("confirm_before_use" if classification_status == "needs_review" else "auto_select_allowed")
        aliases = []
        for value in [source.get("aliases", ""), source.get("item_name", ""), source.get("sku_name", "")]:
            for alias in re.split(r"[;,；|]", value):
                alias = _clean(alias)
                if alias and alias not in aliases and alias != record["standard_name"]:
                    aliases.append(alias)
        sku_values: list[str] = []
        for key in _ordered_keys(attrs):
            value = attrs.get(key, "")
            if value and value not in sku_values and value != record["standard_name"]:
                sku_values.append(value)
        sku_name = " ".join([record["standard_name"], *sku_values]).strip()
        keywords = []
        for value in [source["item_code"], record["standard_name"], source["item_name"], source["sku_name"], *aliases, *sku_values]:
            value = _clean(value)
            if value and value not in keywords:
                keywords.append(value)
        normalized_specs = _format_specs(attrs)
        release_row = dict(source)
        release_row.update(
            {
                "item_name": record["standard_name"],
                "sku_name": sku_name,
                "required_specs": normalized_specs,
                "optional_specs": _clean(source.get("optional_specs", "")),
                "item_group": f"{record['top_group']}/{source['sub_group'] or record['family']}",
                "top_group": record["top_group"],
                "material_family": record["family"],
                "stock_uom": source["stock_uom"] or "个",
                "purchase_uom": source["purchase_uom"] or source["stock_uom"] or "个",
                "conversion_factor": source["conversion_factor"] or "1",
                "aliases": "; ".join(aliases),
                "search_keywords": " ".join(keywords),
                "quality_level": quality_level,
                "agent_use_policy": policy,
                "governance_note": "；".join(notes),
                "classification_key": record["classification_key"],
                "standard_name": record["standard_name"],
                "required_attribute_keys": ",".join(required_keys),
                "missing_required_specs": ",".join(missing),
                "classification_status": classification_status,
                "source_item_name": source["item_name"],
                "source_sku_name": source["sku_name"],
                "source_required_specs": source["required_specs"],
                "source_item_group": source["item_group"],
                "source_material_family": source["material_family"],
                "rule_version": RULE_VERSION,
            }
        )
        release_rows.append(release_row)
        mapping_rows.append(
            {
                "item_code": source["item_code"],
                "type_id": meta["type_id"],
                "standard_name": record["standard_name"],
                "mapping_method": "deterministic_v1_1_normalization",
                "mapping_evidence": "source item_name/item_group/material_family plus source_required_specs",
                "mapping_status": "needs_review" if classification_status != "ready" else "frozen",
                "source_hash": _source_hash(source),
                "classification_key": record["classification_key"],
                "missing_required_specs": ",".join(missing),
            }
        )
        if missing:
            audit_rows.append(
                {
                    "issue_type": "missing_required_specs",
                    "scope": "sku",
                    "item_code": source["item_code"],
                    "type_id": meta["type_id"],
                    "classification_key": record["classification_key"],
                    "detail": ",".join(missing),
                    "severity": "high",
                }
            )
        if family_candidate:
            audit_rows.append(
                {
                    "issue_type": "candidate_family",
                    "scope": "sku",
                    "item_code": source["item_code"],
                    "type_id": meta["type_id"],
                    "classification_key": record["classification_key"],
                    "detail": source["material_family"],
                    "severity": "high",
                }
            )
        if unsafe_reason:
            audit_rows.append(
                {
                    "issue_type": "human_confirmation_required",
                    "scope": "sku",
                    "item_code": source["item_code"],
                    "type_id": meta["type_id"],
                    "classification_key": record["classification_key"],
                    "detail": unsafe_reason,
                    "severity": "medium",
                }
            )
        if record["name_notes"]:
            audit_rows.append(
                {
                    "issue_type": "standard_name_normalized",
                    "scope": "sku",
                    "item_code": source["item_code"],
                    "type_id": meta["type_id"],
                    "classification_key": record["classification_key"],
                    "detail": ",".join(record["name_notes"]),
                    "severity": "info",
                }
            )

    alias_to_types: dict[str, set[str]] = defaultdict(set)
    for row in release_rows:
        for alias in re.split(r"[;,；|]", row["aliases"]):
            alias = _clean(alias)
            if alias:
                alias_to_types[alias].add(row["classification_key"])
    for alias, keys in sorted(alias_to_types.items()):
        if len(keys) > 1:
            audit_rows.append(
                {
                    "issue_type": "ambiguous_alias",
                    "scope": "alias",
                    "item_code": "",
                    "type_id": "",
                    "classification_key": "|".join(sorted(keys)),
                    "detail": alias,
                    "severity": "high",
                }
            )
            for row in release_rows:
                if alias in {_clean(x) for x in re.split(r"[;,；|]", row["aliases"])} and row["agent_use_policy"] == "auto_select_allowed":
                    row["agent_use_policy"] = "confirm_before_use"
                    row["quality_level"] = "needs_review"
                    row["classification_status"] = "needs_review"
                    row["governance_note"] = (row["governance_note"] + "；" if row["governance_note"] else "") + "ambiguous_alias:" + alias

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_tsv(output_dir / f"{RELEASE_NAME}.tsv", release_rows, RELEASE_COLUMNS)
    _write_tsv(
        output_dir / "material_type_dictionary.tsv",
        type_rows,
        [
            "type_id", "top_group", "material_family", "standard_name", "classification_key",
            "definition", "includes", "excludes", "governance_status", "revision", "source_hash",
            "prompt_version", "generator_model", "reviewer_model", "required_attribute_keys", "sku_count", "unsafe_reason",
        ],
    )
    _write_tsv(
        output_dir / "material_attribute_templates.tsv",
        template_rows,
        [
            "type_id", "attribute_key", "display_name", "requirement", "value_type", "unit", "enum_values",
            "affects_sku_identity", "display_order", "description", "source_evidence",
        ],
    )
    _write_tsv(
        output_dir / "sku_type_mapping.tsv",
        mapping_rows,
        [
            "item_code", "type_id", "standard_name", "mapping_method", "mapping_evidence", "mapping_status",
            "source_hash", "classification_key", "missing_required_specs",
        ],
    )
    _write_tsv(
        output_dir / "audit_report.tsv",
        audit_rows,
        ["issue_type", "scope", "item_code", "type_id", "classification_key", "detail", "severity"],
    )

    issue_counts = Counter(row["issue_type"] for row in audit_rows)
    summary = {
        "release": RELEASE_NAME,
        "rule_version": RULE_VERSION,
        "authoritative": False,
        "input_release": "material_master_release_v1_0",
        "input_path": _reported_path(input_path),
        "output_path": _reported_path(output_dir / f"{RELEASE_NAME}.tsv"),
        "row_count": len(release_rows),
        "unique_item_codes": len({row["item_code"] for row in release_rows}),
        "type_count": len(type_rows),
        "mapped_sku_count": len(mapping_rows),
        "quality_counts": dict(Counter(row["quality_level"] for row in release_rows)),
        "policy_counts": dict(Counter(row["agent_use_policy"] for row in release_rows)),
        "classification_status_counts": dict(Counter(row["classification_status"] for row in release_rows)),
        "issue_counts": dict(issue_counts),
        "ambiguous_alias_count": sum(1 for row in audit_rows if row["issue_type"] == "ambiguous_alias"),
        "generated_by": "rebuild_material_master_v1_1.py",
        "no_erpnext_write": True,
    }
    (output_dir / f"{RELEASE_NAME}_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "audit_report.json").write_text(json.dumps({"summary": summary, "issues": audit_rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary = rebuild(args.input, args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
