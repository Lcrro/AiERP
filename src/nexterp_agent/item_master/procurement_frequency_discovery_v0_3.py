"""Third-pass, quality-gated discovery of procurement material families.

v0.2 was useful for finding families, but its generic attribute parser exposed
three risks in the source workbook: hose lengths were lost, source units were
often unusable, and a few family-specific terms carried a different meaning
than the generic attribute name suggested.  v0.3 keeps the v0.2 evidence and
adds a deterministic quality gate.  It is still a read-only analysis: it never
creates or updates an ERPNext Item.

The important distinction in this module is:

* ``candidate_coverage`` means that a row has a family hypothesis;
* ``rule_ready_for_review`` means that a human can review a bounded family
  rule; and
* ``publish_gate`` is never an automatic publish decision.

Historical quantities, units and prices are retained as evidence.  A policy
unit is recommended for later templates, but the source value is never
silently rewritten.
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

from .procurement_frequency_discovery import DEFAULT_SOURCE_PATH, DiscoveryRow, normalize_uom, read_source_rows
from .procurement_frequency_discovery_v0_2 import (
    _canonical_text,
    _extract_attributes,
    _classify_family,
    _SPACE_RE,
)


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = ROOT / ".runtime" / "material-master" / "frequency-discovery-v0.3"
VERSION = "procurement-frequency-discovery-v0.3"


# These are policy units for future templates, not corrections to the source
# workbook.  The accepted set is deliberately narrow for linear/assembled
# goods and explicit for the families where the historical list is known to
# use aliases.  Anything outside it remains a review signal.
_FAMILY_UOM_POLICY: dict[str, dict[str, Any]] = {
    "PPR管": {"preferred": "米", "accepted": {"米"}},
    "高压胶管": {"preferred": "条", "accepted": {"条", "米", "卷"}},
    "灭火器": {"preferred": "件", "accepted": {"件"}},
    "弹簧垫圈与平垫圈组合": {"preferred": "套", "accepted": {"套", "件"}},
    "建筑用天然砂": {"preferred": "吨", "accepted": {"吨"}},
    "普通硅酸盐水泥": {"preferred": "袋", "accepted": {"袋", "吨"}},
    "螺纹钢": {"preferred": "吨", "accepted": {"吨"}},
    "钢丝绳": {"preferred": "卷", "accepted": {"卷", "米", "条"}},
    "吊带": {"preferred": "条", "accepted": {"条", "根", "件"}},
}

_DEFAULT_DISCRETE_UOM_POLICY = {"preferred": "件", "accepted": {"件", "套", "支", "根", "条", "只", "个"}}
_MISSING_ATTR_FLAGS = {
    "高压胶管": "missing_hose_length",
    "灭火器": "missing_extinguisher_agent_or_capacity",
    "弹簧垫圈与平垫圈组合": "missing_washer_thread_size",
}
_V3_ATTR_ORDER = (
    "公称尺寸",
    "规格",
    "长度",
    "结构规格",
    "角度",
    "灭火剂类型",
    "额定容量",
    "适配螺纹",
    "适配螺栓性能等级",
    "性能/等级",
    "材质",
    "表面处理",
    "接口/结构",
    "用途",
)
_PACKAGING_OR_BRAND = {"包装", "品牌"}

_EXTINGUISHER_AGENT_PATTERNS = (
    ("二氧化碳", re.compile(r"二氧化碳|co2", re.I)),
    ("干粉", re.compile(r"干粉", re.I)),
    ("泡沫", re.compile(r"泡沫", re.I)),
    ("水基", re.compile(r"水基", re.I)),
)
_CAPACITY_RE = re.compile(r"(?i)(\d+(?:\.\d+)?)\s*(kg|千克|l|升)")
_PPR_SIZE_RE = re.compile(r"(?i)ppr\s*(?:φ|ф|ø|dn)?\s*(\d+(?:\.\d+)?)(?:\s*/\s*(\d+(?:\.\d+)?))?")
_PPR_ANGLE_RE = re.compile(r"(?i)(\d+(?:\.\d+)?)\s*(?:度|°)")
_HOSE_LENGTH_RE = re.compile(r"(?i)(\d+(?:\.\d+)?)\s*(m|米)")
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
_DIGIT_RE = re.compile(r"\d")


def _canonical_family(family: str, raw_name: str) -> tuple[str, str]:
    """Apply only reviewed semantic aliases, retaining their provenance."""
    if family in {"平弹垫", "平垫弹垫", "平垫与弹垫"}:
        return "弹簧垫圈与平垫圈组合", "v3_semantic_alias_rule"
    # A generic ``螺丝`` remains generic even when it contains dimensions.
    return family, "v2_rule" if family else "unresolved"


def _norm_number(value: str) -> str:
    return _SPACE_RE.sub("", value).replace("．", ".").upper()


def _extract_v3_attributes(raw_name: str, family: str, base: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Return family-aware attributes and parsing quality flags."""
    text = _canonical_text(raw_name)
    attributes = dict(base)
    flags: list[str] = []

    if family == "弹簧垫圈与平垫圈组合":
        size = attributes.pop("规格", "")
        if size:
            attributes["适配螺纹"] = size
        grade = attributes.pop("性能/等级", "")
        if grade:
            attributes["适配螺栓性能等级"] = grade
        if not attributes.get("适配螺纹"):
            flags.append("missing_washer_thread_size")

    if family.startswith("PPR"):
        match = _PPR_SIZE_RE.search(text)
        if match:
            attributes["公称尺寸"] = _norm_number(match.group(1))
            # For reducing tees the second number is part of the size, not an
            # elbow angle.  Keep it in the original specification as evidence.
            if match.group(2) and family != "PPR弯头" and family != "PPR内丝弯头":
                attributes["规格"] = f"{_norm_number(match.group(1))}/{_norm_number(match.group(2))}"
            elif match.group(2):
                attributes["规格"] = f"{_norm_number(match.group(1))}/{_norm_number(match.group(2))}"
        if family in {"PPR弯头", "PPR内丝弯头"}:
            angle = _PPR_ANGLE_RE.search(text)
            if angle:
                attributes["角度"] = _norm_number(angle.group(1)) + "°"
            elif "/" in text and not attributes.get("角度"):
                # Slash without a degree marker is ambiguous (angle vs size).
                flags.append("ambiguous_ppr_slash")

    if family == "高压胶管":
        length_matches = list(_HOSE_LENGTH_RE.finditer(text))
        if length_matches:
            attributes["长度"] = _norm_number(length_matches[-1].group(1)) + "M"
        else:
            flags.append("missing_hose_length")
        # Keep the construction token separate from the cut length.  The
        # source uses forms such as 36*2层-1寸-7.5m and 52*2层-38-50m.
        tail = re.sub(r"(?i)^.*?高压胶管", "", text)
        tail = _HOSE_LENGTH_RE.sub("", tail).strip(" -—")
        parts = [part.strip() for part in re.split(r"[-—]", tail) if part.strip()]
        if parts:
            if len(parts) >= 2:
                # “36*2层-1寸” places construction before bore; “50-2”
                # places bore before layer count.  Preserve both tokens and
                # avoid forcing a false semantic interpretation.
                if any(marker in parts[0] for marker in ("*", "x", "层")):
                    attributes["结构规格"] = parts[0]
                    attributes["公称尺寸"] = parts[1]
                else:
                    attributes["公称尺寸"] = parts[0]
                    attributes["结构规格"] = parts[1]
            else:
                attributes["结构规格"] = parts[0]

    if family == "灭火器":
        for label, pattern in _EXTINGUISHER_AGENT_PATTERNS:
            if pattern.search(text):
                attributes["灭火剂类型"] = label
                break
        capacity = _CAPACITY_RE.search(text)
        if capacity:
            attributes["额定容量"] = _norm_number(capacity.group(1)) + capacity.group(2).upper().replace("千克", "KG").replace("升", "L")
        if not attributes.get("灭火剂类型") or not attributes.get("额定容量"):
            flags.append("missing_extinguisher_agent_or_capacity")

    return attributes, sorted(set(flags))


