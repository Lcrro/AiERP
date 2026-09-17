"""Fifth-pass procurement-family discovery with evidence-safe review queues.

v0.5 tightens v0.4 in four places exposed by the second audit:

* attribute parsing flags are separated from historical quantity/price flags;
* unit-policy maturity is separate from source-evidence quality;
* review queues are exhaustive and mutually exclusive;
* every parsed attribute carries source-row evidence and a field confidence.

The source workbook is hashed, outputs are reproducible metadata, and no
ERPNext write is performed.
"""

from __future__ import annotations

from collections import defaultdict, Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from .procurement_frequency_discovery import DEFAULT_SOURCE_PATH, read_source_rows
from .procurement_frequency_discovery_v0_3 import (
    _FAMILY_UOM_POLICY,
    _row_json,
    _row_quality,
    build_clusters_v3,
    convert_rows_v3,
)
from .procurement_frequency_discovery_v0_4 import _build_fuzzy_candidates_v4


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = ROOT / ".runtime" / "material-master" / "frequency-discovery-v0.5"
VERSION = "procurement-frequency-discovery-v0.5"

# These fittings are a known construction-purchasing convention.  They are
# deliberately explicit; paint, generic pipe and unknown families remain
# policy_missing until a template is reviewed.
_FAMILY_UOM_POLICY_V5: dict[str, dict[str, Any]] = dict(_FAMILY_UOM_POLICY)
for _ppr_family in {
    "PPR弯头", "PPR内丝弯头", "PPR内丝直接", "PPR截止阀", "PPR三通",
    "PPR异径三通", "PPR直接", "铝合金快速接头",
}:
    _FAMILY_UOM_POLICY_V5[_ppr_family] = {"preferred": "件", "accepted": {"件", "个", "套"}}

_BLOCKING_FLAGS = {"blocked_specific_item", "service_or_logistics", "bundled_or_vague", "quantity_not_usable"}
_ATTR_FIELDS = {
    "公称尺寸", "规格", "长度", "结构规格", "角度", "灭火剂类型", "额定容量",
    "适配螺纹", "适配螺栓性能等级", "性能/等级", "材质", "表面处理", "接口/结构", "用途",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_flags(rows: list[Any]) -> set[str]:
    flags: set[str] = set()
    for row in rows:
        flags.update(row.v2_row.flags)
        if row.qty is None or row.qty <= 0:
            flags.add("quantity_not_usable")
        if row.market_unit_price is None or row.market_unit_price < 0:
            flags.add("price_not_observed")
    return flags


def _attribute_evidence(rows: list[Any], family: str) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str], list[str]]:
    values: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    parse_flags: set[str] = set()
    for row in rows:
        parse_flags.update(row.attribute_flags)
        for field, value in row.attributes.items():
            if field not in _ATTR_FIELDS or not value:
                continue
            entry = values[field].setdefault(value, {"value": value, "source_rows": [], "raw_names": []})
            entry["source_rows"].append(row.source_row)
            entry["raw_names"].append(row.raw_name)

    evidence: dict[str, list[dict[str, Any]]] = {}
    confidence: dict[str, str] = {}
    for field, field_values in values.items():
        if parse_flags:
            field_confidence = "low"
        elif family == "高压胶管" and field == "长度":
            field_confidence = "high"
        elif family.startswith("PPR") and field in {"公称尺寸", "角度"}:
            field_confidence = "high"
        elif family == "灭火器" and field in {"灭火剂类型", "额定容量"}:
            field_confidence = "high"
        elif family == "弹簧垫圈与平垫圈组合" and field in {"适配螺纹", "适配螺栓性能等级"}:
            field_confidence = "medium"
        else:
            field_confidence = "medium"
        confidence[field] = field_confidence
        entries = []
        for entry in field_values.values():
            entry = dict(entry)
            entry["source_rows"] = sorted(set(entry["source_rows"]))
            entry["raw_names"] = list(dict.fromkeys(entry["raw_names"]))
            entry["confidence"] = field_confidence
            entries.append(entry)
        evidence[field] = sorted(entries, key=lambda item: item["value"])
    return evidence, confidence, sorted(parse_flags)


