"""Compare governed lexical retrieval with the vector shadow lane.

This is a read-only evaluation command.  It never writes ERPNext, changes a
catalog, or changes production ranking.  The JSON report is intended to make
the next review reproducible while labelled alias/normalisation data is still
being collected.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
from statistics import median
import sys
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.item_master.release_resolver import (
    DEFAULT_RELEASE_CATALOG_PATH,
    ReleaseMaterialResolver,
    load_current_published_catalog,
    normalize_specs,
    normalize_spec_text,
    normalize_text,
    score_release_row,
)
from nexterp_agent.item_master.source_identity import (
    DEFAULT_SOURCE_DATASET,
    DEFAULT_SOURCE_DOCUMENT,
    DEFAULT_SOURCE_SHEET,
    make_source_record,
    normalize_source_records,
    source_record_key,
    source_record_matches,
)


DEFAULT_CASES_PATH = ROOT / "data" / "material_purchase_2024" / "material_search_eval_cases.csv"
DEFAULT_CURRENT_LINKED_CLUSTERS_PATH = (
    ROOT / ".runtime" / "material-master" / "frequency-discovery" / "clusters.jsonl"
)
DEFAULT_CURRENT_PLACEMENTS_PATH = ROOT / ".runtime" / "material-master" / "gpc-material-placements.jsonl"
DEFAULT_CURRENT_ITEM_MAP_PATH = ROOT / ".runtime" / "erpnext-material-test" / "material-item-code-map.json"
DEFAULT_REVIEW_SET_PATH = ROOT / "data" / "material_master" / "retrieval_review_v0_1.jsonl"

VECTOR_REVIEW_GATES = {
    "minimum_confirmed_positive": 300,
    "minimum_confirmed_negative": 100,
    "minimum_recall_at_5": 0.95,
    "minimum_top1": 0.85,
    "maximum_hard_negative_mismatch_rate": 0.01,
    "minimum_recall_at_5_lift_over_lexical": 0.05,
    "top1_must_not_decrease": True,
}


def review_gate_status(path: str | Path = DEFAULT_REVIEW_SET_PATH) -> dict[str, Any]:
    """Report whether reviewed labels are sufficient to maintain vectors.

    The generated review queue deliberately starts with zero confirmed labels.
    Keeping this gate in the evaluator prevents a future shadow report from
    being mistaken for evidence that vector retrieval is production-ready.
    Metric thresholds are reported here as policy; they can only be evaluated
    after the corresponding rows contain reviewer decisions.
    """

    review_path = Path(path)
    counts = {"positive": 0, "negative": 0, "pending": 0, "invalid": 0}
    approved_values = {"approved", "confirmed", "positive", "通过", "确认", "正确"}
    rejected_values = {"rejected", "negative", "false", "否", "拒绝", "错误"}
    if not review_path.is_file():
        return {
            "status": "blocked",
            "path": str(review_path),
            "counts": counts,
            "gates": VECTOR_REVIEW_GATES,
            "reasons": ["人工复核队列不存在，不能评估向量维护门槛。"],
        }
    with review_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                counts["invalid"] += 1
                continue
            decision = str(row.get("review_decision") or "").strip().casefold()
            role = str(row.get("sample_role") or "").strip().casefold()
            if not decision:
                counts["pending"] += 1
            elif decision in approved_values:
                counts["positive"] += int("positive" in role)
            elif decision in rejected_values:
                counts["negative"] += int("negative" in role)
            else:
                counts["invalid"] += 1
    reasons: list[str] = []
    if counts["positive"] < VECTOR_REVIEW_GATES["minimum_confirmed_positive"]:
        reasons.append(
            f"已确认正样本 {counts['positive']} 条，少于 {VECTOR_REVIEW_GATES['minimum_confirmed_positive']} 条。"
        )
    if counts["negative"] < VECTOR_REVIEW_GATES["minimum_confirmed_negative"]:
        reasons.append(
            f"已确认负样本 {counts['negative']} 条，少于 {VECTOR_REVIEW_GATES['minimum_confirmed_negative']} 条。"
        )
    if counts["pending"] or counts["invalid"]:
        reasons.append(f"仍有 {counts['pending']} 条待复核、{counts['invalid']} 条决策值无效。")
    return {
        "status": "eligible_for_metric_check" if not reasons else "blocked",
        "path": str(review_path),
        "counts": counts,
        "gates": VECTOR_REVIEW_GATES,
        "reasons": reasons,
    }


def load_cases(path: str | Path = DEFAULT_CASES_PATH) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            raw_specs = row.get("specs_json") or row.get("specs") or "{}"
            try:
                specs = json.loads(raw_specs)
            except json.JSONDecodeError:
                specs = {}
            cases.append({**row, "specs": normalize_specs(specs if isinstance(specs, dict) else {})})
    return cases


def _placement_source_index(
    placements_path: str | Path = DEFAULT_CURRENT_PLACEMENTS_PATH,
    item_code_map_path: str | Path = DEFAULT_CURRENT_ITEM_MAP_PATH,
) -> dict[tuple[str, str, str, int], list[dict[str, Any]]]:
    """Index placements by the complete source identity, never row alone."""

    map_payload = json.loads(Path(item_code_map_path).read_text(encoding="utf-8"))
    code_map = map_payload.get("material_item_codes", map_payload)
    if not isinstance(code_map, dict):
        return {}
    by_source: dict[tuple[str, str, str, int], list[dict[str, Any]]] = {}
    with Path(placements_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            placement = json.loads(line)
            item_code = str(code_map.get(str(placement.get("material_id") or "")) or "").strip()
            if not item_code.isdigit():
                continue
            records = normalize_source_records(placement.get("source_records"))
            if not records and "实际采购清单" in str(placement.get("source_reference") or ""):
                # Migration fallback for legacy runtime rows.  The source
                # family is explicit in source_reference, so it cannot collide
                # with historical reference rows that reuse the same number.
                records = [
                    make_source_record(
                        int(source_row),
                        dataset=DEFAULT_SOURCE_DATASET,
                        document=DEFAULT_SOURCE_DOCUMENT,
                        sheet=DEFAULT_SOURCE_SHEET,
                    )
                    for source_row in placement.get("source_rows") or []
                    if str(source_row).isdigit()
                ]
            for record in records:
                by_source.setdefault(source_record_key(record), []).append({
                    **placement,
                    "item_code": item_code,
                    "_source_record": record,
                })
    return by_source


def _linked_placement(
    raw_name: str,
    cluster_standard_type: str,
    choices: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    """Choose a placement only when the source row and type give a safe label.

    A source row can be shared by a current placement and a historical
    reference row. We therefore require the governed standard type whenever it
    is available, and reject ties instead of manufacturing a gold label.
    """

    if not choices:
        return None, "unmatched_source_row"
    cluster_norm = normalize_text(cluster_standard_type)
    typed = [
        choice for choice in choices
        if cluster_norm and normalize_text(choice.get("standard_type")) == cluster_norm
    ]
    query_norm = normalize_text(raw_name)
    query_spec_tokens = [
        normalize_text(token)
        for token in re.findall(
            r"(?:[a-z]+\s*)?\d+(?:\.\d+)?(?:\s*[*×x/]\s*\d+(?:\.\d+)?)?\s*(?:mm|cm|m|kg|kw|w|a|v|寸|号|只|包)?",
            raw_name,
            flags=re.IGNORECASE,
        )
    ]
    query_spec_tokens = [token for token in query_spec_tokens if token]
    spec_matched = [
        choice for choice in choices
        if query_spec_tokens and any(
            normalize_text(token) in normalize_spec_text(
                " ".join([
                    str(choice.get("material_name") or ""),
                    str(choice.get("specification_basis") or ""),
                    json.dumps(choice.get("procurement_attributes") or {}, ensure_ascii=False),
                ])
            )
            for token in query_spec_tokens
        )
    ]
    if query_spec_tokens and not spec_matched:
        return None, "specification_mismatch"

    if typed:
        pool = typed
        if query_spec_tokens:
            pool = [choice for choice in typed if choice in spec_matched]
            if not pool:
                return None, "specification_mismatch"
    else:
        cluster_type_tokens = [
            token for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", cluster_norm)
            if len(token) >= 2
        ]
        compatible = [
            choice for choice in choices
            if (
                cluster_type_tokens
                and any(
                    token in normalize_text(choice.get("material_name"))
                    for token in cluster_type_tokens
                )
            )
        ]
        if compatible:
            pool = compatible
        elif spec_matched:
            # A unique source row plus a matching size/model can safely link a
            # broad standard type (e.g. PPR 接头) to a narrower review family.
            pool = spec_matched
        else:
            return None, "standard_type_mismatch"

    def name_score(choice: dict[str, Any]) -> tuple[int, int]:
        material_norm = normalize_text(choice.get("material_name"))
        standard_norm = normalize_text(choice.get("standard_type"))
        exact = int(bool(query_norm and query_norm in material_norm))
        type_match = int(bool(cluster_norm and standard_norm == cluster_norm))
        return exact, type_match

    scored = sorted(pool, key=lambda choice: name_score(choice), reverse=True)
    if not scored:
        return None, "unmatched_source_row"
    best_score = name_score(scored[0])
    best = [choice for choice in scored if name_score(choice) == best_score]
    if len(best) != 1:
        return None, "ambiguous_source_row"
    return best[0], "source_row_and_standard_type"


def load_current_linked_cases(
    clusters_path: str | Path = DEFAULT_CURRENT_LINKED_CLUSTERS_PATH,
    placements_path: str | Path = DEFAULT_CURRENT_PLACEMENTS_PATH,
    item_code_map_path: str | Path = DEFAULT_CURRENT_ITEM_MAP_PATH,
) -> list[dict[str, Any]]:
    """Build review cases from frequency clusters linked to numeric SKUs.

    This is intentionally a conservative benchmark: only rows whose original
    source reference can be linked to exactly one current numeric placement are
    emitted. The other 1,273-line history remains a review queue, not a false
    accuracy label.
    """

    by_source = _placement_source_index(placements_path, item_code_map_path)
    cases: list[dict[str, Any]] = []
    with Path(clusters_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            cluster = json.loads(line)
            names = cluster.get("raw_names") or []
            source_rows = cluster.get("source_rows") or []
            cluster_type = str(cluster.get("standard_type_candidate") or "").strip()
            for index, raw_name in enumerate(names):
                if index >= len(source_rows) or not str(raw_name or "").strip():
                    continue
                try:
                    source_row = int(source_rows[index])
                except (TypeError, ValueError):
                    continue
                cluster_records = normalize_source_records(cluster.get("source_records"))
                if cluster_records:
                    matching_records = [
                        record for record in cluster_records
                        if int(record.get("source_row") or 0) == source_row
                    ]
                else:
                    matching_records = [make_source_record(
                        source_row,
                        dataset=str(cluster.get("source_dataset") or DEFAULT_SOURCE_DATASET),
                        document=str(cluster.get("source_document") or DEFAULT_SOURCE_DOCUMENT),
                        sheet=str(cluster.get("source_sheet") or DEFAULT_SOURCE_SHEET),
                    )]
                if not matching_records:
                    continue
                source_candidates = [
                    placement
                    for record in matching_records
                    for placement in by_source.get(source_record_key(record), [])
                    if source_record_matches(record, placement.get("_source_record") or {})
                ]
                placement, link_status = _linked_placement(
                    str(raw_name), cluster_type,
                    source_candidates,
                )
                if placement is None:
                    continue
                cases.append({
                    "query": str(raw_name).strip(),
                    "specs": {},
                    "expected_top_item_code": placement["item_code"],
                    "expected_top_item_name": placement.get("material_name", ""),
                    "cluster_id": str(cluster.get("cluster_id") or ""),
                    "cluster_standard_type": cluster_type,
                    "source_row": source_row,
                    "link_status": link_status,
                    "label_status": "silver_unreviewed",
                    "evaluation_label": "linked_provisional",
                    "source_identity": matching_records[0],
                })
    # Keep one case per complete source identity/SKU/query so a repeated
    # cluster alias cannot dominate the benchmark.  In particular, row 47 in
    # two different source documents remains two independent review cases.
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for case in cases:
        identity = case.get("source_identity") or {}
        key = (
            identity.get("source_dataset", ""),
            identity.get("source_document", ""),
            identity.get("source_sheet", ""),
            identity.get("source_row", case["source_row"]),
            identity.get("source_row_hash", ""),
            case["expected_top_item_code"],
            case["query"],
        )
        unique.setdefault(key, case)
    return list(unique.values())


def resolver_for_catalog(catalog: str, *, vector_mode: str = "shadow") -> ReleaseMaterialResolver:
    if catalog == "current":
        rows = load_current_published_catalog()
        if not rows:
            raise RuntimeError("当前 GPC/ERPNext 发布目录为空或映射文件不存在。")
        return ReleaseMaterialResolver.from_rows(
            rows,
            catalog_path="<current-published-gpc-catalog>",
            vector_mode=vector_mode,  # type: ignore[arg-type]
        )
    return ReleaseMaterialResolver(DEFAULT_RELEASE_CATALOG_PATH, vector_mode=vector_mode)  # type: ignore[arg-type]


def lexical_top_codes(resolver: ReleaseMaterialResolver, query: str, specs: dict[str, Any], limit: int = 10) -> list[str]:
    scored = [score_release_row(row, query, specs) for row in resolver.rows]
    scored = [candidate for candidate in scored if candidate.score > 0]
    scored.sort(key=lambda candidate: (-candidate.match_tier, -candidate.score, candidate.item_code))
    return [candidate.item_code for candidate in scored[:limit]]


def evaluate(cases: list[dict[str, Any]], resolver: ReleaseMaterialResolver) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    lexical_latencies: list[float] = []
    shadow_latencies: list[float] = []
    ranking_changed = 0
    vector_only_recall_cases = 0
    vector_signal_cases = 0
    expected_name_covered = 0
    expected_code_cases = 0
    lexical_top1_code_hits = 0
    shadow_top1_code_hits = 0
    lexical_recall5_code_hits = 0
    shadow_recall5_code_hits = 0

    for case in cases:
        query = str(case.get("query") or "")
        specs = case.get("specs") or {}
        expected_name = normalize_text(case.get("expected_top_item_name") or "")
        if expected_name and any(
            expected_name in normalize_text(row.get("item_name") or "")
            or expected_name in normalize_text(row.get("sku_name") or "")
            for row in resolver.rows
        ):
            expected_name_covered += 1
        started = perf_counter()
        baseline_codes = lexical_top_codes(resolver, query, specs)
        lexical_latencies.append((perf_counter() - started) * 1000)
        started = perf_counter()
        vector_scores = resolver.vector_scores(query, specs)
        result = resolver.resolve(query, specs=specs, limit=10, _vector_scores=vector_scores)
        shadow_latencies.append((perf_counter() - started) * 1000)
        candidates = result.get("candidates") or []
        shadow_codes = [str(candidate.get("item_code") or "") for candidate in candidates]
        expected_code = str(case.get("expected_top_item_code") or "")
        if expected_code:
            expected_code_cases += 1
            lexical_top1_code_hits += int(bool(baseline_codes and baseline_codes[0] == expected_code))
            shadow_top1_code_hits += int(bool(shadow_codes and shadow_codes[0] == expected_code))
            lexical_recall5_code_hits += int(expected_code in baseline_codes[:5])
            shadow_recall5_code_hits += int(expected_code in shadow_codes[:5])
        vector_only_matches = sorted(
            ((score, code) for code, score in vector_scores.items() if score >= 0.42),
            key=lambda item: (-item[0], item[1]),
        )
        if not baseline_codes and vector_only_matches:
            vector_only_recall_cases += 1
        if baseline_codes and shadow_codes and baseline_codes[0] != shadow_codes[0]:
            ranking_changed += 1
        if any(score >= 0.42 for score in vector_scores.values()):
            vector_signal_cases += 1
        rows.append(
            {
                "query": query,
                "baseline_top": baseline_codes[:3],
                "shadow_top": shadow_codes[:3],
                "status": result.get("status"),
                "top_score": result.get("top_score", 0),
                "vector_scores": [candidate.get("vector_score", 0) for candidate in candidates[:3]],
                "vector_only_review_matches": [code for _score, code in vector_only_matches[:3]],
                "expected_top_item_code": case.get("expected_top_item_code", ""),
                "expected_top_item_name": case.get("expected_top_item_name", ""),
            }
        )

    return {
        "case_count": len(cases),
        "catalog_count": len(resolver.rows),
        "vector_mode": "shadow",
        "ranking_changed_count": ranking_changed,
        "vector_signal_case_count": vector_signal_cases,
        "vector_only_recall_case_count": vector_only_recall_cases,
        "expected_name_coverage_count": expected_name_covered,
        "expected_name_coverage_rate": round(expected_name_covered / len(cases), 4) if cases else 0,
        "linked_code_case_count": expected_code_cases,
        "linked_code_metrics": {
            "lexical_top1_hits": lexical_top1_code_hits,
            "lexical_top1_rate": round(lexical_top1_code_hits / expected_code_cases, 4) if expected_code_cases else 0,
            "shadow_top1_hits": shadow_top1_code_hits,
            "shadow_top1_rate": round(shadow_top1_code_hits / expected_code_cases, 4) if expected_code_cases else 0,
            "lexical_recall5_hits": lexical_recall5_code_hits,
            "lexical_recall5_rate": round(lexical_recall5_code_hits / expected_code_cases, 4) if expected_code_cases else 0,
            "shadow_recall5_hits": shadow_recall5_code_hits,
            "shadow_recall5_rate": round(shadow_recall5_code_hits / expected_code_cases, 4) if expected_code_cases else 0,
        },
        "latency_ms": {
            "lexical_median": round(median(lexical_latencies), 3) if lexical_latencies else 0,
            "shadow_median": round(median(shadow_latencies), 3) if shadow_latencies else 0,
        },
        "cases": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", choices=("legacy", "current"), default="current")
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH))
    parser.add_argument(
        "--linked-current",
        action="store_true",
        help="从 1,273 条频次聚类中构建保守的当前数字 SKU 链接评估集",
    )
    parser.add_argument(
        "--review-set",
        default=str(DEFAULT_REVIEW_SET_PATH),
        help="人工复核队列，用于输出向量维护门槛状态",
    )
    args = parser.parse_args()
    cases = load_current_linked_cases() if args.linked_current else load_cases(args.cases)
    report = evaluate(cases, resolver_for_catalog(args.catalog, vector_mode="shadow"))
    report["catalog"] = args.catalog
    report["case_source"] = "current_linked_clusters" if args.linked_current else str(args.cases)
    report["vector_maintenance_gate"] = review_gate_status(args.review_set)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
