from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "material_purchase_2024"
DEFAULT_MERGED_CATALOG_PATH = DEFAULT_DATA_DIR / "merged_standard_item_catalog.csv"
DEFAULT_RESOLVED_CATALOG_PATH = DEFAULT_DATA_DIR / "resolved_standard_item_catalog.csv"
DEFAULT_RESOLUTION_QUEUE_PATH = DEFAULT_DATA_DIR / "material_conflict_resolution_queue.csv"
DEFAULT_CONFLICTS_PATH = DEFAULT_DATA_DIR / "merge_conflicts.csv"
DEFAULT_ITEMS_PATH = DEFAULT_DATA_DIR / "material_catalog_composition_items.csv"
DEFAULT_BREAKDOWN_PATH = DEFAULT_DATA_DIR / "material_catalog_composition_breakdown.csv"
DEFAULT_SUMMARY_PATH = DEFAULT_DATA_DIR / "material_catalog_composition_summary.json"


ITEM_FIELDS = [
    "merged_item_code",
    "standard_name",
    "canonical_group_path",
    "specs",
    "unit",
    "source_count",
    "source_candidate_count",
    "merge_source_type",
    "merge_reason",
    "merge_confidence",
    "confidence_bucket",
    "needs_human_review",
    "note_has_open_question",
    "related_conflict_types",
    "resolution_issue_types",
    "composition_bucket",
    "composition_reason",
    "source_rows",
    "alias_names",
]

BREAKDOWN_FIELDS = [
    "section",
    "key",
    "label",
    "count",
    "percent",
    "description",
]

OPEN_QUESTION_MARKERS = ("?", "？", "是否", "需不需要", "需要区分", "未说明", "疑似", "原文")
IMPORT_READY_LABELS = {
    "ready": ("可导入-直接可用", "无阻塞冲突且不需要人工复核。"),
    "ready_distinct_specs": ("可导入-按规格拆分", "同名同分组下存在多个规格，已按规格保留为独立物料。"),
}
ISSUE_LABELS = {
    "alias_conflict": ("冲突-别名一对多", "同一个原始叫法命中多个候选，检索或建档时必须确认。"),
    "unit_conflict": ("冲突-单位不一致", "同名同规格存在非同义单位，需要补单位换算或拆分。"),
    "low_precision_conflict": ("冲突-低精度", "低精度/缺规格项与高精度项并存，需要补齐规格。"),
    "specs_conflict": ("冲突-规格需确认", "同名同分组存在多个规格签名，需要确认是否均为独立物料。"),
}


def normalize_for_key(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").strip().lower()
    text = text.replace("（", "(").replace("）", ")")
    return re.sub(r"\s+", "", text)


def parse_bool(value: str) -> bool:
    return normalize_for_key(value) in {"1", "true", "yes", "y", "是", "需要", "需复核"}


def parse_float(value: str, default: float = 0.0) -> float:
    try:
        return float((value or "").strip())
    except ValueError:
        return default


def split_multi(value: str) -> list[str]:
    text = unicodedata.normalize("NFKC", value or "").strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"\s*(?:[;；|])\s*", text) if part.strip()]