def _uom_policy(cluster: dict[str, Any]) -> dict[str, Any]:
    family = cluster["standard_type_candidate"]
    policy = _FAMILY_UOM_POLICY_V5.get(family)
    old = dict(cluster["uom_quality"])
    if policy is None:
        normalized = sorted(set(old.get("normalized_uoms") or []))
        old.update({
            "preferred_uom": "",
            "accepted_normalized_uoms": [],
            "invalid_source_uoms": [],
            "invalid_source_uom_count": 0,
            "policy_status": "missing",
            "status": "policy_missing" if normalized else "missing",
            "note": "尚未建立该物料族的单位策略；不默认推荐“件”。历史单位仅作来源证据。",
        })
        return old
    normalized = sorted(set(old.get("normalized_uoms") or []))
    invalid = sorted(value for value in normalized if value not in policy["accepted"])
    counts = Counter(row["normalized_uom"] for row in cluster.get("_member_rows", []) if row.get("normalized_uom"))
    old.update({
        "preferred_uom": policy["preferred"],
        "accepted_normalized_uoms": sorted(policy["accepted"]),
        "invalid_source_uoms": invalid,
        "invalid_source_uom_count": sum(1 for row in cluster.get("_member_rows", []) if row.get("normalized_uom") in invalid),
        "policy_status": "defined",
        "status": "conflict" if invalid or old.get("same_name_conflict") else ("normalized_alias" if len(normalized) > 1 else ("trusted" if normalized else "missing")),
        "mode_uom": counts.most_common(1)[0][0] if counts else old.get("mode_uom", ""),
        "note": "推荐单位来自已确认的族级采购口径；历史单位只作证据，未被静默改写。",
    })
    return old


def _family_template_status(confidence: str, parse_flags: list[str]) -> str:
    if confidence in {"blocked", "unresolved"}:
        return "blocked"
    if confidence == "explicit":
        return "ready_for_review" if not parse_flags else "review_required"
    if confidence == "mixed_rule_confidence":
        return "review_required"
    return "candidate"


def _source_evidence_quality(cluster: dict[str, Any], uom: dict[str, Any], source_flags: set[str]) -> str:
    if source_flags & _BLOCKING_FLAGS:
        return "blocked"
    if uom.get("policy_status") == "missing":
        return "pending_unit_policy"
    if uom.get("status") in {"conflict", "missing"}:
        return "review_required"
    if "price_not_observed" in source_flags:
        return "ready_with_price_gap"
    return "ready"


def _publication_readiness(family_status: str, source_status: str, unit_status: str) -> str:
    if family_status == "blocked" or source_status == "blocked":
        return "blocked"
    if family_status != "ready_for_review" or unit_status != "defined" or source_status not in {"ready", "ready_with_price_gap"}:
        return "review_required"
    return "ready_for_review"


def _enrich_clusters_v5(clusters: list[dict[str, Any]], rows: list[Any]) -> list[dict[str, Any]]:
    by_source = {row.source_row: row for row in rows}
    output: list[dict[str, Any]] = []
    for source in clusters:
        cluster = dict(source)
        members = [by_source[row_id] for row_id in cluster["source_rows"] if row_id in by_source]
        cluster["_member_rows"] = [
            {"source_row": row.source_row, "normalized_uom": row.normalized_uom}
            for row in members
        ]
        evidence, field_confidence, parse_flags = _attribute_evidence(members, cluster["standard_type_candidate"])
        source_flags = _source_flags(members)
        uom = _uom_policy(cluster)
        family_status = _family_template_status(cluster["family_confidence"], parse_flags)
        source_status = _source_evidence_quality(cluster, uom, source_flags)
        publication = _publication_readiness(family_status, source_status, uom.get("policy_status", "missing"))
        cluster["attribute_evidence"] = evidence
        cluster["attribute_field_confidence"] = field_confidence
        cluster["attribute_parse_flags"] = parse_flags
        cluster["source_quality_flags"] = sorted(source_flags)
        cluster["blocking_flags"] = sorted(source_flags & _BLOCKING_FLAGS)
        cluster["uom_quality"] = uom
        cluster["family_template_status"] = family_status
        cluster["unit_policy_status"] = uom.get("policy_status", "missing")
        cluster["source_evidence_quality"] = source_status
        cluster["publication_readiness"] = publication
        cluster["publish_gate"] = publication
        cluster["review_status"] = "禁止自动发布" if publication != "ready_for_review" else "可进入人工规则确认"
        reasons = set(cluster.get("review_reasons") or [])
        if parse_flags:
            reasons.add("存在属性解析缺失或歧义")
        if uom.get("policy_status") == "missing":
            reasons.add("尚未定义族级单位策略")
        if uom.get("status") in {"conflict", "missing"}:
            reasons.add("历史单位与族级单位口径冲突或缺失")
        if "price_not_observed" in source_flags:
            reasons.add("历史行未观察到价格（不阻断族模板复核）")
        if cluster["blocking_flags"]:
            reasons.add("存在服务、笼统、数量或特定物料阻断标记")
        cluster["review_reasons"] = sorted(reasons)
        cluster["price_evidence"] = (
            "usable_for_comparison"
            if (
                uom.get("policy_status") == "defined"
                and uom.get("status") in {"trusted", "normalized_alias"}
                and "quantity_not_usable" not in source_flags
                and "price_not_observed" not in source_flags
            )
            else "observed_only"
        )
        cluster.pop("_member_rows", None)
        output.append(cluster)
    return output