def _technical_variant_key(attributes: dict[str, str]) -> str:
    values = [
        f"{key}={attributes[key]}"
        for key in _V3_ATTR_ORDER
        if key not in _PACKAGING_OR_BRAND and attributes.get(key)
    ]
    return "|".join(values) or "(无可识别规格)"


def _uom_quality(members: list["DiscoveryV3Row"], family: str) -> dict[str, Any]:
    policy = _FAMILY_UOM_POLICY.get(family, _DEFAULT_DISCRETE_UOM_POLICY)
    raw_uoms = sorted({row.raw_uom for row in members if row.raw_uom})
    normalized_uoms = sorted({row.normalized_uom for row in members if row.normalized_uom})
    invalid = sorted({uom for uom in normalized_uoms if uom not in policy["accepted"]})
    by_name: dict[str, set[str]] = defaultdict(set)
    for row in members:
        if row.normalized_uom:
            by_name[row.raw_name].add(row.normalized_uom)
    same_name_conflict = any(len(values) > 1 for values in by_name.values())
    if not normalized_uoms:
        status = "missing"
    elif invalid or same_name_conflict:
        status = "conflict"
    elif len(normalized_uoms) > 1:
        status = "normalized_alias"
    else:
        status = "trusted"
    counts = Counter(row.normalized_uom for row in members if row.normalized_uom)
    return {
        "raw_uoms": raw_uoms,
        "normalized_uoms": normalized_uoms,
        "mode_uom": counts.most_common(1)[0][0] if counts else "",
        "preferred_uom": policy["preferred"],
        "accepted_normalized_uoms": sorted(policy["accepted"]),
        "invalid_source_uoms": invalid,
        "invalid_source_uom_count": sum(1 for row in members if row.normalized_uom in invalid),
        "same_name_conflict": same_name_conflict,
        "status": status,
        "note": "推荐单位来自施工采购口径；历史单位只作证据，未被静默改写。",
    }