def dedupe_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = (value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def join_values(values: Iterable[str], separator: str = "；") -> str:
    return separator.join(dedupe_keep_order(values))


def sorted_codes(codes: Iterable[str]) -> list[str]:
    def code_key(code: str) -> tuple[str, int, str]:
        match = re.search(r"(\d+)$", code)
        if match:
            return (code[: match.start()], int(match.group(1)), code)
        return (code, -1, code)

    return sorted({code for code in codes if code}, key=code_key)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def source_to_merged_map(merged_rows: list[dict[str, str]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in merged_rows:
        merged_code = row["merged_item_code"]
        for source_code in split_multi(row.get("merged_from_codes", "")):
            mapping[source_code] = merged_code
        mapping[merged_code] = merged_code
    return mapping


def map_conflict_types_by_code(
    conflicts: list[dict[str, str]],
    source_to_merged: dict[str, str],
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for conflict in conflicts:
        conflict_type = conflict.get("conflict_type", "")
        for raw_code in split_multi(conflict.get("candidate_codes", "")):
            result[source_to_merged.get(raw_code, raw_code)].add(conflict_type)
    return result


def map_issue_types_by_code(queue_rows: list[dict[str, str]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for row in queue_rows:
        issue_type = row.get("issue_type", "")
        for code in split_multi(row.get("candidate_codes", "")):
            result[code].add(issue_type)
    return result


def has_open_question(value: str) -> bool:
    text = value or ""
    return any(marker in text for marker in OPEN_QUESTION_MARKERS)


def confidence_bucket(value: str) -> str:
    confidence = parse_float(value)
    if confidence >= 0.95:
        return "高置信度 >= 0.95"
    if confidence >= 0.9:
        return "中高置信度 0.90-0.94"
    if confidence >= 0.7:
        return "低置信度 0.70-0.89"
    return "极低置信度 < 0.70"


def merge_source_type(row: dict[str, str]) -> str:
    source_count = len(split_multi(row.get("merged_from_codes", "")))
    if source_count > 1:
        return "多条候选自动合并"
    if "exact_name_group_unit_specs" in row.get("merge_reason", ""):
        return "多条候选自动合并"
    return "单条候选保留"


def classify_primary_bucket(
    row: dict[str, str],
    resolved_by_code: dict[str, dict[str, str]],
    conflict_types: set[str],
    issue_types: set[str],
) -> tuple[str, str]:
    code = row["merged_item_code"]
    if code in resolved_by_code:
        status = resolved_by_code[code].get("resolution_status", "")
        return IMPORT_READY_LABELS.get(status, ("可导入-其他", "已进入可导入池。"))

    if parse_bool(row.get("needs_human_review", "")):
        return "需复核-人工标记", "合并候选已带 needs_human_review=true。"

    if has_open_question(row.get("notes", "")):
        return "需复核-备注问题", "备注中仍有待确认问题。"

    for issue_type in ("alias_conflict", "unit_conflict", "low_precision_conflict", "specs_conflict"):
        if issue_type in issue_types or issue_type in conflict_types:
            return ISSUE_LABELS[issue_type]

    if parse_float(row.get("merge_confidence", "0")) < 0.9:
        return "需复核-低置信度", "合并置信度低于 0.90。"

    return "待治理-未归类", "未进入可导入池，也没有命中已知主分类。"


def top_group(path: str) -> str:
    return (path or "未分组").split("/", 1)[0] or "未分组"


def build_item_rows(
    merged_rows: list[dict[str, str]],
    resolved_rows: list[dict[str, str]],
    queue_rows: list[dict[str, str]],
    conflicts: list[dict[str, str]],
) -> list[dict[str, str]]:
    resolved_by_code = {row["merged_item_code"]: row for row in resolved_rows}
    source_to_merged = source_to_merged_map(merged_rows)
    conflict_types_by_code = map_conflict_types_by_code(conflicts, source_to_merged)
    issue_types_by_code = map_issue_types_by_code(queue_rows)
    items: list[dict[str, str]] = []

    for row in merged_rows:
        code = row["merged_item_code"]
        conflict_types = conflict_types_by_code.get(code, set())
        issue_types = issue_types_by_code.get(code, set())
        bucket, reason = classify_primary_bucket(row, resolved_by_code, conflict_types, issue_types)
        source_codes = split_multi(row.get("merged_from_codes", ""))
        items.append(
            {
                "merged_item_code": code,
                "standard_name": row.get("standard_name", ""),
                "canonical_group_path": row.get("canonical_group_path", ""),
                "specs": row.get("specs", ""),
                "unit": row.get("unit", ""),
                "source_count": row.get("source_count", ""),
                "source_candidate_count": str(len(source_codes) or 1),
                "merge_source_type": merge_source_type(row),
                "merge_reason": row.get("merge_reason", ""),
                "merge_confidence": row.get("merge_confidence", ""),
                "confidence_bucket": confidence_bucket(row.get("merge_confidence", "")),
                "needs_human_review": row.get("needs_human_review", ""),
                "note_has_open_question": "true" if has_open_question(row.get("notes", "")) else "false",
                "related_conflict_types": join_values(sorted(conflict_types)),
                "resolution_issue_types": join_values(sorted(issue_types)),
                "composition_bucket": bucket,
                "composition_reason": reason,
                "source_rows": row.get("source_rows", ""),
                "alias_names": row.get("alias_names", ""),
            }
        )
    return items


def add_breakdown_rows(
    rows: list[dict[str, str]],
    section: str,
    counter: Counter[str],
    total: int,
    descriptions: dict[str, str] | None = None,
) -> None:
    descriptions = descriptions or {}
    for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
        rows.append(
            {
                "section": section,
                "key": key,
                "label": key,
                "count": str(count),
                "percent": f"{(count / total * 100):.2f}%" if total else "0.00%",
                "description": descriptions.get(key, ""),
            }
        )


def build_breakdown_rows(item_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    total = len(item_rows)
    rows: list[dict[str, str]] = []

    add_breakdown_rows(
        rows,
        "主分类",
        Counter(row["composition_bucket"] for row in item_rows),
        total,
        {label: description for label, description in [*IMPORT_READY_LABELS.values(), *ISSUE_LABELS.values()]},
    )
    add_breakdown_rows(rows, "合并来源", Counter(row["merge_source_type"] for row in item_rows), total)
    add_breakdown_rows(rows, "置信度", Counter(row["confidence_bucket"] for row in item_rows), total)
    add_breakdown_rows(
        rows,
        "人工复核标记",
        Counter("需要复核" if parse_bool(row["needs_human_review"]) else "无需复核" for row in item_rows),
        total,
    )
    add_breakdown_rows(
        rows,
        "备注问题",
        Counter("备注有待确认问题" if row["note_has_open_question"] == "true" else "备注无开放问题" for row in item_rows),
        total,
    )
    add_breakdown_rows(
        rows,
        "一级分组",
        Counter(top_group(row["canonical_group_path"]) for row in item_rows),
        total,
    )

    conflict_counter: Counter[str] = Counter()
    for row in item_rows:
        conflict_types = split_multi(row["related_conflict_types"])
        if not conflict_types:
            conflict_counter["无冲突"] += 1
            continue
        for conflict_type in conflict_types:
            conflict_counter[conflict_type] += 1
    add_breakdown_rows(
        rows,
        "冲突类型",
        conflict_counter,
        total,
        {
            "specs_conflict": "规格冲突，可能是不同规格物料，也可能需要人工确认。",
            "low_precision_conflict": "低精度与高精度候选并存。",
            "unit_conflict": "单位不一致。",
            "alias_conflict": "别名命中多个候选。",
            "无冲突": "没有被 merge_conflicts.csv 标记。",
        },
    )
    return rows


def summarize_material_catalog_composition(
    merged_catalog_path: Path = DEFAULT_MERGED_CATALOG_PATH,
    resolved_catalog_path: Path = DEFAULT_RESOLVED_CATALOG_PATH,
    resolution_queue_path: Path = DEFAULT_RESOLUTION_QUEUE_PATH,
    conflicts_path: Path = DEFAULT_CONFLICTS_PATH,
    items_path: Path = DEFAULT_ITEMS_PATH,
    breakdown_path: Path = DEFAULT_BREAKDOWN_PATH,
    summary_path: Path = DEFAULT_SUMMARY_PATH,
) -> dict[str, object]:
    merged_rows = read_csv(merged_catalog_path)
    resolved_rows = read_csv(resolved_catalog_path)
    queue_rows = read_csv(resolution_queue_path)
    conflicts = read_csv(conflicts_path)

    item_rows = build_item_rows(merged_rows, resolved_rows, queue_rows, conflicts)
    breakdown_rows = build_breakdown_rows(item_rows)
    write_csv(items_path, ITEM_FIELDS, item_rows)
    write_csv(breakdown_path, BREAKDOWN_FIELDS, breakdown_rows)

    primary_counts = Counter(row["composition_bucket"] for row in item_rows)
    summary = {
        "merged_rows": len(merged_rows),
        "composition_items": len(item_rows),
        "breakdown_rows": len(breakdown_rows),
        "primary_bucket_counts": dict(primary_counts),
        "primary_bucket_total": sum(primary_counts.values()),
        "source_type_counts": dict(Counter(row["merge_source_type"] for row in item_rows)),
        "confidence_bucket_counts": dict(Counter(row["confidence_bucket"] for row in item_rows)),
        "needs_human_review_count": sum(1 for row in item_rows if parse_bool(row["needs_human_review"])),
        "note_open_question_count": sum(1 for row in item_rows if row["note_has_open_question"] == "true"),
        "outputs": {
            "items": str(items_path),
            "breakdown": str(breakdown_path),
            "summary": str(summary_path),
        },
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize the composition of merged material catalog candidates.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--merged-catalog", type=Path, default=None)
    parser.add_argument("--resolved-catalog", type=Path, default=None)
    parser.add_argument("--resolution-queue", type=Path, default=None)
    parser.add_argument("--conflicts", type=Path, default=None)
    parser.add_argument("--items", type=Path, default=None)
    parser.add_argument("--breakdown", type=Path, default=None)
    parser.add_argument("--summary", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_dir = args.data_dir
    summary = summarize_material_catalog_composition(
        merged_catalog_path=args.merged_catalog or data_dir / "merged_standard_item_catalog.csv",
        resolved_catalog_path=args.resolved_catalog or data_dir / "resolved_standard_item_catalog.csv",
        resolution_queue_path=args.resolution_queue or data_dir / "material_conflict_resolution_queue.csv",
        conflicts_path=args.conflicts or data_dir / "merge_conflicts.csv",
        items_path=args.items or data_dir / "material_catalog_composition_items.csv",
        breakdown_path=args.breakdown or data_dir / "material_catalog_composition_breakdown.csv",
        summary_path=args.summary or data_dir / "material_catalog_composition_summary.json",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
