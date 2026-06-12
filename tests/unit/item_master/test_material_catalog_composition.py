import csv
import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "summarize_material_catalog_composition.py"
SPEC = importlib.util.spec_from_file_location("summarize_material_catalog_composition", SCRIPT_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


MERGED_FIELDS = [
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

RESOLVED_FIELDS = [
    *MERGED_FIELDS,
    "import_ready",
    "resolution_status",
    "resolution_reason",
    "related_conflict_types",
    "blocking_conflict_types",
]

QUEUE_FIELDS = [
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

CONFLICT_FIELDS = [
    "conflict_type",
    "standard_name",
    "canonical_group_path",
    "unit_values",
    "specs_values",
    "candidate_codes",
    "source_rows",
    "reason",
]


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def merged_row(
    code: str,
    name: str,
    specs: str,
    needs_review: str = "false",
    notes: str = "",
) -> dict[str, str]:
    return {
        "merged_item_code": code,
        "standard_name": name,
        "reviewed_group_paths": "五金备件/其他/紧固件",
        "canonical_group_path": "五金备件/其他/紧固件",
        "specs": specs,
        "unit": "个",
        "source_count": "1",
        "source_statuses": "可建档",
        "alias_names": name,
        "source_rows": "Sheet1:1",
        "notes": notes,
        "merged_from_codes": code,
        "merge_reason": "single_candidate",
        "merge_confidence": "1.00",
        "needs_human_review": needs_review,
    }


def resolved_row(row: dict[str, str], status: str = "ready") -> dict[str, str]:
    return {
        **row,
        "import_ready": "true",
        "resolution_status": status,
        "resolution_reason": "测试可导入",
        "related_conflict_types": "",
        "blocking_conflict_types": "",
    }


def queue_row(issue_type: str, code: str) -> dict[str, str]:
    return {
        "issue_id": f"ISSUE-{code}",
        "issue_type": issue_type,
        "priority": "medium",
        "standard_name": "测试物料",
        "canonical_group_path": "五金备件/其他/紧固件",
        "candidate_codes": code,
        "source_proposed_codes": code,
        "source_rows": "Sheet1:1",
        "unit_values": "个",
        "specs_values": "规格: A",
        "reason": "测试队列",
        "suggested_action": "测试建议",
    }


def conflict_row(conflict_type: str, code: str) -> dict[str, str]:
    return {
        "conflict_type": conflict_type,
        "standard_name": "测试物料",
        "canonical_group_path": "五金备件/其他/紧固件",
        "unit_values": "个",
        "specs_values": "规格: A",
        "candidate_codes": code,
        "source_rows": "Sheet1:1",
        "reason": "测试冲突",
    }


def run_summary(
    tmp_path: Path,
    merged_rows: list[dict[str, str]],
    resolved_rows: list[dict[str, str]],
    queue_rows: list[dict[str, str]],
    conflict_rows: list[dict[str, str]],
):
    merged_path = tmp_path / "merged.csv"
    resolved_path = tmp_path / "resolved.csv"
    queue_path = tmp_path / "queue.csv"
    conflicts_path = tmp_path / "conflicts.csv"
    items_path = tmp_path / "items.csv"
    breakdown_path = tmp_path / "breakdown.csv"
    summary_path = tmp_path / "summary.json"

    write_csv(merged_path, MERGED_FIELDS, merged_rows)
    write_csv(resolved_path, RESOLVED_FIELDS, resolved_rows)
    write_csv(queue_path, QUEUE_FIELDS, queue_rows)
    write_csv(conflicts_path, CONFLICT_FIELDS, conflict_rows)

    summary = module.summarize_material_catalog_composition(
        merged_catalog_path=merged_path,
        resolved_catalog_path=resolved_path,
        resolution_queue_path=queue_path,
        conflicts_path=conflicts_path,
        items_path=items_path,
        breakdown_path=breakdown_path,
        summary_path=summary_path,
    )
    return summary, read_csv(items_path), read_csv(breakdown_path)


def test_primary_bucket_counts_sum_to_merged_total(tmp_path: Path) -> None:
    ready = merged_row("REVIEW-MAT-00001", "热缩管", "规格: 3CM")
    human = merged_row("REVIEW-MAT-00002", "门锁", "规格型号缺失", needs_review="true")
    alias = merged_row("REVIEW-MAT-00003", "螺丝", "规格: 10*40")

    summary, items, _breakdown = run_summary(
        tmp_path,
        [ready, human, alias],
        [resolved_row(ready)],
        [queue_row("alias_conflict", "REVIEW-MAT-00003")],
        [conflict_row("alias_conflict", "REVIEW-MAT-00003")],
    )

    assert summary["merged_rows"] == 3
    assert summary["primary_bucket_total"] == 3
    assert {item["composition_bucket"] for item in items} == {
        "可导入-直接可用",
        "需复核-人工标记",
        "冲突-别名一对多",
    }


def test_open_question_notes_have_their_own_bucket(tmp_path: Path) -> None:
    row = merged_row("REVIEW-MAT-00001", "灯管", "功率: 36W", notes="需不需要区分 LED/荧光灯？")

    summary, items, breakdown = run_summary(tmp_path, [row], [], [], [])

    assert summary["note_open_question_count"] == 1
    assert items[0]["composition_bucket"] == "需复核-备注问题"
    assert any(item["section"] == "备注问题" and item["key"] == "备注有待确认问题" for item in breakdown)


def test_exact_merge_source_type_is_reported(tmp_path: Path) -> None:
    row = merged_row("REVIEW-MAT-00001", "热缩管", "规格: 30mm")
    row["merged_from_codes"] = "REVIEW-MAT-00001；REVIEW-MAT-00002"
    row["merge_reason"] = "exact_name_group_unit_specs"

    _summary, items, _breakdown = run_summary(tmp_path, [row], [resolved_row(row, "ready_distinct_specs")], [], [])

    assert items[0]["source_candidate_count"] == "2"
    assert items[0]["merge_source_type"] == "多条候选自动合并"
    assert items[0]["composition_bucket"] == "可导入-按规格拆分"