def _frequency_quadrant(dates: int, variants: int) -> str:
    if dates >= 4 and variants > 1:
        return "high_repeat_multi_spec"
    if dates >= 4:
        return "high_repeat_single_spec"
    if variants > 1:
        return "low_repeat_multi_spec"
    return "one_off_or_low_repeat"


def _row_quality(row: "DiscoveryV3Row") -> list[str]:
    flags = list(row.v2_row.flags)
    flags.extend(row.attribute_flags)
    if row.family_confidence == "lexical_candidate" and _DIGIT_RE.search(row.family_candidate):
        flags.append("digit_contaminated_family_candidate")
    if row.qty is None or row.qty <= 0:
        flags.append("quantity_not_usable")
    if row.market_unit_price is None or row.market_unit_price < 0:
        flags.append("price_not_observed")
    return sorted(set(flags))


@dataclass(frozen=True)
class DiscoveryV3Row:
    source_row: int
    purchase_date: str
    raw_name: str
    qty: float | None
    raw_uom: str
    normalized_uom: str
    procedure_sequence: str
    market_unit_price: float | None
    source_family_candidate: str
    family_candidate: str
    family_confidence: str
    family_rule_source: str
    attributes: dict[str, str]
    attribute_flags: tuple[str, ...]
    technical_variant_key: str
    v2_row: DiscoveryRow


def convert_rows_v3(rows: list[DiscoveryRow]) -> list[DiscoveryV3Row]:
    output: list[DiscoveryV3Row] = []
    for source in rows:
        source_family, confidence = _classify_family(source.raw_name)
        family, rule_source = _canonical_family(source_family, source.raw_name)
        base = _extract_attributes(source.raw_name, family)
        attrs, attr_flags = _extract_v3_attributes(source.raw_name, family, base)
        output.append(DiscoveryV3Row(
            source_row=source.source_row,
            purchase_date=source.purchase_date,
            raw_name=source.raw_name,
            qty=source.qty,
            raw_uom=source.raw_uom,
            normalized_uom=source.normalized_uom or normalize_uom(source.raw_uom),
            procedure_sequence=source.procedure_sequence,
            market_unit_price=source.market_unit_price,
            source_family_candidate=source_family,
            family_candidate=family,
            family_confidence=confidence,
            family_rule_source=rule_source,
            attributes=attrs,
            attribute_flags=tuple(attr_flags),
            technical_variant_key=_technical_variant_key(attrs),
            v2_row=source,
        ))
    return output


def _cluster_id(family: str, source_rows: Iterable[int]) -> str:
    payload = json.dumps([family, sorted(source_rows)], ensure_ascii=False, separators=(",", ":"))
    return f"PF3-{min(source_rows):04d}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:8].upper()}"


