"""Fourth-pass procurement-family discovery with separated review axes.

v0.3 proved that family parsing and source-data quality cannot share one gate:
an otherwise useful family such as ``高压胶管`` can have a good template while
old rows still contain mixed units.  v0.4 keeps v0.3's deterministic parsers
and evidence, but reports three independent decisions:

* ``family_template_status`` -- whether a family rule is ready for human
  template review;
* ``source_data_quality`` -- whether historical rows are safe for quantities
  and price aggregation; and
* ``publication_readiness`` -- whether the family may proceed to a guarded
  publication review (never an automatic publish).

The analysis remains read-only and never writes ERPNext.
"""

from __future__ import annotations

from collections import Counter
import difflib
import json
import re
from pathlib import Path
from typing import Any

from .procurement_frequency_discovery import DEFAULT_SOURCE_PATH, read_source_rows
from .procurement_frequency_discovery_v0_3 import (
    DEFAULT_OUTPUT_ROOT as V3_OUTPUT_ROOT,
    _FAMILY_UOM_POLICY,
    _semantic_block_keys,
    _row_quality,
    build_clusters_v3,
    convert_rows_v3,
)


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = ROOT / ".runtime" / "material-master" / "frequency-discovery-v0.4"
VERSION = "procurement-frequency-discovery-v0.4"

_STRUCTURE_TOKENS = {
    "弯头", "接头", "内丝", "外丝", "直通", "三通", "四通", "法兰",
    "红模板", "黑模板", "高压", "低压", "干粉", "二氧化碳", "泡沫", "水基",
}
_NUMBER_RE = re.compile(r"(?i)(?:\d+(?:\.\d+)?|m\d+|dn\d+|φ\s*\d+)")


def _uom_quality_v4(cluster: dict[str, Any]) -> dict[str, Any]:
    """Make unknown-family units explicitly undefined instead of defaulting to 件."""
    family = cluster["standard_type_candidate"]
    quality = dict(cluster["uom_quality"])
    if family in _FAMILY_UOM_POLICY:
        quality["policy_status"] = "defined"
        return quality

    normalized = sorted(set(quality.get("normalized_uoms") or []))
    quality.update({
        "preferred_uom": "",
        "accepted_normalized_uoms": [],
        "invalid_source_uoms": [],
        "invalid_source_uom_count": 0,
        "policy_status": "missing",
        "status": "policy_missing" if normalized else "missing",
        "note": "尚未建立该物料族的单位策略；不再默认推荐“件”。历史单位仅作来源证据。",
    })
    return quality


def _family_template_status(cluster: dict[str, Any]) -> str:
    confidence = cluster["family_confidence"]
    if confidence in {"blocked", "unresolved"}:
        return "blocked"
    if confidence == "explicit":
        return "ready_for_review" if not cluster["attribute_quality_flags"] else "review_required"
    if confidence == "mixed_rule_confidence":
        return "review_required"
    return "candidate"


def _source_data_quality(cluster: dict[str, Any], uom: dict[str, Any]) -> str:
    blocking = set(cluster.get("blocking_flags") or [])
    if blocking & {"blocked_specific_item", "service_or_logistics", "bundled_or_vague", "quantity_not_usable"}:
        return "blocked"
    if uom.get("status") in {"conflict", "missing", "policy_missing"}:
        return "review_required"
    if "price_not_observed" in cluster.get("attribute_quality_flags", []):
        return "ready_with_price_gap"
    return "ready"


def _publication_readiness(family_status: str, source_status: str) -> str:
    if family_status == "blocked" or source_status == "blocked":
        return "blocked"
    if family_status != "ready_for_review" or source_status not in {"ready", "ready_with_price_gap"}:
        return "review_required"
    return "ready_for_review"


