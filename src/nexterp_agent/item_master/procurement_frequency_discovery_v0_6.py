"""Sixth-pass procurement discovery: catalog alignment and family decisions.

v0.5 answers *which* families are frequent.  It intentionally does not answer
whether a family is safe to merge or how a template should be built.  v0.6
adds that review layer without changing the v0.5 parser or making any ERPNext
write.  A decision is a bounded review proposal, never an automatic publish
instruction.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from .procurement_frequency_discovery import DEFAULT_SOURCE_PATH
from .procurement_frequency_discovery_v0_5 import discover_v5


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = ROOT / ".runtime" / "material-master" / "frequency-discovery-v0.6"
VERSION = "procurement-frequency-discovery-v0.6"


# These are deliberately reviewable product-family decisions, not inferred
# GPC mappings.  Existing GPC/Nexterp names are used as targets where known;
# a generic family is explicitly split rather than silently merged.
_FAMILY_DECISIONS: dict[str, dict[str, Any]] = {
    "PPR弯头": {
        "decision": "selector", "canonical_family": "PPR弯头",
        "catalog_match_status": "aligned_to_internal_family",
        "existing_standard_type_candidates": ["PPR弯头"],
        "selector_axes": ["公称尺寸", "角度"],
        "required_attributes": ["公称尺寸", "角度"],
        "descriptor_attributes": ["材质", "接口/结构"], "purchase_only_attributes": ["品牌"],
        "configured_uom": "件", "rationale": "同一弯头族按尺寸和角度选择；内丝结构不能与普通弯头合并。",
    },
    "PPR内丝弯头": {
        "decision": "selector", "canonical_family": "PPR内丝弯头",
        "catalog_match_status": "aligned_to_internal_family",
        "existing_standard_type_candidates": ["PPR内丝弯头"],
        "selector_axes": ["公称尺寸", "角度"], "required_attributes": ["公称尺寸", "角度"],
        "descriptor_attributes": ["材质", "接口/结构"], "purchase_only_attributes": ["品牌"],
        "configured_uom": "件", "rationale": "内丝是结构差异，单独建立选择器。",
    },
    "PPR内丝直接": {
        "decision": "selector", "canonical_family": "PPR内丝直接",
        "catalog_match_status": "aligned_to_internal_family",
        "existing_standard_type_candidates": ["PPR内丝直接"],
        "selector_axes": ["公称尺寸"], "required_attributes": ["公称尺寸"],
        "descriptor_attributes": ["材质", "接口/结构"], "purchase_only_attributes": ["品牌"],
        "configured_uom": "件", "rationale": "内丝结构与普通直接不同，按尺寸选择。",
    },
    "PPR截止阀": {
        "decision": "selector", "canonical_family": "PPR截止阀",
        "catalog_match_status": "aligned_to_internal_family",
        "existing_standard_type_candidates": ["PPR截止阀"],
        "selector_axes": ["公称尺寸"], "required_attributes": ["公称尺寸"],
        "descriptor_attributes": ["材质", "接口/结构"], "purchase_only_attributes": ["品牌"],
        "configured_uom": "件", "rationale": "尺寸影响适配和价格，材质作为描述或采购条件。",
    },
    "PPR管": {
        "decision": "selector", "canonical_family": "PPR管",
        "catalog_match_status": "aligned_to_internal_family",
        "existing_standard_type_candidates": ["PPR管"],
        "selector_axes": ["公称尺寸"], "required_attributes": ["公称尺寸"],
        "descriptor_attributes": ["材质", "规格"], "purchase_only_attributes": ["品牌", "长度"],
        "configured_uom": "米", "rationale": "管径决定适配，采购长度和品牌不应制造目录族。",
    },
    "PPR直接": {
        "decision": "selector", "canonical_family": "PPR直接",
        "catalog_match_status": "aligned_to_internal_family",
        "existing_standard_type_candidates": ["PPR直接"],
        "selector_axes": ["公称尺寸"], "required_attributes": ["公称尺寸"],
        "descriptor_attributes": ["材质", "接口/结构"], "purchase_only_attributes": ["品牌"],
        "configured_uom": "件", "rationale": "同族按管径选择，接口结构保留为描述和校验。",
    },
    "PPR三通": {
        "decision": "selector", "canonical_family": "PPR三通",
        "catalog_match_status": "aligned_to_internal_family",
        "existing_standard_type_candidates": ["PPR三通"],
        "selector_axes": ["公称尺寸", "规格"], "required_attributes": ["公称尺寸"],
        "descriptor_attributes": ["材质", "接口/结构"], "purchase_only_attributes": ["品牌"],
        "configured_uom": "件", "rationale": "三通与异径三通结构不同；在本族内按尺寸选择。",
    },
    "PPR异径三通": {
        "decision": "selector", "canonical_family": "PPR异径三通",
        "catalog_match_status": "aligned_to_internal_family",
        "existing_standard_type_candidates": ["PPR异径三通"],
        "selector_axes": ["规格"], "required_attributes": ["规格"],
        "descriptor_attributes": ["公称尺寸", "材质", "接口/结构"], "purchase_only_attributes": ["品牌"],
        "configured_uom": "件", "rationale": "异径组合尺寸会影响适配和价格，单独选择。",
    },
    "铝合金快速接头": {
        "decision": "selector", "canonical_family": "铝合金快速接头",
        "catalog_match_status": "aligned_to_internal_family",
        "existing_standard_type_candidates": ["铝合金快速接头"],
        "selector_axes": ["规格"], "required_attributes": ["规格"],
        "descriptor_attributes": ["材质"], "purchase_only_attributes": ["品牌"],
        "configured_uom": "件", "rationale": "接口规格决定互换性，铝合金为族约束。",
    },
    "弹簧垫圈与平垫圈组合": {
        "decision": "selector", "canonical_family": "弹簧垫圈与平垫圈组合",
        "catalog_match_status": "aligned_to_internal_family",
        "existing_standard_type_candidates": ["弹簧垫圈与平垫圈组合"],
        "selector_axes": ["适配螺纹", "适配螺栓性能等级"],
        "required_attributes": ["适配螺纹"], "descriptor_attributes": ["适配螺栓性能等级", "材质"],
        "purchase_only_attributes": ["包装"], "configured_uom": "套",
        "rationale": "组合供货按适配螺纹选择；历史单位冲突时仍需人工核对。",
    },
    "吊带": {
        "decision": "configurable", "canonical_family": "吊带",
        "catalog_match_status": "aligned_to_internal_family",
        "existing_standard_type_candidates": ["吊带"], "selector_axes": ["规格"],
        "required_attributes": ["规格", "额定载荷", "有效长度", "吊带形式", "安全系数/执行标准"],
        "descriptor_attributes": ["用途", "材质"], "purchase_only_attributes": ["品牌", "包装"],
        "configured_uom": "条", "rationale": "载荷和长度是安全及价格关键，缺失时不得直接发布。",
    },
    "钢丝绳": {
        "decision": "configurable", "canonical_family": "钢丝绳",
        "catalog_match_status": "aligned_to_internal_family",
        "existing_standard_type_candidates": ["钢丝绳"], "selector_axes": ["规格"],
        "required_attributes": ["规格", "直径", "绳芯/结构", "长度", "执行标准"],
        "descriptor_attributes": ["材质", "表面处理"], "purchase_only_attributes": ["品牌", "包装"],
        "configured_uom": "卷", "rationale": "承载和长度决定安全与价格，按配置而非自由组合。",
    },
    "高压胶管": {
        "decision": "configurable", "canonical_family": "高压胶管",
        "catalog_match_status": "aligned_to_internal_family",
        "existing_standard_type_candidates": ["高压胶管"],
        "selector_axes": ["公称尺寸", "结构规格", "长度", "接口/结构"],
        "required_attributes": ["公称尺寸", "结构规格", "长度", "接口/结构"],
        "descriptor_attributes": ["用途", "材质"], "purchase_only_attributes": ["品牌", "包装"],
        "configured_uom": "条", "rationale": "胶管结构、长度和接口均会改变适配和价格；不从别名自动合并。",
    },
    "灭火器": {
        "decision": "split_required", "canonical_family": "灭火器",
        "catalog_match_status": "split_to_existing_types",
        "existing_standard_type_candidates": ["灭火器", "家庭/企业灭火器组合装"],
        "selector_axes": ["灭火剂类型", "额定容量"],
        "required_attributes": ["灭火剂类型", "额定容量"], "descriptor_attributes": ["用途", "材质"],
        "purchase_only_attributes": ["品牌", "包装"], "configured_uom": "件",
        "rationale": "灭火器与灭火器箱/组合装必须拆开；缺灭火剂或容量时阻断。",
    },
    "防锈漆": {
        "decision": "selector", "canonical_family": "防锈漆",
        "catalog_match_status": "aligned_to_internal_family", "existing_standard_type_candidates": ["防锈漆"],
        "selector_axes": ["规格", "颜色"], "required_attributes": ["规格"],
        "descriptor_attributes": ["表面处理", "用途"], "purchase_only_attributes": ["品牌", "包装"],
        "configured_uom": "桶", "rationale": "包装规格影响采购价格；用途和颜色作为描述/校验。",
    },
    "螺丝": {
        "decision": "split_required", "canonical_family": "螺丝",
        "catalog_match_status": "split_to_existing_types",
        "existing_standard_type_candidates": ["六角螺栓", "内六角螺钉", "机螺钉", "自攻螺钉", "双头螺栓", "膨胀锚栓"],
        "selector_axes": ["规格", "性能/等级", "材质/表面处理"],
        "required_attributes": ["头型/结构", "规格", "性能/等级", "材质/表面处理"],
        "descriptor_attributes": ["用途"], "purchase_only_attributes": ["品牌", "包装"], "configured_uom": "件",
        "rationale": "‘螺丝’不是可采购标准类型；必须按头型、结构和用途拆到既有类型。",
    },
    "膨胀螺丝": {
        "decision": "split_required", "canonical_family": "膨胀螺丝",
        "catalog_match_status": "split_to_existing_types", "existing_standard_type_candidates": ["膨胀锚栓", "膨胀螺栓"],
        "selector_axes": ["规格", "材质/表面处理", "性能/等级"],
        "required_attributes": ["锚固结构", "规格", "材质/表面处理", "性能/等级"],
        "descriptor_attributes": ["用途"], "purchase_only_attributes": ["品牌", "包装"], "configured_uom": "件",
        "rationale": "膨胀结构存在锚栓/螺栓差异，不能把同名记录直接合成一个族。",
    },
    "无缝管": {
        "decision": "configurable", "canonical_family": "无缝管", "catalog_match_status": "not_yet_aligned",
        "existing_standard_type_candidates": [], "selector_axes": ["规格"],
        "required_attributes": ["外径", "壁厚", "长度", "材质", "执行标准"],
        "descriptor_attributes": ["用途"], "purchase_only_attributes": ["品牌", "包装"], "configured_uom": "",
        "rationale": "规格不足以确定外径、壁厚和材质；先建立单位和字段规则。",
    },
    "卸扣": {
        "decision": "selector", "canonical_family": "卸扣", "catalog_match_status": "not_yet_aligned",
        "existing_standard_type_candidates": [], "selector_axes": ["规格"],
        "required_attributes": ["额定载荷", "型式", "销轴"], "descriptor_attributes": ["材质"],
        "purchase_only_attributes": ["品牌", "包装"], "configured_uom": "件",
        "rationale": "额定载荷和型式决定安全及价格，未完成字段规则前不发布。",
    },
    "扎带": {
        "decision": "selector", "canonical_family": "扎带", "catalog_match_status": "not_yet_aligned",
        "existing_standard_type_candidates": [], "selector_axes": ["规格"],
        "required_attributes": ["长度", "宽度", "材质", "颜色", "抗拉强度"], "descriptor_attributes": [],
        "purchase_only_attributes": ["品牌", "包装"], "configured_uom": "条",
        "rationale": "长度、宽度和抗拉强度是可替代性及价格边界，包装不制造 SKU。",
    },
    "五孔面板插座": {
        "decision": "selector", "canonical_family": "五孔面板插座", "catalog_match_status": "not_yet_aligned",
        "existing_standard_type_candidates": [], "selector_axes": ["规格", "接口/结构"],
        "required_attributes": ["额定电流", "额定电压", "安装方式"], "descriptor_attributes": ["颜色", "材质"],
        "purchase_only_attributes": ["品牌", "包装"], "configured_uom": "个",
        "rationale": "电气额定参数影响安全和价格；插座与开关插座不能按相似名称合并。",
    },
}

_STRUCTURAL_TOKENS = {"弯头", "接头", "内丝", "外丝", "直通", "直接", "三通", "四通", "法兰", "箱", "灭火器", "灭火器箱", "阀", "管", "扣", "螺栓", "螺钉"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _base_decision(cluster: dict[str, Any]) -> dict[str, Any]:
    family = cluster["standard_type_candidate"]
    configured = dict(_FAMILY_DECISIONS.get(family) or {})
    if configured:
        return configured
    if cluster.get("publication_readiness") == "blocked" or cluster.get("family_template_status") == "blocked":
        return {
            "decision": "blocked", "canonical_family": family, "catalog_match_status": "blocked",
            "existing_standard_type_candidates": [], "selector_axes": [], "required_attributes": [],
            "descriptor_attributes": [], "purchase_only_attributes": [], "configured_uom": "",
            "rationale": "v0.5 已发现阻断项，不能进入族模板或发布。",
        }
    quadrant = cluster.get("frequency_quadrant")
    if quadrant == "high_repeat_single_spec":
        decision = "single_spec_keep"
        rationale = "高频但未观察到多规格；先保留单规格，不因频次强行建立选择器。"
    elif quadrant == "low_repeat_multi_spec":
        decision = "defer_multi_spec"
        rationale = "多规格但重复度不足，等高频族规则沉淀后再复核。"
    else:
        decision = "defer"
        rationale = "非本轮优先族；保留原始证据，不自动创建模板。"
    return {
        "decision": decision, "canonical_family": family,
        "catalog_match_status": "not_yet_aligned", "existing_standard_type_candidates": [],
        "selector_axes": [], "required_attributes": [], "descriptor_attributes": [],
        "purchase_only_attributes": [], "configured_uom": "", "rationale": rationale,
    }


def _unit_evidence(cluster: dict[str, Any]) -> dict[str, Any]:
    quality = cluster.get("uom_quality") or {}
    status = quality.get("status") or "missing"
    policy_status = quality.get("policy_status") or "missing"
    reliability = "strong" if status in {"trusted", "normalized_alias"} and policy_status == "defined" else "weak" if status == "conflict" else "missing"
    return {
        "policy_status": policy_status, "historical_uom_status": status,
        "reliability": reliability, "preferred_uom": quality.get("preferred_uom", ""),
        "historical_uoms": quality.get("normalized_uoms", []),
        "invalid_source_uoms": quality.get("invalid_source_uoms", []),
        "cannot_auto_convert": reliability != "strong",
        "evidence_note": "历史单位只作证据；冲突或缺失时禁止静默换算。",
    }


def _frequency_evidence(cluster: dict[str, Any], rows_by_id: dict[int, Any]) -> dict[str, Any]:
    members = [rows_by_id[row_id] for row_id in cluster.get("source_rows", []) if row_id in rows_by_id]
    same_day_name_counts = Counter((row.purchase_date, row.raw_name) for row in members)
    duplicate_groups = {key: count for key, count in same_day_name_counts.items() if count > 1}
    duplicate_excess = sum(count - 1 for count in duplicate_groups.values())
    sessions = {(row.purchase_date, row.procedure_sequence) for row in members}
    technical_events = {(row.purchase_date, row.procedure_sequence, row.technical_variant_key) for row in members}
    return {
        "line_count": len(members),
        "unique_purchase_date_count": len({row.purchase_date for row in members}),
        "unique_session_count": len(sessions),
        "deduped_event_count": len(technical_events),
        "same_day_duplicate_group_count": len(duplicate_groups),
        "same_day_duplicate_excess_line_count": duplicate_excess,
        "frequency_signal": "repeat_across_dates" if len({row.purchase_date for row in members}) >= 4 and len(sessions) >= 4 else "not_repeat_across_dates",
        "prioritization_only": True,
        "note": "频次用于排序和复核优先级，不等同于真实采购订单数。",
    }


def _missing_required(decision: dict[str, Any], cluster: dict[str, Any]) -> list[str]:
    observed = cluster.get("attributes_observed") or {}
    return [field for field in decision.get("required_attributes", []) if not observed.get(field)]


def _review_decision(cluster: dict[str, Any], rows_by_id: dict[int, Any]) -> dict[str, Any]:
    decision = _base_decision(cluster)
    unit = _unit_evidence(cluster)
    gaps = _missing_required(decision, cluster)
    publication = cluster.get("publication_readiness")
    if decision["decision"] in {"selector", "configurable"}:
        gate = "manual_review_required" if (gaps or unit["reliability"] != "strong" or publication != "ready_for_review") else "ready_for_template_review"
    elif decision["decision"] == "split_required":
        gate = "split_before_template"
    elif decision["decision"] in {"defer", "defer_multi_spec", "single_spec_keep"}:
        gate = "deferred"
    elif decision["decision"] == "blocked":
        gate = "blocked"
    else:
        gate = "manual_review_required"
    return {
        "cluster_id": cluster["cluster_id"], "standard_type_candidate": cluster["standard_type_candidate"],
        "line_count": cluster["line_count"], "variant_count": cluster["variant_count"],
        "frequency_quadrant": cluster["frequency_quadrant"], "family_confidence": cluster["family_confidence"],
        "decision": decision["decision"], "canonical_family": decision["canonical_family"],
        "catalog_match_status": decision["catalog_match_status"],
        "existing_standard_type_candidates": decision["existing_standard_type_candidates"],
        "selector_axes": decision["selector_axes"], "required_attributes": decision["required_attributes"],
        "required_attribute_gaps": gaps, "descriptor_attributes": decision["descriptor_attributes"],
        "purchase_only_attributes": decision["purchase_only_attributes"],
        "configured_uom": decision["configured_uom"], "unit_evidence": unit,
        "publication_gate": gate, "v5_publication_readiness": publication,
        "frequency_evidence": _frequency_evidence(cluster, rows_by_id),
        "rationale": decision["rationale"], "no_auto_publish": True,
    }


def _annotate_fuzzy(candidates: list[dict[str, Any]], decisions: dict[str, dict[str, Any]], clusters: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for source in candidates:
        row = dict(source)
        left = decisions.get(row["left_cluster_id"], {})
        right = decisions.get(row["right_cluster_id"], {})
        left_name = row.get("left_type", "")
        right_name = row.get("right_type", "")
        left_tokens = {token for token in _STRUCTURAL_TOKENS if token in left_name}
        right_tokens = {token for token in _STRUCTURAL_TOKENS if token in right_name}
        same_canonical = bool(left.get("canonical_family")) and left.get("canonical_family") == right.get("canonical_family")
        if same_canonical and left_tokens == right_tokens and left.get("decision") not in {"split_required", "blocked"}:
            action = "alias_review_candidate"
            guard_reason = "同一候选族且未发现结构标记差异；仍需人工核对。"
        else:
            action = "do_not_merge"
            guard_reason = "结构标记、族决策或拆分要求存在差异；禁止自动合并。"
        row["reconciliation_action"] = action
        row["reconciliation_guard_reason"] = guard_reason
        row["left_v6_decision"] = left.get("decision", "")
        row["right_v6_decision"] = right.get("decision", "")
        row["decision"] = "人工复核，不自动合并"
        output.append(row)
    return output


def build_v6_review(v5_result: dict[str, Any]) -> dict[str, Any]:
    """Build the v0.6 review package from an in-memory v0.5 result."""
    rows_by_id = {row.source_row: row for row in v5_result["rows"]}
    decisions = [_review_decision(cluster, rows_by_id) for cluster in v5_result["clusters"]]
    decision_by_id = {row["cluster_id"]: row for row in decisions}
    clusters = []
    for cluster in v5_result["clusters"]:
        enriched = dict(cluster)
        enriched["v6_decision"] = decision_by_id[cluster["cluster_id"]]
        clusters.append(enriched)
    fuzzy = _annotate_fuzzy(v5_result["fuzzy_review_candidates"], decision_by_id, {c["cluster_id"]: c for c in clusters})
    total_lines = len(v5_result["rows"])
    decision_counts = Counter(row["decision"] for row in decisions)
    gate_counts = Counter(row["publication_gate"] for row in decisions)
    unit_counts = Counter(row["unit_evidence"]["reliability"] for row in decisions)
    summary = {
        "version": VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_path": v5_result["summary"]["source_path"], "source_sha256": v5_result["summary"]["source_sha256"],
        "source_sheet": v5_result["summary"].get("source_sheet", "实际采购清单"),
        "source_row_count": total_lines, "cluster_count": len(clusters),
        "decision_counts": dict(decision_counts), "publication_gate_counts": dict(gate_counts),
        "unit_evidence_reliability_counts": dict(unit_counts),
        "priority_decision_cluster_count": sum(row["decision"] in {"selector", "configurable", "split_required"} for row in decisions),
        "priority_decision_line_coverage_percent": round(100 * sum(row["line_count"] for row in decisions if row["decision"] in {"selector", "configurable", "split_required"}) / total_lines, 2) if total_lines else 0,
        "required_attribute_gap_cluster_count": sum(bool(row["required_attribute_gaps"]) for row in decisions),
        "fuzzy_candidate_count": len(fuzzy),
        "fuzzy_do_not_merge_count": sum(row["reconciliation_action"] == "do_not_merge" for row in fuzzy),
        "fuzzy_alias_review_candidate_count": sum(row["reconciliation_action"] == "alias_review_candidate" for row in fuzzy),
        "v5_output_root": v5_result.get("output_root"), "writes_erpnext": False,
        "notes": [
            "本轮只增加目录对齐和人工决策层，不覆盖 v0.5 原始发现结果。",
            "selector/configurable 表示候选模板形态，不代表已经批准生成 SKU。",
            "split_required 先拆到标准类型，再分别建立属性选择器；模糊候选默认禁止合并。",
            "单位冲突或缺失时不得静默换算；频次只用于排序，不冒充真实订单数。",
        ],
    }
    audit = {
        "version": VERSION, "source_sha256": summary["source_sha256"],
        "queue_reference": v5_result["summary"].get("review_queue_counts", {}),
        "decision_counts": dict(decision_counts), "publication_gate_counts": dict(gate_counts),
        "unit_evidence_reliability_counts": dict(unit_counts),
        "required_attribute_gap_clusters": [row["cluster_id"] for row in decisions if row["required_attribute_gaps"]],
        "split_required_families": [row["standard_type_candidate"] for row in decisions if row["decision"] == "split_required"],
        "fuzzy_do_not_merge_count": summary["fuzzy_do_not_merge_count"],
        "fuzzy_alias_review_candidate_count": summary["fuzzy_alias_review_candidate_count"],
        "all_decisions_have_no_auto_publish": all(row["no_auto_publish"] for row in decisions),
        "frequency_is_prioritization_only": all(row["frequency_evidence"]["prioritization_only"] for row in decisions),
    }
    return {"summary": summary, "clusters": clusters, "review_decisions": decisions, "fuzzy_review_candidates": fuzzy, "quality_audit": audit}


def discover_v6(source_path: Path = DEFAULT_SOURCE_PATH, output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict[str, Any]:
    """Run v0.5 into a staging directory and emit only read-only v0.6 data."""
    output_root = Path(output_root)
    staging = output_root / "_v0.5"
    v5_result = discover_v5(source_path, staging)
    result = build_v6_review(v5_result)
    output_root.mkdir(parents=True, exist_ok=True)
    for name, rows in {
        "clusters.jsonl": result["clusters"],
        "review-decisions.jsonl": result["review_decisions"],
        "fuzzy-review-candidates.jsonl": result["fuzzy_review_candidates"],
    }.items():
        with (output_root / name).open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    (output_root / "discovery-summary.json").write_text(json.dumps(result["summary"], ensure_ascii=False, indent=2), encoding="utf-8")
    (output_root / "quality-audit.json").write_text(json.dumps(result["quality_audit"], ensure_ascii=False, indent=2), encoding="utf-8")
    result["output_root"] = str(output_root)
    result["v5_result"] = v5_result
    return result


__all__ = ["DEFAULT_OUTPUT_ROOT", "VERSION", "build_v6_review", "discover_v6"]