def build_clusters_v3(rows: list[DiscoveryV3Row]) -> list[dict[str, Any]]:
    grouped: dict[str, list[DiscoveryV3Row]] = defaultdict(list)
    for row in rows:
        grouped[row.family_candidate].append(row)
    output: list[dict[str, Any]] = []
    for family, members in sorted(grouped.items(), key=lambda item: min(row.source_row for row in item[1])):
        confidence_values = {row.family_confidence for row in members}
        confidence = "explicit" if confidence_values == {"explicit"} else sorted(confidence_values)[0] if len(confidence_values) == 1 else "mixed_rule_confidence"
        variant_keys = list(dict.fromkeys(row.technical_variant_key for row in members))
        raw_names = list(dict.fromkeys(row.raw_name for row in members))
        by_variant: dict[str, list[DiscoveryV3Row]] = defaultdict(list)
        for row in members:
            by_variant[row.technical_variant_key].append(row)
        alias_groups: list[dict[str, Any]] = []
        for key, variant_members in by_variant.items():
            names = list(dict.fromkeys(row.raw_name for row in variant_members))
            if len(names) > 1:
                alias_groups.append({
                    "technical_variant_key": key,
                    "raw_names": names,
                    "source_rows": [row.source_row for row in variant_members],
                    "status": "同规格不同叫法/待确认",
                })
        dates = {row.purchase_date for row in members}
        sessions = {(row.purchase_date, row.procedure_sequence) for row in members}
        event_keys = {(row.purchase_date, row.procedure_sequence, row.technical_variant_key) for row in members}
        qty_by_uom: dict[str, float] = defaultdict(float)
        observed_value = 0.0
        priced_rows = 0
        for row in members:
            if row.qty is not None:
                qty_by_uom[row.normalized_uom or "(缺失)"] += row.qty
            if row.qty is not None and row.market_unit_price is not None and row.market_unit_price >= 0:
                observed_value += row.qty * row.market_unit_price
                priced_rows += 1
        uom = _uom_quality(members, family)
        quality_flags = sorted({flag for row in members for flag in _row_quality(row)})
        blocking_flags = sorted({
            flag for flag in quality_flags
            if flag in {"blocked_specific_item", "service_or_logistics", "bundled_or_vague", "quantity_not_usable"}
        })
        review_flags = set(quality_flags) - {"price_not_observed"}
        if confidence in {"blocked", "unresolved"}:
            publish_gate = "blocked"
        elif confidence != "explicit" or uom["status"] in {"conflict", "missing"} or review_flags:
            publish_gate = "review_required"
        else:
            publish_gate = "rule_ready_for_review"
        review_reasons: list[str] = []
        if confidence != "explicit":
            review_reasons.append("族规则不是显式规则")
        if uom["status"] in {"conflict", "missing"}:
            review_reasons.append("历史单位与推荐单位口径冲突或缺失")
        if "price_not_observed" in quality_flags:
            review_reasons.append("历史行未观察到价格（不阻断模板复核）")
        if "quantity_not_usable" in quality_flags:
            review_reasons.append("数量缺失或无效")
        review_reasons.extend(flag for flag in quality_flags if flag not in {"price_not_observed", "quantity_not_usable"})
        attribute_coverage = round(sum(bool(row.attributes) for row in members) / len(members), 6) if members else 0.0
        quadrant = _frequency_quadrant(len(dates), len(variant_keys))
        score = math.log1p(len(event_keys)) * (1 + 0.5 * math.log1p(max(0, len(variant_keys) - 1)))
        output.append({
            "cluster_id": _cluster_id(family, [row.source_row for row in members]),
            "standard_type_candidate": family,
            "family_confidence": confidence,
            "family_rule_sources": sorted({row.family_rule_source for row in members}),
            "source_family_candidates": sorted({row.source_family_candidate for row in members}),
            "publish_gate": publish_gate,
            "review_status": "禁止自动发布" if publish_gate != "rule_ready_for_review" else "可进入人工规则确认",
            "review_reasons": sorted(set(review_reasons)),
            "source_rows": [row.source_row for row in members],
            "raw_names": raw_names,
            "line_count": len(members),
            "raw_name_count": len(raw_names),
            "distinct_event_count_approx": len(event_keys),
            "active_purchase_date_count": len(dates),
            "purchase_session_count": len(sessions),
            "repeat_line_count": len(members) - len(event_keys),
            "variant_count": len(variant_keys) if variant_keys != ["(无可识别规格)"] else 1,
            "variant_keys": variant_keys,
            "alias_candidate_group_count": len(alias_groups),
            "alias_candidate_groups": alias_groups,
            "frequency_quadrant": quadrant,
            "frequency_metric_note": "频次同时保留行数、日期数、日期+工序会话数和规格事件数；未将任一指标冒充真实采购单数。",
            "attributes_observed": {
                attr: sorted({row.attributes[attr] for row in members if row.attributes.get(attr)})
                for attr in _V3_ATTR_ORDER
                if any(row.attributes.get(attr) for row in members)
            },
            "attribute_coverage": attribute_coverage,
            "attribute_quality_flags": quality_flags,
            "uom_quality": uom,
            "quantity_by_uom": dict(sorted(qty_by_uom.items())),
            "priced_line_count": priced_rows,
            "price_evidence": "usable_for_comparison" if priced_rows == len(members) and uom["status"] in {"trusted", "normalized_alias"} else "observed_only",
            "market_value_sum_observed": round(observed_value, 6),
            "source_flags": sorted({flag for row in members for flag in row.v2_row.flags}),
            "blocking_flags": blocking_flags,
            "integration_priority_score": round(score, 6),
            "no_auto_publish": True,
        })
    ranked = sorted(output, key=lambda row: (-row["integration_priority_score"], -row["distinct_event_count_approx"], row["cluster_id"]))
    frequency = sorted(output, key=lambda row: (-row["distinct_event_count_approx"], -row["active_purchase_date_count"], -row["line_count"], row["cluster_id"]))
    frequency_ranks = {row["cluster_id"]: index for index, row in enumerate(frequency, start=1)}
    for index, row in enumerate(ranked, start=1):
        row["integration_rank"] = index
        row["frequency_rank"] = frequency_ranks[row["cluster_id"]]
    return ranked


