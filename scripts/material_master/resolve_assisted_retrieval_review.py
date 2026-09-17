"""Resolve the 19 high-risk retrieval rows with auditable assisted decisions.

The output is deliberately separate from the human gold-label queue.  These
decisions help a human reviewer finish the queue, but they never populate
``review_decision``, promote aliases, enable vectors, or write ERPNext.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data" / "material_master" / "retrieval_review_v0_1.model_pre_review.jsonl"
DEFAULT_OUTPUT = ROOT / "data" / "material_master" / "retrieval_review_v0_1.assisted_resolution.jsonl"
DEFAULT_SUMMARY = ROOT / "data" / "material_master" / "retrieval_review_v0_1.assisted_resolution.summary.json"
ASSISTED_REVIEWER = "codex-assisted-material-review-v0.1"


TYPO_IDS = {f"POS-{index:04d}" for index in range(260, 270)}

# These source aliases already have a governed current placement.  The
# resolution accepts them for candidate recall/evaluation only.  Exact SKU
# auto-selection remains subject to all required attributes, so a generic
# alias such as "扫把" or "阀门扳手" still asks for the missing specification.
SOURCE_ALIAS_DECISIONS: dict[str, dict[str, str]] = {
    "POS-0276": {
        "basis": "现有边界审阅已将采购行42确定为2 kg手提式ABC干粉灭火器；保留消防验收约束。",
        "guard": "仅凭“2kg”不得绕过灭火剂和型式校验。",
    },
    "POS-0280": {
        "basis": "现有治理记录按用户授权，将“4m”解释为与4.2 mm自攻螺钉配套的Φ6×30 mm尼龙膨胀管。",
        "guard": "保留原文解释依据；若后续出现其他规格，必须重新确认，不能沿用默认值。",
    },
    "POS-0286": {
        "basis": "采购行5、9、82及现有治理记录一致归入86型五孔墙壁插座。",
        "guard": "10 A、明装及附加功能仍属于必选属性，查询缺失时不得自动选料。",
    },
    "POS-0287": {
        "basis": "采购历史中“黄沙”重复出现，现有发布物料将其治理为建筑用天然砂。",
        "guard": "中砂、颜色和用途未在短名称中完整表达，只能召回候选。",
    },
    "POS-0289": {
        "basis": "采购原文明确为95水泥砖，现有发布物料保留95 mm系列并治理为混凝土实心砖。",
        "guard": "结构和强度要求仍需按具体采购确认。",
    },
    "POS-0290": {
        "basis": "采购行10、83与既有治理记录一致归入86型墙壁插座明装底盒。",
        "guard": "“底座”只作为召回别名；盒深和安装方式缺失时不得自动选料。",
    },
    "POS-0291": {
        "basis": "现有发布记录将采购行13与大竹扫把区分，治理为塑料长柄扫把。",
        "guard": "通用词“扫把”缺少材质和形式，只能召回候选。",
    },
    "POS-0295": {
        "basis": "采购行4与既有治理记录一致归入86型墙壁插座明装底盒。",
        "guard": "“插板底座”存在口语歧义，盒深和安装方式缺失时不得自动选料。",
    },
    "POS-0299": {
        "basis": "现有发布记录将采购行16按施工现场常用手动F型阀门扳手治理为300 mm规格。",
        "guard": "通用词“阀门扳手”缺少形式和长度，只能召回候选。",
    },
}


def _read_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
    return rows


def resolve_assisted_review(
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
    resolved: list[dict[str, Any]] = []
    for row in _read_rows(input_file):
        model_review = row.get("model_pre_review") or {}
        if model_review.get("verdict") != "needs_human":
            continue
        review_id = str(row.get("review_id") or "")
        if review_id in TYPO_IDS:
            decision = {
                "evaluation_decision": "confirmed_positive",
                "candidate_recall_decision": "evaluation_only",
                "production_alias_action": "do_not_promote_synthetic_typo",
                "basis": "查询是当前标准SKU名称的单字错别字挑战，目标物料和全部规格保持一致。",
                "guard": "该样本由测试生成，不代表真实采购别名，不能写入生产别名表。",
            }
        elif review_id in SOURCE_ALIAS_DECISIONS:
            detail = SOURCE_ALIAS_DECISIONS[review_id]
            source_status = str(row.get("source_audit_status") or "")
            decision = {
                "evaluation_decision": "confirmed_positive",
                "candidate_recall_decision": "accepted_with_required_attribute_guard",
                "production_alias_action": "keep_as_reviewed_candidate_only",
                "basis": detail["basis"],
                "guard": detail["guard"],
                "source_identity_verified": source_status == "complete",
            }
        else:
            decision = {
                "evaluation_decision": "unresolved",
                "candidate_recall_decision": "needs_human",
                "production_alias_action": "none",
                "basis": "没有配置受控复核结论。",
                "guard": "保持待复核。",
            }
        resolved.append({
            "review_id": review_id,
            "query": row.get("query", ""),
            "expected_item_code": row.get("expected_item_code", ""),
            "expected_item_name": row.get("expected_item_name", ""),
            "source_identity": row.get("source_identity") or {},
            "source_audit_status": row.get("source_audit_status", ""),
            # Human gold fields intentionally remain blank.
            "review_decision": "",
            "reviewer": "",
            "reviewed_at": "",
            "assisted_resolution": {
                **decision,
                "assisted_reviewer": ASSISTED_REVIEWER,
                "assisted_reviewed_at": timestamp,
                "human_confirmation_still_required": True,
                "production_effect": "none",
            },
        })
    expected_ids = TYPO_IDS | set(SOURCE_ALIAS_DECISIONS)
    actual_ids = {str(row.get("review_id") or "") for row in resolved}
    missing = sorted(expected_ids - actual_ids)
    unexpected = sorted(actual_ids - expected_ids)
    if missing or unexpected or len(resolved) != 19:
        raise RuntimeError(f"高风险复核集合不完整：missing={missing}, unexpected={unexpected}, count={len(resolved)}")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in resolved),
        encoding="utf-8",
    )
    summary = {
        "schema_version": "retrieval-review-assisted-resolution-v0.1",
        "input": str(input_file),
        "output": str(output_file),
        "assisted_reviewer": ASSISTED_REVIEWER,
        "assisted_reviewed_at": timestamp,
        "row_count": len(resolved),
        "decision_counts": dict(Counter(
            row["assisted_resolution"]["candidate_recall_decision"] for row in resolved
        )),
        "evaluation_positive_count": sum(
            row["assisted_resolution"]["evaluation_decision"] == "confirmed_positive" for row in resolved
        ),
        "complete_source_identity_count": sum(
            row.get("source_audit_status") == "complete" for row in resolved
        ),
        "synthetic_typo_count": sum(
            row["assisted_resolution"]["production_alias_action"] == "do_not_promote_synthetic_typo"
            for row in resolved
        ),
        "production_effect": {
            "writes_erpnext": False,
            "fills_human_gold_labels": False,
            "promotes_aliases": False,
            "enables_vector_retrieval": False,
        },
        "notes": [
            "10条错别字样本只确认评测关系，不进入生产别名。",
            "9条真实采购简称接受为候选召回关系，但查询缺少必选属性时仍不得自动选料。",
            "这是模型辅助复核结论，不冒充真人金标准。",
        ],
    }
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"rows": resolved, "summary": summary, "output": str(output_file), "summary_path": str(summary_file)}


def main() -> int:
    parser = argparse.ArgumentParser(description="落盘19条高风险物料检索样本的模型辅助复核结论")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--reviewed-at", default=None)
    args = parser.parse_args()
    result = resolve_assisted_review(
        args.input,
        args.output,
        args.summary,
        reviewed_at=args.reviewed_at,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