def _risk_tier(left: str, right: str) -> str:
    """Classify fuzzy pairs; numeric/structural differences require priority review."""
    left_tokens = set(_NUMBER_RE.findall(left.upper()))
    right_tokens = set(_NUMBER_RE.findall(right.upper()))
    left_struct = {token for token in _STRUCTURE_TOKENS if token in left}
    right_struct = {token for token in _STRUCTURE_TOKENS if token in right}
    if left_tokens != right_tokens or left_struct != right_struct:
        return "structure_sensitive"
    return "semantic_near"


def _build_fuzzy_candidates_v4(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the complete, explicitly non-merging fuzzy review queue."""
    blocks: dict[str, list[dict[str, Any]]] = {}
    for cluster in clusters:
        for key in _semantic_block_keys(cluster):
            blocks.setdefault(key, []).append(cluster)
    seen: set[tuple[str, str]] = set()
    candidates: list[dict[str, Any]] = []
    for block in blocks.values():
        for index, left in enumerate(block):
            for right in block[index + 1:]:
                pair = tuple(sorted((left["cluster_id"], right["cluster_id"])))
                if pair in seen or left["standard_type_candidate"] == right["standard_type_candidate"]:
                    continue
                seen.add(pair)
                similarity = difflib.SequenceMatcher(
                    None, left["standard_type_candidate"], right["standard_type_candidate"]
                ).ratio()
                shared = sorted(_semantic_block_keys(left) & _semantic_block_keys(right))
                if similarity < 0.55 and not shared:
                    continue
                tier = _risk_tier(left["standard_type_candidate"], right["standard_type_candidate"])
                candidates.append({
                    "left_cluster_id": left["cluster_id"],
                    "right_cluster_id": right["cluster_id"],
                    "similarity": round(similarity, 6),
                    "shared_semantic_blocks": shared,
                    "left_type": left["standard_type_candidate"],
                    "right_type": right["standard_type_candidate"],
                    "left_rows": left["source_rows"],
                    "right_rows": right["source_rows"],
                    "risk_tier": tier,
                    "decision": "人工复核，不自动合并",
                    "reason": "仅用于发现相似族；必须核对结构、用途、GPC范围、单位和价格影响。",
                })
    return sorted(
        candidates,
        key=lambda row: (
            0 if row["risk_tier"] == "structure_sensitive" else 1,
            -row["similarity"],
            row["left_cluster_id"],
            row["right_cluster_id"],
        ),
    )


def _enrich_clusters_v4(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for source in clusters:
        cluster = dict(source)
        # Blocking flags must be reflected in the gate, not merely displayed.
        flags = set(cluster.get("attribute_quality_flags") or [])
        for flag in cluster.get("source_flags") or []:
            flags.add(flag)
        cluster["blocking_flags"] = sorted({
            flag for flag in flags
            if flag in {"blocked_specific_item", "service_or_logistics", "bundled_or_vague", "quantity_not_usable"}
        })
        uom = _uom_quality_v4(cluster)
        family_status = _family_template_status(cluster)
        source_status = _source_data_quality(cluster, uom)
        publication = _publication_readiness(family_status, source_status)
        cluster["uom_quality"] = uom
        cluster["family_template_status"] = family_status
        cluster["source_data_quality"] = source_status
        cluster["publication_readiness"] = publication
        # Keep v3's publish_gate for consumers, but make its value correct.
        cluster["publish_gate"] = publication
        cluster["review_status"] = "禁止自动发布" if publication != "ready_for_review" else "可进入人工规则确认"
        if uom.get("status") in {"conflict", "missing", "policy_missing"}:
            reasons = set(cluster.get("review_reasons") or [])
            reasons.add("族模板与历史单位质量分开审核")
            cluster["review_reasons"] = sorted(reasons)
        if cluster.get("blocking_flags"):
            reasons = set(cluster.get("review_reasons") or [])
            reasons.add("存在服务、笼统、数量或特定物料阻断标记")
            cluster["review_reasons"] = sorted(reasons)
        if cluster.get("price_evidence") == "usable_for_comparison" and uom.get("status") == "policy_missing":
            cluster["price_evidence"] = "observed_only"
        output.append(cluster)
    return output


def _queue_entry(cluster: dict[str, Any], queue: str, reason: str) -> dict[str, Any]:
    return {
        "cluster_id": cluster["cluster_id"],
        "standard_type_candidate": cluster["standard_type_candidate"],
        "queue": queue,
        "reason": reason,
        "line_count": cluster["line_count"],
        "variant_count": cluster["variant_count"],
        "active_purchase_date_count": cluster["active_purchase_date_count"],
        "family_template_status": cluster["family_template_status"],
        "source_data_quality": cluster["source_data_quality"],
        "publication_readiness": cluster["publication_readiness"],
        "integration_rank": cluster.get("integration_rank"),
    }


def build_review_queues_v4(clusters: list[dict[str, Any]]) -> dict[str, Any]:
    high_multi = [c for c in clusters if c["frequency_quadrant"] == "high_repeat_multi_spec"]
    explicit_multi = [c for c in high_multi if c["family_confidence"] in {"explicit", "mixed_rule_confidence"}]
    lexical_multi = [c for c in high_multi if c["family_confidence"] == "lexical_candidate"]
    high_single = [c for c in clusters if c["frequency_quadrant"] == "high_repeat_single_spec"]
    deferred = [c for c in clusters if c["frequency_quadrant"] == "one_off_or_low_repeat"]
    blocked = [c for c in clusters if c["publication_readiness"] == "blocked"]
    return {
        "template_review_priority": [
            _queue_entry(c, "high_repeat_multi_spec_explicit", "先确认族模板属性一次，再处理历史行单位")
            for c in explicit_multi
        ],
        "lexical_high_repeat_review": [
            _queue_entry(c, "high_repeat_multi_spec_lexical", "先确认族归类与别名，暂不自动合并")
            for c in lexical_multi
        ],
        "high_repeat_single_spec_review": [
            _queue_entry(c, "high_repeat_single_spec", "确认是否值得建立单规格标准类型")
            for c in high_single
        ],
        "deferred_low_repeat": [
            _queue_entry(c, "deferred_low_repeat", "低频或一次性记录，等高频规则沉淀后再处理")
            for c in deferred
        ],
        "blocked": [
            _queue_entry(c, "blocked", "服务、笼统、数量异常或明确阻断项")
            for c in blocked
        ],
    }


def discover_v4(source_path: Path = DEFAULT_SOURCE_PATH, output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict[str, Any]:
    source_rows = read_source_rows(source_path)
    rows = convert_rows_v3(source_rows)
    clusters = _enrich_clusters_v4(build_clusters_v3(rows))
    fuzzy = _build_fuzzy_candidates_v4(clusters)
    queues = build_review_queues_v4(clusters)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "source-rows.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            from .procurement_frequency_discovery_v0_3 import _row_json
            handle.write(json.dumps(_row_json(row), ensure_ascii=False) + "\n")
    with (output_root / "clusters.jsonl").open("w", encoding="utf-8") as handle:
        for cluster in clusters:
            handle.write(json.dumps(cluster, ensure_ascii=False) + "\n")
    with (output_root / "fuzzy-review-candidates.jsonl").open("w", encoding="utf-8") as handle:
        for candidate in fuzzy:
            handle.write(json.dumps(candidate, ensure_ascii=False) + "\n")
    (output_root / "review-queues.json").write_text(json.dumps(queues, ensure_ascii=False, indent=2), encoding="utf-8")

    candidate_rows = [c for c in clusters if c["family_confidence"] != "unresolved"]
    family_ready = [c for c in clusters if c["family_template_status"] == "ready_for_review"]
    publication_ready = [c for c in clusters if c["publication_readiness"] == "ready_for_review"]
    source_blocked = [c for c in clusters if c["source_data_quality"] == "blocked"]
    confidence_lines = {
        confidence: sum(c["line_count"] for c in clusters if c["family_confidence"] == confidence)
        for confidence in sorted({c["family_confidence"] for c in clusters})
    }
    summary = {
        "version": VERSION,
        "source_path": str(Path(source_path).expanduser().resolve()),
        "source_sheet": "实际采购清单",
        "source_row_count": len(rows),
        "unique_raw_name_count": len({row.raw_name for row in rows}),
        "cluster_count": len(clusters),
        "candidate_cluster_count": len(candidate_rows),
        "candidate_coverage_percent": round(100 * sum(c["line_count"] for c in candidate_rows) / len(rows), 2),
        "family_confidence_line_counts": confidence_lines,
        "family_ready_for_review_cluster_count": len(family_ready),
        "family_ready_for_review_line_coverage_percent": round(100 * sum(c["line_count"] for c in family_ready) / len(rows), 2),
        "publication_ready_for_review_cluster_count": len(publication_ready),
        "publication_ready_for_review_line_coverage_percent": round(100 * sum(c["line_count"] for c in publication_ready) / len(rows), 2),
        "source_data_blocked_cluster_count": len(source_blocked),
        "review_required_cluster_count": sum(c["publication_readiness"] == "review_required" for c in clusters),
        "blocked_cluster_count": sum(c["publication_readiness"] == "blocked" for c in clusters),
        "multi_spec_candidate_count": sum(c["variant_count"] > 1 for c in candidate_rows),
        "uom_policy_missing_cluster_count": sum(c["uom_quality"].get("policy_status") == "missing" for c in clusters),
        "uom_conflict_cluster_count": sum(c["uom_quality"]["status"] == "conflict" for c in clusters),
        "missing_or_invalid_quantity_line_count": sum("quantity_not_usable" in _row_quality(row) for row in rows),
        "priced_line_count": sum(row.market_unit_price is not None and row.market_unit_price >= 0 for row in rows),
        "frequency_quadrant_counts": dict(Counter(c["frequency_quadrant"] for c in clusters)),
        "fuzzy_review_candidate_count_total": len(fuzzy),
        "fuzzy_review_candidate_count_exported": len(fuzzy),
        "fuzzy_review_candidate_truncated": False,
        "fuzzy_risk_tier_counts": dict(Counter(c["risk_tier"] for c in fuzzy)),
        "review_queue_counts": {name: len(items) for name, items in queues.items()},
        "writes_erpnext": False,
        "notes": [
            "候选覆盖率只表示有族假设；族模板成熟度、源数据质量和发布准备度分别统计。",
            "未知族不再默认推荐‘件’；没有族级单位策略时为 policy_missing。",
            "服务、笼统、数量异常和特定物料阻断项进入 blocked，不参与标准物料发布。",
            "模糊候选完整导出并标记 structure_sensitive/semantic_near，任何候选均不自动合并。",
            "价格仅在单位策略已定义且历史单位质量可信时可用于比较。",
        ],
    }
    (output_root / "discovery-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_root / "quality-audit.json").write_text(json.dumps({
        "version": VERSION,
        "blocking_clusters": [c["cluster_id"] for c in clusters if c["publication_readiness"] == "blocked"],
        "family_template_ready": [c["cluster_id"] for c in family_ready],
        "publication_ready_for_review": [c["cluster_id"] for c in publication_ready],
        "uom_policy_missing": [c["cluster_id"] for c in clusters if c["uom_quality"].get("policy_status") == "missing"],
        "fuzzy_structure_sensitive_count": sum(c["risk_tier"] == "structure_sensitive" for c in fuzzy),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "summary": summary,
        "rows": rows,
        "clusters": clusters,
        "fuzzy_review_candidates": fuzzy,
        "review_queues": queues,
        "output_root": str(output_root),
    }


__all__ = [
    "DEFAULT_OUTPUT_ROOT",
    "VERSION",
    "build_review_queues_v4",
    "discover_v4",
]