def _semantic_block_keys(cluster: dict[str, Any]) -> set[str]:
    text = cluster["standard_type_candidate"]
    keys = {text[:2], text[-2:]}
    for field in ("接口/结构", "用途", "灭火剂类型", "材质"):
        for value in cluster.get("attributes_observed", {}).get(field, []):
            chinese = "".join(_CHINESE_RE.findall(value))
            if len(chinese) >= 2:
                keys.add(chinese[:2])
    return {key for key in keys if key}


def build_family_review_candidates_v3(clusters: list[dict[str, Any]], *, limit: int = 500) -> list[dict[str, Any]]:
    blocks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cluster in clusters:
        for key in _semantic_block_keys(cluster):
            blocks[key].append(cluster)
    seen: set[tuple[str, str]] = set()
    candidates: list[dict[str, Any]] = []
    for block in blocks.values():
        for index, left in enumerate(block):
            for right in block[index + 1:]:
                pair = tuple(sorted((left["cluster_id"], right["cluster_id"])))
                if pair in seen or left["standard_type_candidate"] == right["standard_type_candidate"]:
                    continue
                seen.add(pair)
                similarity = difflib.SequenceMatcher(None, left["standard_type_candidate"], right["standard_type_candidate"]).ratio()
                shared = sorted(_semantic_block_keys(left) & _semantic_block_keys(right))
                if similarity < 0.55 and not shared:
                    continue
                candidates.append({
                    "left_cluster_id": left["cluster_id"],
                    "right_cluster_id": right["cluster_id"],
                    "similarity": round(similarity, 6),
                    "shared_semantic_blocks": shared,
                    "left_type": left["standard_type_candidate"],
                    "right_type": right["standard_type_candidate"],
                    "left_rows": left["source_rows"],
                    "right_rows": right["source_rows"],
                    "decision": "人工复核，不自动合并",
                    "reason": "语义阻塞仅用于发现可能同族；仍需核对结构、用途、GPC范围、单位和价格影响。",
                })
    return sorted(candidates, key=lambda row: (-row["similarity"], row["left_cluster_id"], row["right_cluster_id"]))[:limit]


def _row_json(row: DiscoveryV3Row) -> dict[str, Any]:
    value = {
        "source_row": row.source_row,
        "purchase_date": row.purchase_date,
        "raw_name": row.raw_name,
        "qty": row.qty,
        "raw_uom": row.raw_uom,
        "normalized_uom": row.normalized_uom,
        "procedure_sequence": row.procedure_sequence,
        "market_unit_price": row.market_unit_price,
        "source_family_candidate": row.source_family_candidate,
        "family_candidate": row.family_candidate,
        "family_confidence": row.family_confidence,
        "family_rule_source": row.family_rule_source,
        "attributes": row.attributes,
        "attribute_flags": list(row.attribute_flags),
        "technical_variant_key": row.technical_variant_key,
        "row_quality_flags": _row_quality(row),
    }
    return value


