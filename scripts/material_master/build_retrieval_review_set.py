"""Build a human-review queue for deterministic material retrieval.

This command only creates review data.  It never promotes aliases, writes
ERPNext, or treats generated matches as confirmed labels.  The output is
deliberately split into positive and hard-negative candidates so reviewers can
record an auditable decision before a row is allowed into production search.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.item_master.release_resolver import load_current_published_catalog
from nexterp_agent.item_master.source_identity import normalize_source_records

try:  # package import for tests; direct-script fallback for CLI use
    from .evaluate_vector_shadow import load_current_linked_cases
except ImportError:  # pragma: no cover - exercised by ``python script.py``
    from evaluate_vector_shadow import load_current_linked_cases


DEFAULT_OUTPUT = ROOT / "data" / "material_master" / "retrieval_review_v0_1.jsonl"
DEFAULT_SUMMARY = ROOT / "data" / "material_master" / "retrieval_review_v0_1.summary.json"


def _review_row(
    *,
    review_id: str,
    role: str,
    query: str,
    expected_item_code: str = "",
    expected_item_name: str = "",
    candidate_item_code: str = "",
    candidate_item_name: str = "",
    source_identity: Any = None,
    coverage_tags: list[str] | None = None,
    reason: str,
) -> dict[str, Any]:
    return {
        "review_id": review_id,
        "sample_role": role,
        "query": query,
        "expected_item_code": expected_item_code,
        "expected_item_name": expected_item_name,
        "candidate_item_code": candidate_item_code,
        "candidate_item_name": candidate_item_name,
        "source_identity": source_identity or {},
        "coverage_tags": list(dict.fromkeys(coverage_tags or [])),
        "selection_reason": reason,
        "label_status": "pending_review",
        "review_decision": "",
        "reviewer": "",
        "reviewed_at": "",
        "notes": "",
    }


_BRAND_TOKENS = ("飞利浦", "公牛", "世达", "东成", "起帆", "海螺", "立邦", "得力", "博世")


def _coverage_tags(query: str, row: dict[str, Any] | None = None) -> list[str]:
    """Label why a review row is useful; tags do not affect matching."""

    text = str(query or "")
    tags: list[str] = []
    if re.search(r"\d+(?:\.\d+)?\s*(?:mm|cm|m|kg|kw|w|a|v|φ|Φ|×|x|\*)", text, re.I):
        tags.append("spec_variant")
    row_brand_text = " ".join(
        str((row or {}).get(key) or "") for key in ("brand", "price_drivers")
    )
    if any(token in text for token in _BRAND_TOKENS) or any(token in row_brand_text for token in _BRAND_TOKENS):
        tags.append("brand")
    source_records = (row or {}).get("source_records")
    if isinstance(source_records, list) and len(source_records) > 1:
        tags.append("high_frequency")
    return tags


def _typo_variant(query: str) -> str:
    """Create a small, deterministic typo challenge for human review."""

    replacements = (
        ("螺栓", "螺拴"),
        ("接头", "接斗"),
        ("膨胀", "澎胀"),
        ("钢筋", "刚筋"),
        ("水泥", "水泥"),
        ("阀", "法"),
        ("管", "罐"),
    )
    for source, target in replacements:
        if source in query and source != target:
            return query.replace(source, target, 1)
    return ""


def build_review_set(output_path: Path = DEFAULT_OUTPUT, summary_path: Path = DEFAULT_SUMMARY) -> dict[str, Any]:
    catalog = load_current_published_catalog()
    positives: list[dict[str, Any]] = []
    seen_queries: set[str] = set()
    for row in catalog:
        query = str(row.get("sku_name") or row.get("item_name") or "").strip()
        code = str(row.get("item_code") or "").strip()
        if not query or not code or query in seen_queries:
            continue
        seen_queries.add(query)
        try:
            source_identity = json.loads(str(row.get("source_records") or "[]"))
        except json.JSONDecodeError:
            source_identity = []
        positives.append(_review_row(
            review_id=f"POS-{len(positives) + 1:04d}",
            role="positive_candidate",
            query=query,
            expected_item_code=code,
            expected_item_name=query,
            source_identity=normalize_source_records(source_identity),
            coverage_tags=["canonical", *_coverage_tags(query, row)],
            reason="当前数字 Item Code 的标准 SKU 名称；需人工确认可作为精确正样本。",
        ))

    # Add a few realistic typo forms.  These are still positive candidates,
    # never approved aliases, and make typo handling visible in the review
    # workload instead of silently treating it as a vector problem.
    typo_added = 0
    for row in catalog:
        if len(positives) >= 300 or typo_added >= 10:
            break
        query = str(row.get("sku_name") or row.get("item_name") or "").strip()
        typo = _typo_variant(query)
        code = str(row.get("item_code") or "").strip()
        if not typo or typo in seen_queries or not code:
            continue
        seen_queries.add(typo)
        typo_added += 1
        positives.append(_review_row(
            review_id=f"POS-{len(positives) + 1:04d}",
            role="positive_candidate",
            query=typo,
            expected_item_code=code,
            expected_item_name=query,
            source_identity=[],
            coverage_tags=["typo", *_coverage_tags(query, row)],
            reason="由标准 SKU 名称生成的错别字挑战；需人工确认是否仍指向同一物料。",
        ))

    # Add distinct silver aliases until the positive review queue reaches the
    # requested 300 rows.  They remain pending and are never auto-approved.
    for case in load_current_linked_cases():
        if len(positives) >= 300:
            break
        query = str(case.get("query") or "").strip()
        code = str(case.get("expected_top_item_code") or "").strip()
        if not query or not code or query in seen_queries:
            continue
        seen_queries.add(query)
        positives.append(_review_row(
            review_id=f"POS-{len(positives) + 1:04d}",
            role="positive_candidate",
            query=query,
            expected_item_code=code,
            expected_item_name=str(case.get("expected_top_item_name") or ""),
            source_identity=case.get("source_identity") or {},
            coverage_tags=["alias", "high_frequency", *_coverage_tags(query)],
            reason="频次发现与当前目录的银标链接；必须人工确认后才可成为别名。",
        ))

    if len(positives) < 300:
        raise RuntimeError(f"当前目录与银标样本不足 300 条正样本候选：{len(positives)}")

    negatives: list[dict[str, Any]] = []
    # Fifty cross-type hard negatives: the query is valid for one SKU but is
    # paired with a different standard type to test type/spec conflict gates.
    for index, left in enumerate(catalog):
        if len(negatives) >= 50:
            break
        left_code = str(left.get("item_code") or "")
        left_query = str(left.get("sku_name") or left.get("item_name") or "").strip()
        right = next(
            (
                candidate for candidate in catalog[index + 1:]
                if str(candidate.get("standard_name") or candidate.get("item_name") or "")
                != str(left.get("standard_name") or left.get("item_name") or "")
            ),
            None,
        )
        if not left_code or not left_query or right is None:
            continue
        negatives.append(_review_row(
            review_id=f"NEG-{len(negatives) + 1:04d}",
            role="hard_negative_candidate",
            query=left_query,
            expected_item_code=left_code,
            expected_item_name=left_query,
            candidate_item_code=str(right.get("item_code") or ""),
            candidate_item_name=str(right.get("sku_name") or right.get("item_name") or ""),
            coverage_tags=["hard_negative", "cross_type", *_coverage_tags(left_query, left)],
            reason="跨标准类型干扰对；需人工确认候选应被拒绝。",
        ))

    for index in range(50):
        query = f"不存在物料测试-{index + 1:03d}"
        negatives.append(_review_row(
            review_id=f"NEG-{len(negatives) + 1:04d}",
            role="nonexistent_candidate",
            query=query,
            coverage_tags=["nonexistent"],
            reason="不存在物料负样本；需人工确认不得召回或自动选择。",
        ))

    if len(negatives) < 100:
        raise RuntimeError(f"负样本候选不足 100 条：{len(negatives)}")

    rows = [*positives[:300], *negatives[:100]]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    summary = {
        "schema_version": "retrieval-review-v0.1",
        "positive_candidate_count": 300,
        "negative_candidate_count": 100,
        "label_status": "pending_review",
        "confirmed_positive_count": 0,
        "confirmed_negative_count": 0,
        "source": "current numeric catalog + current linked silver cases + deterministic hard negatives",
        "writes_erpnext": False,
        "coverage_tag_counts": {
            tag: sum(tag in row.get("coverage_tags", []) for row in rows)
            for tag in sorted({tag for row in rows for tag in row.get("coverage_tags", [])})
        },
        "notes": [
            "这些是人工复核候选，不是已确认金标准。",
            "只有 review_decision=approved 且 reviewer/reviewed_at 完整的正样本才可进入 approved_material_aliases。",
            "负样本不得作为候选别名或自动选择依据。",
        ],
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"rows": rows, "summary": summary, "output": str(output_path), "summary_path": str(summary_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="生成物料检索正/负样本人工复核队列")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()
    result = build_review_set(args.output, args.summary)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"output: {result['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
