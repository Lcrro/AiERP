"""Run a conservative model-assisted first pass over the retrieval review queue.

This command deliberately writes a *separate* projection.  It does not fill
``review_decision``, does not promote aliases, and never writes ERPNext.  The
model verdict is an auditable recommendation for a human reviewer, not a
gold-standard label.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.item_master.release_resolver import normalize_text


DEFAULT_INPUT = ROOT / "data" / "material_master" / "retrieval_review_v0_1.jsonl"
DEFAULT_OUTPUT = ROOT / "data" / "material_master" / "retrieval_review_v0_1.model_pre_review.jsonl"
DEFAULT_SUMMARY = ROOT / "data" / "material_master" / "retrieval_review_v0_1.model_pre_review.summary.json"

MODEL_REVIEWER = "codex-model-assisted-v0.1"

# A short query can be semantically plausible while still omitting a purchase
# critical attribute.  Keep these conservative exceptions explicit so a later
# reviewer can audit the policy rather than reverse-engineer a score.
AMBIGUOUS_ALIAS_QUERIES = {
    "灭火器2kg": "只给出容量，未说明灭火剂/类型，不能排除二氧化碳等其他灭火器。",
    "4m膨胀管300只/包": "查询中的 4m 与目标 SKU 的 Φ6×30 mm 不一致，可能是录入错误或另一规格。",
    "公牛86型五孔插座面板": "可归入86型五孔墙壁插座，但查询未明确10 A、明装及附加功能，不能直接自动选定具体SKU。",
    "公牛86型五孔面板底座": "底座可能指底盒，也可能指面板组件，需核对实物或原始单据。",
    "公牛86型五孔插板底座": "插板底座与墙壁插座明装底盒存在语义边界，需核对实物。",
    "黄沙": "通用俗称缺少粒度和颜色，目标为中砂黄色，需核对采购规格。",
    "95水泥砖": "只给出尺寸和俗称，未明确实心结构及材质，需核对采购规格。",
    "扫把": "通用名称未说明材质和长度，目标为塑料长柄扫把。",
    "麻绳": "通用名称未说明直径，目标为 Φ12 mm，不能据此自动绑定。",
    "阀门扳手": "未说明 F 型和长度，目录中可能存在其他阀门扳手。",
    "150卡箍": "未说明沟槽、刚性等结构属性，不能仅凭 DN150 自动绑定。",
    "棉大衣": "未说明均码、长款加厚等采购属性。",
    "瓦刀": "与泥瓦刀存在同义/不同 SKU 边界，需核对形状和规格。",
    "泥瓦刀": "与瓦刀存在同义/不同 SKU 边界，需核对形状和规格。",
    "公元Φ110截止阀": "未说明 PPR 或普通给水截止阀，目录中存在不同标准类型。",
    "6寸防爆快速接头": "查询含防爆属性，而目标仅标注耐磨防脱，需核对产品属性。",
    "6寸防爆耐磨水带": "查询含防爆属性，而目标名称未明确防爆，需核对产品属性。",
    "4寸防爆耐磨水带": "查询含防爆属性，而目标名称未明确防爆，需核对产品属性。",
}


def _read_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                rows.append({
                    "review_id": f"INVALID-{line_number:04d}",
                    "sample_role": "invalid",
                    "query": "",
                    "_parse_error": str(exc),
                })
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _source_audit(row: dict[str, Any]) -> tuple[str, list[str]]:
    """Return a source-evidence status and machine-readable evidence."""

    role = str(row.get("sample_role") or "").casefold()
    source = row.get("source_identity")
    if "canonical" in row.get("coverage_tags", []) and not source:
        return "catalog_exact", ["current_numeric_catalog"]
    if not source:
        return "not_provided", ["no_source_identity_in_review_row"]
    records = source if isinstance(source, list) else [source]
    complete = True
    for record in records:
        if not isinstance(record, dict):
            complete = False
            continue
        required = ("source_dataset", "source_document", "source_sheet", "source_row", "source_row_hash")
        if any(not str(record.get(key) or "").strip() for key in required):
            complete = False
    if complete:
        return "complete", ["composite_source_identity", "source_row_hash"]
    if "positive" in role:
        return "missing_row_hash", ["composite_source_identity_present", "source_row_hash_missing"]
    return "incomplete", ["source_identity_incomplete"]


def _spec_tokens(text: str) -> set[str]:
    return {
        normalize_text(token)
        for token in re.findall(
            r"(?:[a-z]+\s*)?\d+(?:\.\d+)?(?:\s*[*×x/]\s*\d+(?:\.\d+)?)?\s*(?:mm|cm|m|kg|kw|w|a|v|寸|号|只|包)?",
            text,
            flags=re.IGNORECASE,
        )
        if normalize_text(token)
    }


def _assess_positive(row: dict[str, Any]) -> dict[str, Any]:
    query = str(row.get("query") or "").strip()
    expected_name = str(row.get("expected_item_name") or "").strip()
    expected_code = str(row.get("expected_item_code") or "").strip()
    tags = set(row.get("coverage_tags") or [])
    source_status, evidence = _source_audit(row)
    if "canonical" in tags and normalize_text(query) == normalize_text(expected_name) and expected_code.isdigit():
        return {
            "verdict": "likely_match",
            "confidence": "high",
            "recommended_target_item_code": expected_code,
            "rationale": "查询与当前发布目录 SKU 名称完全一致，且目标 Item Code 为纯数字。可作为正样本候选，但仍需人工确认。",
            "evidence": [*evidence, "query_equals_current_sku_name", "numeric_item_code"],
            "human_review_required": True,
        }
    if "typo" in tags:
        return {
            "verdict": "needs_human",
            "confidence": "medium",
            "recommended_target_item_code": expected_code,
            "rationale": "这是由标准 SKU 生成的错别字挑战；语义上可能相同，但错别字不应未经人工确认进入别名。",
            "evidence": [*evidence, "single_typo_challenge", "target_sku_available"],
            "human_review_required": True,
        }
    if query in AMBIGUOUS_ALIAS_QUERIES:
        return {
            "verdict": "needs_human",
            "confidence": "low",
            "recommended_target_item_code": expected_code,
            "rationale": AMBIGUOUS_ALIAS_QUERIES[query],
            "evidence": [*evidence, "missing_or_conflicting_required_attribute"],
            "human_review_required": True,
        }
    query_specs = _spec_tokens(query)
    expected_specs = _spec_tokens(expected_name)
    # A short source token such as ``110`` or ``2.5`` is often embedded in a
    # catalog token such as ``110×45`` or ``2.5mm``.  Treat that as evidence,
    # but keep the explicit ambiguity list above in force for conflicting
    # values and omitted purchase-critical attributes.
    matching_specs = sorted(
        token
        for token in query_specs
        if any(token in expected or expected in token for expected in expected_specs)
    )
    if matching_specs or (query and normalize_text(query) in normalize_text(expected_name)):
        return {
            "verdict": "likely_match",
            "confidence": "medium",
            "recommended_target_item_code": expected_code,
            "rationale": "查询包含目标 SKU 的核心类型或规格信息，当前映射具有较强语义一致性；因来源为银标候选仍需人工确认。",
            "evidence": [*evidence, "silver_link_candidate", *([f"matching_spec:{item}" for item in matching_specs] if matching_specs else ["type_token_overlap"])],
            "human_review_required": True,
        }
    return {
        "verdict": "needs_human",
        "confidence": "low",
        "recommended_target_item_code": expected_code,
        "rationale": "查询与目标 SKU 的可验证规格或类型词不足，不能安全确认别名。",
        "evidence": [*evidence, "insufficient_spec_or_type_overlap"],
        "human_review_required": True,
    }


def _assess_row(row: dict[str, Any]) -> dict[str, Any]:
    role = str(row.get("sample_role") or "").casefold()
    if role == "positive_candidate":
        return _assess_positive(row)
    if role in {"hard_negative_candidate", "nonexistent_candidate"}:
        candidate = str(row.get("candidate_item_code") or "").strip()
        expected = str(row.get("expected_item_code") or "").strip()
        if role == "nonexistent_candidate":
            rationale = "查询明确标记为不存在物料测试值，不应召回或自动选择。"
            evidence = ["nonexistent_query_pattern"]
        else:
            rationale = "候选 Item Code 与期望 Item Code 不同，且该行被构造为跨标准类型干扰，应拒绝候选。"
            evidence = ["cross_type_hard_negative", "candidate_differs_from_expected"]
        return {
            "verdict": "likely_non_match",
            "confidence": "high",
            "recommended_target_item_code": "",
            "rationale": rationale,
            "evidence": evidence + ([f"candidate_item_code:{candidate}"] if candidate else []),
            "human_review_required": True,
        }
    return {
        "verdict": "needs_human",
        "confidence": "low",
        "recommended_target_item_code": "",
        "rationale": "审核行格式或样本角色无法识别，需人工处理。",
        "evidence": ["unrecognized_review_role"],
        "human_review_required": True,
    }


def model_pre_review(
    input_path: str | Path = DEFAULT_INPUT,
    output_path: str | Path = DEFAULT_OUTPUT,
    summary_path: str | Path = DEFAULT_SUMMARY,
    *,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    input_file = Path(input_path)
    output_file = Path(output_path)
    summary_file = Path(summary_path)
    timestamp = reviewed_at or datetime.now().astimezone().isoformat(timespec="seconds")
    output_rows: list[dict[str, Any]] = []
    verdict_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    for row in _read_rows(input_file):
        assessment = _assess_row(row)
        source_status, _ = _source_audit(row)
        role = str(row.get("sample_role") or "invalid")
        role_counts[role] += 1
        verdict_counts[assessment["verdict"]] += 1
        source_counts[source_status] += 1
        output_rows.append({
            **row,
            # Keep the authoritative human fields untouched.  In particular,
            # review_gate_status() must still see these rows as pending.
            "label_status": "model_pre_reviewed",
            "review_decision": str(row.get("review_decision") or ""),
            "model_pre_review": {
                **assessment,
                "reviewer": MODEL_REVIEWER,
                "reviewed_at": timestamp,
                "production_effect": "none",
            },
            "source_audit_status": source_status,
        })
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in output_rows),
        encoding="utf-8",
    )
    summary = {
        "schema_version": "retrieval-review-model-pre-review-v0.1",
        "input": str(input_file),
        "output": str(output_file),
        "reviewed_at": timestamp,
        "reviewer": MODEL_REVIEWER,
        "row_count": len(output_rows),
        "role_counts": dict(role_counts),
        "verdict_counts": dict(verdict_counts),
        "source_audit_counts": dict(source_counts),
        "human_review_required_count": sum(
            bool(row["model_pre_review"].get("human_review_required")) for row in output_rows
        ),
        "production_effect": {
            "writes_erpnext": False,
            "fills_human_review_decision": False,
            "promotes_aliases": False,
            "enables_vector_retrieval": False,
        },
        "notes": [
            "模型预审仅提供建议，不是人工确认金标准。",
            "原始审核队列仍保持 pending_review，需人工填写 review_decision、reviewer 和 reviewed_at。",
            (
                "本轮银标记录来源身份均含 source_row_hash。"
                if not source_counts.get("missing_row_hash")
                else "缺少 source_row_hash 的银标记录被标记为 missing_row_hash，不得仅凭模型结论晋升。"
            ),
        ],
    }
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"rows": output_rows, "summary": summary, "output": str(output_file), "summary_path": str(summary_file)}


def main() -> int:
    parser = argparse.ArgumentParser(description="对物料检索审核队列执行保守的模型辅助预审")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--reviewed-at", default=None, help="固定审核时间，便于可重复测试")
    args = parser.parse_args()
    result = model_pre_review(args.input, args.output, args.summary, reviewed_at=args.reviewed_at)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