def discover_v3(source_path: Path = DEFAULT_SOURCE_PATH, output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict[str, Any]:
    source_rows = read_source_rows(source_path)
    rows = convert_rows_v3(source_rows)
    clusters = build_clusters_v3(rows)
    review_candidates = build_family_review_candidates_v3(clusters)
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
    candidate_rows = [row for row in clusters if row["family_confidence"] != "unresolved"]
    ready_rows = [row for row in clusters if row["publish_gate"] == "rule_ready_for_review"]
    uom_conflicts = [row for row in clusters if row["uom_quality"]["status"] == "conflict"]
    summary = {
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(Path(source_path).expanduser().resolve()),
        "source_sheet": "实际采购清单",
        "source_row_count": len(rows),
        "unique_raw_name_count": len({row.raw_name for row in rows}),
        "cluster_count": len(clusters),
        "candidate_cluster_count": len(candidate_rows),
        "candidate_coverage_percent": round(100 * sum(row["line_count"] for row in candidate_rows) / len(rows), 2),
        "rule_ready_for_review_cluster_count": len(ready_rows),
        "rule_ready_for_review_line_coverage_percent": round(100 * sum(row["line_count"] for row in ready_rows) / len(rows), 2),
        "review_required_cluster_count": sum(row["publish_gate"] == "review_required" for row in clusters),
        "blocked_cluster_count": sum(row["publish_gate"] == "blocked" for row in clusters),
        "multi_spec_candidate_count": sum(row["variant_count"] > 1 for row in candidate_rows),
        "alias_candidate_group_count": sum(row["alias_candidate_group_count"] for row in candidate_rows),
        "uom_conflict_cluster_count": len(uom_conflicts),
        "uom_trusted_cluster_count": sum(row["uom_quality"]["status"] in {"trusted", "normalized_alias"} for row in clusters),
        "uom_policy_invalid_source_uom_count": sum(row["uom_quality"]["invalid_source_uom_count"] for row in clusters),
        "missing_or_invalid_quantity_line_count": sum("quantity_not_usable" in _row_quality(row) for row in rows),
        "priced_line_count": sum(row.market_unit_price is not None and row.market_unit_price >= 0 for row in rows),
        "frequency_quadrant_counts": dict(Counter(row["frequency_quadrant"] for row in clusters)),
        "fuzzy_review_candidate_count": len(review_candidates),
        "writes_erpnext": False,
        "notes": [
            "candidate_coverage_percent只表示有族假设，不表示已验证或可发布。",
            "rule_ready_for_review仍需人工确认，不等于自动发布；本版本没有auto_publish路径。",
            "历史单位、数量和价格保留为证据；推荐单位来自施工采购模板口径。",
            "高压胶管、PPR弯头、灭火器和垫圈采用族级解析，避免通用正则吞掉关键规格。",
        ],
    }
    (output_root / "discovery-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_root / "quality-audit.json").write_text(json.dumps({
        "version": VERSION,
        "uom_conflict_clusters": [row["cluster_id"] for row in uom_conflicts],
        "high_repeat_multi_spec": [row["cluster_id"] for row in clusters if row["frequency_quadrant"] == "high_repeat_multi_spec"],
        "high_repeat_single_spec": [row["cluster_id"] for row in clusters if row["frequency_quadrant"] == "high_repeat_single_spec"],
        "low_repeat_multi_spec": [row["cluster_id"] for row in clusters if row["frequency_quadrant"] == "low_repeat_multi_spec"],
        "unresolved_or_blocked": [row["cluster_id"] for row in clusters if row["publish_gate"] == "blocked"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"summary": summary, "rows": rows, "clusters": clusters, "fuzzy_review_candidates": review_candidates, "output_root": str(output_root)}


__all__ = [
    "DEFAULT_OUTPUT_ROOT",
    "DiscoveryV3Row",
    "VERSION",
    "build_clusters_v3",
    "build_family_review_candidates_v3",
    "convert_rows_v3",
    "discover_v3",
]
