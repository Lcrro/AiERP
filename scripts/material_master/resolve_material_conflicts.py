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
DEFAULT_MERGED_ALIASES_PATH = DEFAULT_DATA_DIR / "merged_item_aliases.csv"
DEFAULT_CONFLICTS_PATH = DEFAULT_DATA_DIR / "merge_conflicts.csv"
DEFAULT_RESOLVED_CATALOG_PATH = DEFAULT_DATA_DIR / "resolved_standard_item_catalog.csv"
DEFAULT_RESOLUTION_QUEUE_PATH = DEFAULT_DATA_DIR / "material_conflict_resolution_queue.csv"
DEFAULT_ALIAS_CONTEXT_PATH = DEFAULT_DATA_DIR / "material_alias_context_map.csv"
DEFAULT_SUMMARY_PATH = DEFAULT_DATA_DIR / "material_conflict_resolution_summary.json"


MERGED_CATALOG_FIELDS = [
    "merged_item_code",
    "standard_name",
    "reviewed_group_paths",
    "canonical_group_path",
    "specs",
    "unit",
    "source_count",
    "source_statuses",
    "alias_names",
    "source_rows",
    "notes",
    "merged_from_codes",
    "merge_reason",
    "merge_confidence",
    "needs_human_review",
]

RESOLVED_CATALOG_FIELDS = [
    *MERGED_CATALOG_FIELDS,
    "import_ready",
    "resolution_status",
    "resolution_reason",
    "related_conflict_types",
    "blocking_conflict_types",
]

RESOLUTION_QUEUE_FIELDS = [
    "issue_id",
    "issue_type",
    "priority",
    "standard_name",
    "canonical_group_path",
    "candidate_codes",
    "source_proposed_codes",
    "source_rows",
    "unit_values",
    "specs_values",
    "reason",
    "suggested_action",
]

ALIAS_CONTEXT_FIELDS = [
    "raw_name",
    "normalized_raw_name",
    "candidate_count",
    "candidate_codes",
    "import_ready_candidate_codes",
    "requires_confirmation",
    "ambiguity_reason",
    "candidate_contexts",
]

NON_BLOCKING_CONFLICT_TYPES = {"specs_conflict"}
BLOCKING_CONFLICT_TYPES = {"unit_conflict", "alias_conflict", "low_precision_conflict"}
UNCERTAIN_NOTE_MARKERS = ("?", "？", "是否", "需不需要", "需要区分", "未说明", "疑似", "原文")


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


def conflict_codes(conflict: dict[str, str], source_to_merged: dict[str, str]) -> list[str]:
    codes = []
    for code in split_multi(conflict.get("candidate_codes", "")):
        codes.append(source_to_merged.get(code, code))
    return sorted_codes(codes)