def _queues_v5(clusters: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Build mutually exclusive queues with blocked items taking precedence."""
    blocked = [c for c in clusters if c["publication_readiness"] == "blocked"]
    blocked_ids = {c["cluster_id"] for c in blocked}
    remaining = [c for c in clusters if c["cluster_id"] not in blocked_ids]

    def take(predicate: Any) -> list[dict[str, Any]]:
        selected = [c for c in remaining if predicate(c)]
        selected_ids = {c["cluster_id"] for c in selected}
        remaining[:] = [c for c in remaining if c["cluster_id"] not in selected_ids]
        return selected

    explicit_multi = take(lambda c: c["frequency_quadrant"] == "high_repeat_multi_spec" and c["family_confidence"] in {"explicit", "mixed_rule_confidence"})
    lexical_multi = take(lambda c: c["frequency_quadrant"] == "high_repeat_multi_spec")
    high_single = take(lambda c: c["frequency_quadrant"] == "high_repeat_single_spec")
    low_multi = take(lambda c: c["frequency_quadrant"] == "low_repeat_multi_spec")
    deferred = take(lambda c: True)

    def entries(items: list[dict[str, Any]], queue: str, reason: str) -> list[dict[str, Any]]:
        return [{
            "cluster_id": c["cluster_id"],
            "standard_type_candidate": c["standard_type_candidate"],
            "queue": queue,
            "reason": reason,
            "line_count": c["line_count"],
            "variant_count": c["variant_count"],
            "active_purchase_date_count": c["active_purchase_date_count"],
            "family_template_status": c["family_template_status"],
            "unit_policy_status": c["unit_policy_status"],
            "source_evidence_quality": c["source_evidence_quality"],
            "publication_readiness": c["publication_readiness"],
            "integration_rank": c.get("integration_rank"),
        } for c in items]

    return {
        "blocked": entries(blocked, "blocked", "服务、笼统、数量异常或明确阻断项"),
        "template_review_priority": entries(explicit_multi, "high_repeat_multi_spec_explicit", "先确认族模板属性一次，再处理历史行单位"),
        "lexical_high_repeat_review": entries(lexical_multi, "high_repeat_multi_spec_lexical", "先确认族归属与别名，暂不自动合并"),
        "high_repeat_single_spec_review": entries(high_single, "high_repeat_single_spec", "确认是否值得建立单规格标准类型"),
        "low_repeat_multi_spec_review": entries(low_multi, "low_repeat_multi_spec", "保留多规格结构，排在高频族之后复核"),
        "deferred_low_repeat": entries(deferred, "deferred_low_repeat", "低频或一次性记录，等前序规则沉淀后再处理"),
    }


def _fuzzy_v5(clusters: list[dict[str, Any]], queues: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    all_candidates = _build_fuzzy_candidates_v4(clusters)
    priority_ids = {row["cluster_id"] for name in ("template_review_priority", "lexical_high_repeat_review") for row in queues[name]}
    high_ids = priority_ids | {row["cluster_id"] for row in queues["high_repeat_single_spec_review"]}
    for row in all_candidates:
        related_high = row["left_cluster_id"] in high_ids or row["right_cluster_id"] in high_ids
        if row["risk_tier"] == "structure_sensitive":
            row["review_queue"] = "priority_do_not_merge" if related_high else "archive_do_not_merge"
        elif related_high:
            row["review_queue"] = "priority_semantic_review"
        else:
            row["review_queue"] = "archive_low_priority"
    return all_candidates


def discover_v5(source_path: Path = DEFAULT_SOURCE_PATH, output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict[str, Any]:
    source_path = Path(source_path).expanduser().resolve()
    source_rows = read_source_rows(source_path)
    rows = convert_rows_v3(source_rows)
    clusters = _enrich_clusters_v5(build_clusters_v3(rows), rows)
    queues = _queues_v5(clusters)
    fuzzy = _fuzzy_v5(clusters, queues)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "source-rows.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(_row_json(row), ensure_ascii=False) + "\n")
    with (output_root / "clusters.jsonl").open("w", encoding="utf-8") as handle:
        for cluster in clusters:
            handle.write(json.dumps(cluster, ensure_ascii=False) + "\n")
    with (output_root / "fuzzy-review-candidates.jsonl").open("w", encoding="utf-8") as handle:
        for candidate in fuzzy:
            handle.write(json.dumps(candidate, ensure_ascii=False) + "\n")
    (output_root / "review-queues.json").write_text(json.dumps(queues, ensure_ascii=False, indent=2), encoding="utf-8")

    total_lines = len(rows)
    confidence_lines = {
        confidence: sum(c["line_count"] for c in clusters if c["family_confidence"] == confidence)
        for confidence in sorted({c["family_confidence"] for c in clusters})
    }
    family_ready = [c for c in clusters if c["family_template_status"] == "ready_for_review"]
    publication_ready = [c for c in clusters if c["publication_readiness"] == "ready_for_review"]
    summary = {
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path),
        "source_sha256": _sha256(source_path),
        "source_sheet": "实际采购清单",
        "source_row_count": total_lines,
        "unique_raw_name_count": len({row.raw_name for row in rows}),
        "cluster_count": len(clusters),
        "candidate_cluster_count": sum(c["family_confidence"] != "unresolved" for c in clusters),
        "candidate_coverage_percent": round(100 * sum(c["line_count"] for c in clusters if c["family_confidence"] != "unresolved") / total_lines, 2),
        "family_confidence_line_counts": confidence_lines,
        "family_template_ready_for_review_cluster_count": len(family_ready),
        "family_template_ready_for_review_line_coverage_percent": round(100 * sum(c["line_count"] for c in family_ready) / total_lines, 2),
        "publication_ready_for_review_cluster_count": len(publication_ready),
        "publication_ready_for_review_line_coverage_percent": round(100 * sum(c["line_count"] for c in publication_ready) / total_lines, 2),
        "unit_policy_defined_cluster_count": sum(c["unit_policy_status"] == "defined" for c in clusters),
        "unit_policy_missing_cluster_count": sum(c["unit_policy_status"] == "missing" for c in clusters),
        "source_evidence_quality_counts": dict(Counter(c["source_evidence_quality"] for c in clusters)),
        "blocked_cluster_count": sum(c["publication_readiness"] == "blocked" for c in clusters),
        "multi_spec_candidate_count": sum(c["variant_count"] > 1 for c in clusters if c["family_confidence"] != "unresolved"),
        "missing_or_invalid_quantity_line_count": sum("quantity_not_usable" in _row_quality(row) for row in rows),
        "priced_line_count": sum(row.market_unit_price is not None and row.market_unit_price >= 0 for row in rows),
        "frequency_quadrant_counts": dict(Counter(c["frequency_quadrant"] for c in clusters)),
        "review_queue_counts": {name: len(items) for name, items in queues.items()},
        "review_queue_is_exhaustive": sum(len(items) for items in queues.values()) == len(clusters),
        "fuzzy_review_candidate_count_total": len(fuzzy),
        "fuzzy_review_candidate_count_exported": len(fuzzy),
        "fuzzy_review_candidate_truncated": False,
        "fuzzy_review_queue_counts": dict(Counter(row["review_queue"] for row in fuzzy)),
        "writes_erpnext": False,
        "notes": [
            "族模板状态只看属性解析，不被历史价格缺失或数量异常降级。",
            "单位策略未定义单独记为 pending_unit_policy，不默认推荐‘件’。",
            "审核队列互斥且覆盖全部族；阻断项优先，不重复出现在低频暂缓队列。",
            "字段证据保留原始行号和原始物料名；任一模糊候选都不自动合并。",
        ],
    }
    (output_root / "discovery-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_root / "quality-audit.json").write_text(json.dumps({
        "version": VERSION,
        "source_sha256": summary["source_sha256"],
        "queue_is_exhaustive": summary["review_queue_is_exhaustive"],
        "blocking_clusters": [c["cluster_id"] for c in clusters if c["publication_readiness"] == "blocked"],
        "attribute_parse_flag_clusters": [c["cluster_id"] for c in clusters if c["attribute_parse_flags"]],
        "unit_policy_missing": [c["cluster_id"] for c in clusters if c["unit_policy_status"] == "missing"],
        "priority_semantic_fuzzy_count": sum(c["review_queue"] == "priority_semantic_review" for c in fuzzy),
        "structure_sensitive_fuzzy_count": sum(c["risk_tier"] == "structure_sensitive" for c in fuzzy),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "summary": summary,
        "rows": rows,
        "clusters": clusters,
        "review_queues": queues,
        "fuzzy_review_candidates": fuzzy,
        "output_root": str(output_root),
    }


__all__ = ["DEFAULT_OUTPUT_ROOT", "VERSION", "discover_v5"]
