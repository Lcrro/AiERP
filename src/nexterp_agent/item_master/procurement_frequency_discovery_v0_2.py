"""Second-pass discovery of material families in a purchase list.

The v0.1 detector is intentionally kept as a baseline.  This module fixes
the two largest first-pass problems without writing any business data:

* a raw name, an alias, a specification, a SKU and a purchase event are
  represented separately;
* unit quality is reported as evidence, not used to hide a useful family.

The result is still a candidate list.  It is not a material-master release
and it never writes ERPNext.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import difflib
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable
import unicodedata

from .procurement_frequency_discovery import (
    DEFAULT_SOURCE_PATH,
    DiscoveryRow,
    _BRANDS,
    _PACK_RE,
    normalize_text,
    normalize_uom,
    read_source_rows,
)


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = ROOT / ".runtime" / "material-master" / "frequency-discovery-v0.2"
VERSION = "procurement-frequency-discovery-v0.2"

_SIZE_PATTERNS = (
    re.compile(
        r"(?i)(?<![a-z0-9])(?:m|dn|φ|ф|ø|Φ|Ø)\s*\d+(?:\.\d+)?"
        r"(?:\s*[×x*/]\s*(?:m|dn|φ|ф|ø|Φ|Ø)?\s*\d+(?:\.\d+)?)*"
        r"\s*(?:mm|cm|m|米|毫米)?"
    ),
    re.compile(
        r"(?i)(?<![a-z0-9])\d+(?:\.\d+)?\s*(?:t|kg|l|ml|a|w|v|号)"
        r"(?:\s*[×x*/]\s*\d+(?:\.\d+)?\s*(?:m|米|mm|cm)?)?"
    ),
    re.compile(
        r"(?i)(?<![a-z0-9])\d+(?:\.\d+)?(?:\s*[×x*/]\s*\d+(?:\.\d+)?){1,3}"
        r"\s*(?:mm|cm|m|米|毫米)?"
    ),
)
_GRADE_RE = re.compile(
    r"(?i)(?<![a-z0-9])(?:\d+(?:\.\d+)?\s*级|hrb\s*\d+[a-z]*|a\s*\d+\s*-\s*\d+|p\.?o\.?\s*\d+(?:\.\d+)?)"
)
_PACKAGING_RE = re.compile(
    r"(?i)(?<![a-z0-9])\d+(?:\.\d+)?\s*(?:只|个|支|把|套|盒|包|片|根|条|张|瓶|桶|付|kg|千克)"
    r"\s*/\s*(?:只|个|支|把|套|盒|包|片|根|条|张|瓶|桶|付|kg|千克|袋|箱)"
)
_MODEL_RE = re.compile(r"(?i)(?<![a-z0-9])(?:86|118)\s*型")
_PUNCT_RE = re.compile(r"[^0-9a-z\u4e00-\u9fffφΦ]+", re.I)
_SPACE_RE = re.compile(r"\s+")

_ATTR_ORDER = (
    "规格",
    "性能/等级",
    "材质",
    "表面处理",
    "接口/结构",
    "用途",
    "包装",
    "品牌",
)

# Packaging and brand are useful evidence for sourcing/price differences, but
# they do not define the material family's physical specification.  Keeping
# them out of ``variant_key`` prevents a supplier name or pack size from
# inflating the number of specification variants.  They remain in
# ``alias_key``/``attributes_observed`` for review and later SKU decisions.
_VARIANT_EXCLUDED_ATTRIBUTES = frozenset({"品牌", "包装"})

_MATERIAL_TERMS = (
    "不锈钢", "碳钢", "低碳钢", "铝合金", "铝", "铜", "黄铜", "尼龙", "PVC", "PPR",
    "橡胶", "塑料", "混凝土", "水泥", "天然麻纤维", "钢", "铁", "玻璃纤维",
)
_FINISH_TERMS = (
    "镀锌", "热镀锌", "冷镀锌", "磷化", "黑磷化", "常规防锈", "防锈", "喷塑", "不锈钢",
    "白色", "中灰", "黄色", "黑色",
)
_INTERFACE_TERMS = (
    "内丝", "外丝", "内牙", "外牙", "法兰", "直通", "直接", "弯头", "三通", "异径",
    "变径", "六角", "圆柱头", "开口", "十字", "一字", "自攻", "钻尾", "全螺纹",
    "扣压", "卡箍式", "套筒", "插座", "面板", "端子", "球形",
)
_USE_TERMS = (
    "管片专用", "建筑用", "排水", "消防", "防爆", "高压", "浇水", "花园", "工业",
    "现场", "抗震", "装饰", "混凝土抗压", "家用", "企业",
)
_DROP_DESCRIPTORS = (
    "常用默认", "常规", "普通", "加厚", "优质", "精品", "大", "小", "白色", "中灰",
    "黄色", "黑色", "不锈钢", "碳钢", "低碳钢", "铝合金", "镀锌", "磷化", "防锈",
)
_GENERIC_HEADS = (
    "钢丝绳防锈剂", "聚氨酯密封胶", "平面密封胶", "普通硅酸盐水泥", "建筑用天然砂",
    "高压胶管", "高压油管", "排水软管", "园林浇水软管", "手拉葫芦", "钢丝绳",
    "灭火器", "灭火器箱", "弹簧垫圈", "平垫圈", "垫圈", "螺纹钢", "钢筋", "螺栓",
    "螺钉", "螺丝", "螺母", "弯头", "三通", "接头", "直接", "阀", "焊条", "焊丝",
    "钻头", "扳手", "手套", "水带", "吊带", "膨胀管", "膨胀锚栓", "水泥", "砂",
    "砖", "插座", "面板", "端子", "接触器", "卷尺", "安全网", "油布", "垃圾桶",
    "密封胶", "胶带", "锁", "袋", "凳子", "雨衣", "灯", "软管", "葫芦", "表",
)
_CANONICAL_HEADS = {
    # “螺丝” is intentionally not rewritten to “螺钉”.  The source uses it
    # for both screws and bolts, so it must remain a review-only generic head.
    "螺丝": "螺丝",
    "螺钉": "螺钉",
    "膨胀管": "膨胀管",
    "直通": "直接",
}

# Strong seeds.  A seed is a family hypothesis, not an approval to publish.
# The blocked seeds prevent the first pass' steel-rebar false positive.
_EXPLICIT_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("灭火器箱", re.compile(r"灭火器\s*(?:箱|箱子)", re.I), "explicit"),
    ("灭火器", re.compile(r"(?<!箱)灭火器", re.I), "explicit"),
    ("钢筋扭矩扳手", re.compile(r"钢筋.*(?:扭矩|力矩).*扳手", re.I), "blocked"),
    ("钢筋保护套", re.compile(r"钢筋.*保护套", re.I), "blocked"),
    ("螺纹钢", re.compile(r"螺纹钢|带肋钢筋|抗震热轧带肋钢筋", re.I), "explicit"),
    ("开口铜接线端子", re.compile(r"开口.*铜(?:接线)?端子|开口铜鼻子", re.I), "explicit"),
    ("PPR内丝弯头", re.compile(r"ppr.*(?:内丝|内牙).*弯头", re.I), "explicit"),
    ("PPR异径三通", re.compile(r"ppr.*(?:变|异径).*三通|ppr.*\d+\s*/\s*\d+.*三通", re.I), "explicit"),
    ("PPR弯头", re.compile(r"ppr.*弯头", re.I), "explicit"),
    ("PPR内丝直接", re.compile(r"ppr.*(?:内丝|内牙).*?(?:直接|直通)", re.I), "explicit"),
    ("PPR截止阀", re.compile(r"ppr.*截止阀", re.I), "explicit"),
    ("PPR三通", re.compile(r"ppr.*三通", re.I), "explicit"),
    ("PPR直接", re.compile(r"ppr.*(?:直接|直通)", re.I), "explicit"),
    ("PPR管", re.compile(r"ppr.*(?:管|管材)", re.I), "explicit"),
    ("内六角螺钉", re.compile(r"内六角.*(?:螺钉|螺丝)", re.I), "explicit"),
    ("六角螺栓", re.compile(r"(?<!内)(?:六角|外六角).*?(?:螺栓|螺丝)", re.I), "explicit"),
    ("双头螺栓", re.compile(r"双头.*(?:螺栓|螺丝)", re.I), "explicit"),
    ("预埋螺栓", re.compile(r"预埋.*(?:螺栓|螺丝)", re.I), "explicit"),
    ("膨胀锚栓", re.compile(r"膨胀.*(?:锚栓|膨胀栓)", re.I), "explicit"),
    ("钻尾螺钉", re.compile(r"钻尾.*(?:螺钉|螺丝)", re.I), "explicit"),
    ("自攻螺钉", re.compile(r"自攻.*(?:螺钉|螺丝)", re.I), "explicit"),
    ("弹簧垫圈与平垫圈组合", re.compile(r"(?:弹垫|弹簧垫).*平垫|(?:平垫|平垫圈).*弹垫", re.I), "explicit"),
    ("高压胶管", re.compile(r"高压.*胶管", re.I), "explicit"),
    ("药芯焊丝", re.compile(r"药芯焊丝", re.I), "explicit"),
    ("焊条", re.compile(r"焊条", re.I), "explicit"),
    ("钢丝绳防锈剂", re.compile(r"钢丝绳.*(?:喷雾|防锈剂|除锈剂)", re.I), "explicit"),
    ("钢丝绳扣", re.compile(r"钢丝绳扣", re.I), "explicit"),
    ("扣压钢丝绳", re.compile(r"扣压钢丝绳", re.I), "explicit"),
    ("钢丝绳", re.compile(r"钢丝绳", re.I), "explicit"),
    ("吊带", re.compile(r"吊带", re.I), "explicit"),
    ("手拉葫芦保险扣", re.compile(r"手拉葫芦.*保险扣", re.I), "explicit"),
    ("手拉葫芦", re.compile(r"手拉葫芦", re.I), "explicit"),
    ("铝合金快速接头", re.compile(r"铝合金.*快速接头", re.I), "explicit"),
    ("防锈漆", re.compile(r"防锈漆", re.I), "explicit"),
    ("聚氨酯密封胶", re.compile(r"聚氨酯.*密封胶", re.I), "explicit"),
    ("平面密封胶", re.compile(r"平面密封胶", re.I), "explicit"),
    ("双排插拖线板", re.compile(r"双排.*(?:插板|插拖线板)", re.I), "explicit"),
    ("背胶草皮", re.compile(r"背胶草(?:皮|坪)", re.I), "explicit"),
    ("建筑用天然砂", re.compile(r"黄沙|天然砂|中砂|河沙", re.I), "explicit"),
    ("混凝土/水泥砖", re.compile(r"水泥砖|混凝土.*砖", re.I), "explicit"),
    ("水泥垫块", re.compile(r"水泥垫块", re.I), "explicit"),
    ("白水泥", re.compile(r"白水泥", re.I), "explicit"),
    ("普通硅酸盐水泥", re.compile(r"(?:普通)?硅酸盐水泥|海螺.*水泥|(?:42(?:\.5)?|425)水泥", re.I), "explicit"),
    ("尼龙膨胀管", re.compile(r"膨胀管", re.I), "explicit"),
    ("排水软管", re.compile(r"排水.*(?:软管|水管)", re.I), "explicit"),
    ("园林/浇水软管", re.compile(r"(?:草坪|浇水|花园).*软管", re.I), "explicit"),
)


def _canonical_text(value: Any) -> str:
    text = normalize_text(value)
    return text.replace("×", "x").replace("＊", "*").replace("／", "/")


def _find_terms(text: str, terms: Iterable[str]) -> list[str]:
    return [term for term in terms if term.casefold() in text.casefold()]


def _extract_brand(text: str) -> str:
    return "、".join(brand for brand in _BRANDS if brand.casefold() in text.casefold())


def _canonical_size(value: str, family: str) -> str:
    result = normalize_text(value).replace("×", "x").replace("＊", "*")
    result = _SPACE_RE.sub("", result).upper()
    # PPR suppliers routinely alternate Φ110, DN110 and plain 110.
    if family.startswith("PPR"):
        result = re.sub(r"^(?:Φ|Ф|Ø|DN)", "", result, flags=re.I)
    return result


def _extract_attributes(raw_name: str, family: str) -> dict[str, str]:
    text = _canonical_text(raw_name)
    attributes: dict[str, str] = {}
    # Do not let package counts (for example 300只/包) become a dimension.
    size_text = _PACKAGING_RE.sub(" ", text)
    size_matches: list[tuple[int, int, str]] = []
    if family.startswith("PPR"):
        # Supplier names alternate PPRΦ110、PPR110 and PPR110/50.  Anchoring
        # at PPR avoids the look-behind problem caused by the preceding R.
        for match in re.finditer(
            r"(?i)ppr\s*(?:Φ|Ф|Ø|DN)?\s*\d+(?:\s*[/x*]\s*(?:Φ|Ф|Ø|DN)?\s*\d+)*",
            size_text,
        ):
            size_matches.append((*match.span(), re.sub(r"(?i)^ppr", "", match.group(0))))
    for pattern in _SIZE_PATTERNS:
        for match in pattern.finditer(size_text):
            size_matches.append((*match.span(), match.group(0)))
    # Keep the longest non-overlapping token.  This prevents Φ110/45 from
    # being emitted again as 110 and 45.
    selected_sizes: list[tuple[int, int, str]] = []
    for start, end, value in sorted(size_matches, key=lambda item: (-(item[1] - item[0]), item[0])):
        if any(start < other_end and end > other_start for other_start, other_end, _ in selected_sizes):
            continue
        selected_sizes.append((start, end, value))
    sizes = [value for _, _, value in sorted(selected_sizes, key=lambda item: item[0])]
    if _MODEL_RE.search(text):
        sizes.append(_MODEL_RE.search(text).group(0))
    canonical_sizes = list(dict.fromkeys(_canonical_size(value, family) for value in sizes))
    if canonical_sizes:
        attributes["规格"] = " / ".join(canonical_sizes)
    grades = list(dict.fromkeys(_canonical_text(match.group(0)) for match in _GRADE_RE.finditer(text)))
    if grades:
        attributes["性能/等级"] = " / ".join(grades)
    materials = _find_terms(text, _MATERIAL_TERMS)
    if materials:
        attributes["材质"] = " / ".join(materials)
    finishes = _find_terms(text, _FINISH_TERMS)
    if finishes:
        attributes["表面处理"] = " / ".join(finishes)
    interfaces = _find_terms(text, _INTERFACE_TERMS)
    if interfaces:
        attributes["接口/结构"] = " / ".join(interfaces)
    uses = _find_terms(text, _USE_TERMS)
    if uses:
        attributes["用途"] = " / ".join(uses)
    packaging = list(dict.fromkeys(_canonical_text(match.group(0)) for match in _PACKAGING_RE.finditer(text)))
    if packaging:
        attributes["包装"] = " / ".join(packaging)
    brand = _extract_brand(text)
    if brand:
        attributes["品牌"] = brand
    return attributes


def _variant_key(attributes: dict[str, str]) -> str:
    return "|".join(
        f"{key}={attributes[key]}"
        for key in _ATTR_ORDER
        if key not in _VARIANT_EXCLUDED_ATTRIBUTES and attributes.get(key)
    ) or "(无可识别规格)"


def _alias_key(family: str, attributes: dict[str, str]) -> str:
    # Brand is deliberately excluded: it is useful SKU evidence, not an alias
    # boundary.  Other attributes stay in the key so size variants do not look
    # like spelling aliases.
    return f"{family}|" + "|".join(
        f"{key}={attributes[key]}" for key in _ATTR_ORDER if key not in {"品牌"} and attributes.get(key)
    )


def _remove_specs_for_family(text: str) -> str:
    result = _canonical_text(text)
    for brand in _BRANDS:
        result = result.replace(brand, "")
    result = _PACKAGING_RE.sub("", result)
    result = _PACK_RE.sub("", result)
    result = _GRADE_RE.sub("", result)
    for pattern in _SIZE_PATTERNS:
        result = pattern.sub("", result)
    result = _MODEL_RE.sub("", result)
    for descriptor in _DROP_DESCRIPTORS:
        result = result.replace(descriptor, "")
    result = _PUNCT_RE.sub(" ", result.casefold())
    result = _SPACE_RE.sub("", result)
    return result


def _generic_family_key(raw_name: str) -> str:
    residual = _remove_specs_for_family(raw_name)
    if not residual:
        return ""
    # Preserve informative prefixes (PPR、高压、氧气、内六角等) while using a
    # stable canonical head.  Unknown text remains a review-only candidate.
    heads = sorted(_GENERIC_HEADS, key=len, reverse=True)
    for head in heads:
        normalized_head = head.casefold()
        if normalized_head in residual:
            prefix = residual.replace(normalized_head, "")
            prefix = prefix.strip()
            prefix = prefix.replace("螺丝", "").replace("螺钉", "") if head in {"螺丝", "螺钉"} else prefix
            canonical_head = _CANONICAL_HEADS.get(head, head)
            if prefix in {"", "型", "式"}:
                return canonical_head
            return f"{prefix}{canonical_head}"
    return residual if len(residual) >= 2 else ""


def _classify_family(raw_name: str) -> tuple[str, str]:
    text = normalize_text(raw_name)
    for family, pattern, confidence in _EXPLICIT_RULES:
        if pattern.search(text):
            return family, confidence
    generic = _generic_family_key(text)
    if generic:
        return generic, "lexical_candidate"
    return normalize_text(text), "unresolved"


@dataclass(frozen=True)
class DiscoveryV2Row:
    source_row: int
    purchase_date: str
    raw_name: str
    qty: float | None
    raw_uom: str
    normalized_uom: str
    procedure_sequence: str
    market_unit_price: float | None
    family_candidate: str
    family_confidence: str
    attributes: dict[str, str]
    variant_key: str
    alias_key: str
    flags: tuple[str, ...]


def convert_rows(rows: list[DiscoveryRow]) -> list[DiscoveryV2Row]:
    output: list[DiscoveryV2Row] = []
    for row in rows:
        family, confidence = _classify_family(row.raw_name)
        attributes = _extract_attributes(row.raw_name, family)
        output.append(DiscoveryV2Row(
            source_row=row.source_row,
            purchase_date=row.purchase_date,
            raw_name=row.raw_name,
            qty=row.qty,
            raw_uom=row.raw_uom,
            normalized_uom=row.normalized_uom or normalize_uom(row.raw_uom),
            procedure_sequence=row.procedure_sequence,
            market_unit_price=row.market_unit_price,
            family_candidate=family,
            family_confidence=confidence,
            attributes=attributes,
            variant_key=_variant_key(attributes),
            alias_key=_alias_key(family, attributes),
            flags=row.flags,
        ))
    return output


def _cluster_id(key: str, source_rows: Iterable[int]) -> str:
    payload = json.dumps([key, sorted(source_rows)], ensure_ascii=False, separators=(",", ":"))
    return f"PF2-{min(source_rows):04d}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:8].upper()}"


def _uom_quality(members: list[DiscoveryV2Row]) -> dict[str, Any]:
    raw_uoms = sorted({row.raw_uom for row in members if row.raw_uom})
    normalized_uoms = sorted({row.normalized_uom for row in members if row.normalized_uom})
    by_name: dict[str, set[str]] = defaultdict(set)
    for row in members:
        if row.normalized_uom:
            by_name[row.raw_name].add(row.normalized_uom)
    same_name_conflict = any(len(values) > 1 for values in by_name.values())
    if same_name_conflict:
        status = "same_name_conflict"
    elif len(normalized_uoms) > 1:
        status = "mixed_family_conflict"
    elif len(raw_uoms) > 1:
        status = "normalized_consistent_with_aliases"
    elif normalized_uoms:
        status = "consistent"
    else:
        status = "missing"
    counts = Counter(row.normalized_uom for row in members if row.normalized_uom)
    return {
        "raw_uoms": raw_uoms,
        "normalized_uoms": normalized_uoms,
        "mode_uom": counts.most_common(1)[0][0] if counts else "",
        "status": status,
        "same_name_conflict": same_name_conflict,
    }


def _event_key(row: DiscoveryV2Row) -> tuple[str, str, str]:
    # Alias spellings sharing a variant on the same date/procedure count once;
    # two different variants in one session remain separate events.
    return row.purchase_date, row.procedure_sequence, row.variant_key


def build_clusters_v2(rows: list[DiscoveryV2Row]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[DiscoveryV2Row]] = defaultdict(list)
    for row in rows:
        key = (row.family_candidate, row.family_confidence)
        grouped[key].append(row)
    clusters: list[dict[str, Any]] = []
    for (family, confidence), members in sorted(grouped.items(), key=lambda item: min(row.source_row for row in item[1])):
        raw_names = list(dict.fromkeys(row.raw_name for row in members))
        variant_keys = list(dict.fromkeys(row.variant_key for row in members))
        variant_keys_nonempty = [key for key in variant_keys if key != "(无可识别规格)"]
        variant_count = len(variant_keys_nonempty) or (1 if members else 0)
        alias_groups: list[dict[str, Any]] = []
        by_variant: dict[str, list[DiscoveryV2Row]] = defaultdict(list)
        for row in members:
            by_variant[row.variant_key].append(row)
        for variant_key, variant_members in by_variant.items():
            names = list(dict.fromkeys(row.raw_name for row in variant_members))
            alias_keys = sorted({row.alias_key for row in variant_members})
            if len(names) > 1:
                alias_groups.append({
                    "variant_key": variant_key,
                    "raw_names": names,
                    "source_rows": [row.source_row for row in variant_members],
                    "status": "同规格不同叫法/待确认" if len(alias_keys) > 1 else "疑似别名",
                })
        uom = _uom_quality(members)
        event_keys = {_event_key(row) for row in members}
        sessions = {(row.purchase_date, row.procedure_sequence) for row in members}
        dates = {row.purchase_date for row in members}
        qty_by_uom: dict[str, float] = defaultdict(float)
        total_value = 0.0
        priced_rows = 0
        for row in members:
            if row.qty is not None:
                qty_by_uom[row.normalized_uom or "(缺失)"] += row.qty
            if row.qty is not None and row.market_unit_price is not None:
                total_value += row.qty * row.market_unit_price
                priced_rows += 1
        attributes_observed: dict[str, list[str]] = {}
        for attr in _ATTR_ORDER:
            values = sorted({row.attributes[attr] for row in members if row.attributes.get(attr)})
            if values:
                attributes_observed[attr] = values
        source_flags = sorted({flag for row in members for flag in row.flags})
        blocking_flags: list[str] = []
        if confidence == "blocked":
            blocking_flags.append("blocked_specific_item")
        if "service_or_logistics" in source_flags or "bundled_or_vague" in source_flags:
            blocking_flags.append("service_or_bundled_line")
        attribute_coverage = round(
            sum(bool(row.attributes) for row in members) / len(members), 6
        ) if members else 0.0
        alias_group_count = len(alias_groups)
        score = (
            math.log1p(len(event_keys))
            * (1.0 + 0.5 * math.log1p(max(0, variant_count - 1)))
            * (1.0 + 0.25 * math.log1p(alias_group_count))
        )
        if confidence == "explicit" and variant_count > 1:
            queue = "多规格族候选"
        elif confidence == "lexical_candidate" and variant_count > 1:
            queue = "词法族候选/待复核"
        elif alias_group_count:
            queue = "疑似别名/待复核"
        elif confidence in {"blocked", "unresolved"}:
            queue = "保持独立/待复核"
        else:
            queue = "单规格候选"
        if uom["status"] in {"same_name_conflict", "mixed_family_conflict"}:
            review_status = "单位字段待复核"
        elif blocking_flags:
            review_status = "禁止自动发布"
        else:
            review_status = "可进入人工确认"
        auto_ready = (
            confidence == "explicit"
            and variant_count > 1
            and uom["status"] in {"consistent", "normalized_consistent_with_aliases"}
            and not blocking_flags
        )
        clusters.append({
            "cluster_id": _cluster_id(f"{family}:{confidence}", [row.source_row for row in members]),
            "standard_type_candidate": family,
            "family_confidence": confidence,
            "queue": queue,
            "review_status": review_status,
            "auto_ready_multi_attribute": auto_ready,
            "source_rows": [row.source_row for row in members],
            "raw_names": raw_names,
            "line_count": len(members),
            "raw_name_count": len(raw_names),
            "distinct_event_count_approx": len(event_keys),
            "active_purchase_date_count": len(dates),
            "purchase_session_count": len(sessions),
            "repeat_line_count": len(members) - len(event_keys),
            "variant_count": variant_count,
            "variant_keys": variant_keys,
            "alias_candidate_group_count": alias_group_count,
            "alias_candidate_groups": alias_groups,
            "attributes_observed": attributes_observed,
            "attribute_coverage": attribute_coverage,
            "uom_quality": uom,
            "quantity_by_uom": dict(sorted(qty_by_uom.items())),
            "priced_line_count": priced_rows,
            "market_value_sum": round(total_value, 6),
            "source_flags": source_flags,
            "blocking_flags": blocking_flags,
            "integration_priority_score": round(score, 6),
            "frequency_metric_note": "事件按日期+工序+规格键去重；同规格别名在同一会话只计一次，规格不同仍分别计数。",
        })
    ranked = sorted(
        clusters,
        key=lambda row: (
            -row["integration_priority_score"],
            -row["distinct_event_count_approx"],
            -row["active_purchase_date_count"],
            row["cluster_id"],
        ),
    )
    frequency_ranked = sorted(
        ranked,
        key=lambda row: (
            -row["distinct_event_count_approx"],
            -row["active_purchase_date_count"],
            -row["purchase_session_count"],
            -row["line_count"],
            row["cluster_id"],
        ),
    )
    frequency_ranks = {row["cluster_id"]: index for index, row in enumerate(frequency_ranked, start=1)}
    for index, row in enumerate(ranked, start=1):
        row["integration_rank"] = index
        row["frequency_rank"] = frequency_ranks[row["cluster_id"]]
    return ranked


def _family_block_key(value: str) -> str:
    chinese = re.sub(r"[^\u4e00-\u9fff]", "", value)
    if chinese:
        return chinese[-2:]
    return value[:4]


def build_family_review_candidates(clusters: list[dict[str, Any]], *, limit: int = 500) -> list[dict[str, Any]]:
    review_clusters = [row for row in clusters if row["family_confidence"] != "explicit"]
    blocks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cluster in review_clusters:
        blocks[_family_block_key(cluster["standard_type_candidate"])].append(cluster)
    candidates: list[dict[str, Any]] = []
    for block in blocks.values():
        for index, left in enumerate(block):
            for right in block[index + 1:]:
                if left["standard_type_candidate"] == right["standard_type_candidate"]:
                    continue
                similarity = difflib.SequenceMatcher(
                    None,
                    left["standard_type_candidate"],
                    right["standard_type_candidate"],
                ).ratio()
                if similarity < 0.72:
                    continue
                candidates.append({
                    "left_cluster_id": left["cluster_id"],
                    "right_cluster_id": right["cluster_id"],
                    "similarity": round(similarity, 6),
                    "left_type": left["standard_type_candidate"],
                    "right_type": right["standard_type_candidate"],
                    "left_rows": left["source_rows"],
                    "right_rows": right["source_rows"],
                    "decision": "人工复核，不自动合并",
                    "reason": "相似度只用于发现可能的同族；仍需核对GPC范围、用途、结构、单位和价格影响。",
                })
    return sorted(
        candidates,
        key=lambda row: (-row["similarity"], row["left_cluster_id"], row["right_cluster_id"]),
    )[:limit]


def _row_json(row: DiscoveryV2Row) -> dict[str, Any]:
    value = asdict(row)
    value["flags"] = list(row.flags)
    return value


def discover_v2(
    source_path: Path = DEFAULT_SOURCE_PATH,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    source_rows = read_source_rows(source_path)
    rows = convert_rows(source_rows)
    clusters = build_clusters_v2(rows)
    review_candidates = build_family_review_candidates(clusters)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "source-rows.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(_row_json(row), ensure_ascii=False) + "\n")
    with (output_root / "clusters.jsonl").open("w", encoding="utf-8") as handle:
        for row in clusters:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (output_root / "fuzzy-review-candidates.jsonl").open("w", encoding="utf-8") as handle:
        for row in review_candidates:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    family_rows = [row for row in clusters if row["family_confidence"] in {"explicit", "lexical_candidate"}]
    safe_rows = [row for row in clusters if row["family_confidence"] == "explicit"]
    summary = {
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(Path(source_path).expanduser().resolve()),
        "source_sheet": "实际采购清单",
        "source_row_count": len(rows),
        "unique_raw_name_count": len({row.raw_name for row in rows}),
        "cluster_count": len(clusters),
        "explicit_family_count": len(safe_rows),
        "lexical_family_candidate_count": sum(1 for row in clusters if row["family_confidence"] == "lexical_candidate"),
        "unresolved_cluster_count": sum(1 for row in clusters if row["family_confidence"] == "unresolved"),
        "blocked_cluster_count": sum(1 for row in clusters if row["family_confidence"] == "blocked"),
        "family_candidate_count": len(family_rows),
        "family_candidate_row_count": sum(row["line_count"] for row in family_rows),
        "family_candidate_line_coverage_percent": round(100 * sum(row["line_count"] for row in family_rows) / len(rows), 2),
        "multi_spec_candidate_count": sum(1 for row in family_rows if row["variant_count"] > 1),
        "alias_candidate_group_count": sum(row["alias_candidate_group_count"] for row in family_rows),
        "auto_ready_multi_attribute_cluster_count": sum(1 for row in clusters if row["auto_ready_multi_attribute"]),
        "uom_conflict_cluster_count": sum(1 for row in clusters if row["uom_quality"]["status"] in {"same_name_conflict", "mixed_family_conflict"}),
        "same_name_uom_conflict_cluster_count": sum(1 for row in clusters if row["uom_quality"]["same_name_conflict"]),
        "missing_or_invalid_quantity_line_count": sum("missing_or_invalid_quantity" in row.flags for row in rows),
        "service_or_logistics_line_count": sum("service_or_logistics" in row.flags for row in rows),
        "bundled_or_vague_line_count": sum("bundled_or_vague" in row.flags for row in rows),
        "priced_line_count": sum(row.market_unit_price is not None for row in rows),
        "fuzzy_review_candidate_count": len(review_candidates),
        "writes_erpnext": False,
        "notes": [
            "v0.2是候选族发现和排序结果，不是物料主数据发布结果。",
            "raw_name_count、alias_candidate_group_count和variant_count分别表示原始名称、疑似别名组和规格键。",
            "单位冲突只作为数据质量警告；真正发布SKU前必须确认库存单位。",
            "显式族规则只是高质量种子，仍需网页审阅和GPC范围确认。",
        ],
    }
    (output_root / "discovery-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "summary": summary,
        "rows": rows,
        "clusters": clusters,
        "fuzzy_review_candidates": review_candidates,
        "output_root": str(output_root),
    }


__all__ = [
    "DEFAULT_OUTPUT_ROOT",
    "DiscoveryV2Row",
    "VERSION",
    "build_clusters_v2",
    "build_family_review_candidates",
    "convert_rows",
    "discover_v2",
]