def conflicts_by_code(
    conflicts: list[dict[str, str]],
    source_to_merged: dict[str, str],
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for conflict in conflicts:
        conflict_type = conflict.get("conflict_type", "")
        for code in conflict_codes(conflict, source_to_merged):
            result[code].add(conflict_type)
    return result


def classify_row(row: dict[str, str], conflict_types: set[str]) -> tuple[bool, str, str, str]:
    needs_review = parse_bool(row.get("needs_human_review", ""))
    confidence = parse_float(row.get("merge_confidence", "0"))
    blocking_types = sorted(conflict_types & BLOCKING_CONFLICT_TYPES)
    note_needs_review = has_uncertain_note(row.get("notes", ""))

    if needs_review:
        return (
            False,
            "needs_human_review",
            "该物料存在低精度、需复核分组或其他人工确认标记。",
            join_values(blocking_types or ["needs_human_review"]),
        )
    if note_needs_review:
        return (
            False,
            "needs_note_review",
            "备注中仍有待确认问题，暂不进入可导入池。",
            join_values(blocking_types or ["needs_note_review"]),
        )
    if confidence < 0.9:
        return (
            False,
            "low_merge_confidence",
            "合并置信度低于 0.90，暂不进入可导入池。",
            join_values(blocking_types or ["low_merge_confidence"]),
        )
    if blocking_types:
        return (
            False,
            "blocked_by_conflict",
            "该物料涉及单位、别名或低精度冲突，需要先治理。",
            join_values(blocking_types),
        )
    if conflict_types <= NON_BLOCKING_CONFLICT_TYPES and "specs_conflict" in conflict_types:
        return (
            True,
            "ready_distinct_specs",
            "同名同分组下存在多个规格，已按规格保留为独立物料。",
            "",
        )
    return True, "ready", "无阻塞冲突且不需要人工复核。", ""


def has_uncertain_note(value: str) -> bool:
    text = value or ""
    return any(marker in text for marker in UNCERTAIN_NOTE_MARKERS)


def build_resolved_rows(
    merged_rows: list[dict[str, str]],
    conflicts_by_merged_code: dict[str, set[str]],
) -> tuple[list[dict[str, str]], dict[str, tuple[bool, str, str, str]]]:
    resolved_rows: list[dict[str, str]] = []
    classifications: dict[str, tuple[bool, str, str, str]] = {}
    for row in merged_rows:
        code = row["merged_item_code"]
        related_types = conflicts_by_merged_code.get(code, set())
        import_ready, status, reason, blocking_types = classify_row(row, related_types)
        classifications[code] = (import_ready, status, reason, blocking_types)
        if not import_ready:
            continue
        resolved_rows.append(
            {
                **row,
                "import_ready": "true",
                "resolution_status": status,
                "resolution_reason": reason,
                "related_conflict_types": join_values(sorted(related_types)),
                "blocking_conflict_types": blocking_types,
            }
        )
    return resolved_rows, classifications


def is_auto_resolved_conflict(
    conflict: dict[str, str],
    source_to_merged: dict[str, str],
    classifications: dict[str, tuple[bool, str, str, str]],
) -> bool:
    if conflict.get("conflict_type") != "specs_conflict":
        return False
    codes = conflict_codes(conflict, source_to_merged)
    return bool(codes) and all(classifications.get(code, (False, "", "", ""))[0] for code in codes)


def build_resolution_queue(
    merged_rows: list[dict[str, str]],
    conflicts: list[dict[str, str]],
    source_to_merged: dict[str, str],
    classifications: dict[str, tuple[bool, str, str, str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    queued_codes: set[str] = set()

    for conflict in conflicts:
        if is_auto_resolved_conflict(conflict, source_to_merged, classifications):
            continue
        issue_type = conflict.get("conflict_type", "")
        source_codes = split_multi(conflict.get("candidate_codes", ""))
        merged_codes = conflict_codes(conflict, source_to_merged)
        queued_codes.update(merged_codes)
        rows.append(
            {
                "issue_id": f"ISSUE-{len(rows) + 1:05d}",
                "issue_type": issue_type,
                "priority": priority_for_issue(issue_type),
                "standard_name": conflict.get("standard_name", ""),
                "canonical_group_path": conflict.get("canonical_group_path", ""),
                "candidate_codes": join_values(merged_codes),
                "source_proposed_codes": join_values(sorted_codes(source_codes)),
                "source_rows": conflict.get("source_rows", ""),
                "unit_values": conflict.get("unit_values", ""),
                "specs_values": conflict.get("specs_values", ""),
                "reason": conflict.get("reason", ""),
                "suggested_action": suggested_action(issue_type),
            }
        )

    for row in merged_rows:
        code = row["merged_item_code"]
        import_ready, status, reason, blocking_types = classifications[code]
        if import_ready or code in queued_codes:
            continue
        rows.append(
            {
                "issue_id": f"ISSUE-{len(rows) + 1:05d}",
                "issue_type": status,
                "priority": priority_for_issue(status),
                "standard_name": row.get("standard_name", ""),
                "canonical_group_path": row.get("canonical_group_path", ""),
                "candidate_codes": code,
                "source_proposed_codes": row.get("merged_from_codes", ""),
                "source_rows": row.get("source_rows", ""),
                "unit_values": row.get("unit", ""),
                "specs_values": row.get("specs", ""),
                "reason": join_values([reason, row.get("notes", ""), blocking_types]),
                "suggested_action": suggested_action(status),
            }
        )

    return rows


def build_alias_context_rows(
    alias_rows: list[dict[str, str]],
    classifications: dict[str, tuple[bool, str, str, str]],
) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in alias_rows:
        raw_name = row.get("raw_name", "").strip()
        if raw_name:
            grouped[raw_name].append(row)

    rows: list[dict[str, str]] = []
    for raw_name, candidates in sorted(grouped.items(), key=lambda item: normalize_for_key(item[0])):
        candidate_codes = sorted_codes(row.get("merged_item_code", "") for row in candidates)
        import_ready_codes = [
            code for code in candidate_codes if classifications.get(code, (False, "", "", ""))[0]
        ]
        requires_confirmation = len(candidate_codes) > 1 or len(import_ready_codes) != len(candidate_codes)
        ambiguity_reason = alias_ambiguity_reason(candidate_codes, import_ready_codes)
        contexts = []
        for row in candidates:
            contexts.append(
                " | ".join(
                    [
                        row.get("merged_item_code", ""),
                        row.get("standard_name", ""),
                        row.get("canonical_group_path", ""),
                        row.get("specs", ""),
                        row.get("unit", ""),
                    ]
                )
            )
        rows.append(
            {
                "raw_name": raw_name,
                "normalized_raw_name": normalize_for_key(raw_name),
                "candidate_count": str(len(candidate_codes)),
                "candidate_codes": join_values(candidate_codes),
                "import_ready_candidate_codes": join_values(import_ready_codes),
                "requires_confirmation": "true" if requires_confirmation else "false",
                "ambiguity_reason": ambiguity_reason,
                "candidate_contexts": " || ".join(dedupe_keep_order(contexts)),
            }
        )
    return rows


def alias_ambiguity_reason(candidate_codes: list[str], import_ready_codes: list[str]) -> str:
    if len(candidate_codes) > 1:
        return "同一原始叫法命中多个候选；Agent 检索时必须结合规格、分组、用途让用户确认。"
    if len(import_ready_codes) != len(candidate_codes):
        return "唯一候选暂未进入可导入池；需要先完成物料治理。"
    return "唯一可导入候选。"


def priority_for_issue(issue_type: str) -> str:
    if issue_type in {"alias_conflict", "unit_conflict"}:
        return "high"
    if issue_type in {"low_precision_conflict", "needs_human_review", "needs_note_review", "low_merge_confidence"}:
        return "medium"
    if issue_type == "specs_conflict":
        return "medium"
    return "low"


def suggested_action(issue_type: str) -> str:
    actions = {
        "specs_conflict": "逐项确认是否为不同规格物料；若规格足够明确则保留拆分，若其实同物料则补充等价规则后再合并。",
        "unit_conflict": "确认是否同一物料的不同计量单位；如是则补 UOM 换算/包装规格，如不是则拆成不同物料。",
        "alias_conflict": "不要强行唯一化；保留多个候选，检索或建档时按规格、用途、品牌让用户确认。",
        "low_precision_conflict": "补齐规格、品牌、型号、包装或执行标准后再进入可导入池。",
        "needs_human_review": "按备注补齐缺失信息，或确认该分组是否应继续保留人工复核。",
        "needs_note_review": "先回答备注中的问题，确认规格、用途、品牌或型号后再进入可导入池。",
        "low_merge_confidence": "人工确认合并依据，必要时拆分为独立物料。",
    }
    return actions.get(issue_type, "人工确认后再决定导入、拆分或合并。")


def resolve_material_conflicts(
    merged_catalog_path: Path = DEFAULT_MERGED_CATALOG_PATH,
    merged_aliases_path: Path = DEFAULT_MERGED_ALIASES_PATH,
    conflicts_path: Path = DEFAULT_CONFLICTS_PATH,
    resolved_catalog_path: Path = DEFAULT_RESOLVED_CATALOG_PATH,
    resolution_queue_path: Path = DEFAULT_RESOLUTION_QUEUE_PATH,
    alias_context_path: Path = DEFAULT_ALIAS_CONTEXT_PATH,
    summary_path: Path = DEFAULT_SUMMARY_PATH,
) -> dict[str, object]:
    merged_rows = read_csv(merged_catalog_path)
    alias_rows = read_csv(merged_aliases_path)
    conflicts = read_csv(conflicts_path)
    source_to_merged = source_to_merged_map(merged_rows)
    conflict_map = conflicts_by_code(conflicts, source_to_merged)

    resolved_rows, classifications = build_resolved_rows(merged_rows, conflict_map)
    queue_rows = build_resolution_queue(merged_rows, conflicts, source_to_merged, classifications)
    alias_context_rows = build_alias_context_rows(alias_rows, classifications)

    write_csv(resolved_catalog_path, RESOLVED_CATALOG_FIELDS, resolved_rows)
    write_csv(resolution_queue_path, RESOLUTION_QUEUE_FIELDS, queue_rows)
    write_csv(alias_context_path, ALIAS_CONTEXT_FIELDS, alias_context_rows)

    auto_resolved_conflicts = sum(
        1 for conflict in conflicts if is_auto_resolved_conflict(conflict, source_to_merged, classifications)
    )
    summary = {
        "merged_rows": len(merged_rows),
        "resolved_rows": len(resolved_rows),
        "resolution_queue_rows": len(queue_rows),
        "alias_context_rows": len(alias_context_rows),
        "source_conflicts": len(conflicts),
        "auto_resolved_conflicts": auto_resolved_conflicts,
        "unresolved_conflicts": len(conflicts) - auto_resolved_conflicts,
        "import_ready_ratio": round(len(resolved_rows) / len(merged_rows), 4) if merged_rows else 0,
        "source_conflict_types": dict(Counter(row.get("conflict_type", "") for row in conflicts)),
        "resolution_queue_issue_types": dict(Counter(row.get("issue_type", "") for row in queue_rows)),
        "outputs": {
            "resolved_catalog": str(resolved_catalog_path),
            "resolution_queue": str(resolution_queue_path),
            "alias_context": str(alias_context_path),
            "summary": str(summary_path),
        },
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve material merge conflicts into import-ready and review queues.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--merged-catalog", type=Path, default=None)
    parser.add_argument("--merged-aliases", type=Path, default=None)
    parser.add_argument("--conflicts", type=Path, default=None)
    parser.add_argument("--resolved-catalog", type=Path, default=None)
    parser.add_argument("--resolution-queue", type=Path, default=None)
    parser.add_argument("--alias-context", type=Path, default=None)
    parser.add_argument("--summary", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_dir = args.data_dir
    summary = resolve_material_conflicts(
        merged_catalog_path=args.merged_catalog or data_dir / "merged_standard_item_catalog.csv",
        merged_aliases_path=args.merged_aliases or data_dir / "merged_item_aliases.csv",
        conflicts_path=args.conflicts or data_dir / "merge_conflicts.csv",
        resolved_catalog_path=args.resolved_catalog or data_dir / "resolved_standard_item_catalog.csv",
        resolution_queue_path=args.resolution_queue or data_dir / "material_conflict_resolution_queue.csv",
        alias_context_path=args.alias_context or data_dir / "material_alias_context_map.csv",
        summary_path=args.summary or data_dir / "material_conflict_resolution_summary.json",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
