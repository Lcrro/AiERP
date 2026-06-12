import csv
import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "resolve_material_conflicts.py"
SPEC = importlib.util.spec_from_file_location("resolve_material_conflicts", SCRIPT_PATH)
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

ALIAS_FIELDS = [
    "raw_name",
    "merged_item_code",
    "standard_name",
    "canonical_group_path",
    "specs",
    "unit",
    "source_proposed_item_codes",
    "alias_source",
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
    unit: str = "个",
    group: str = "五金备件/其他/紧固件",
    needs_review: str = "false",
    confidence: str = "1.00",
    notes: str = "",
) -> dict[str, str]:
    return {
        "merged_item_code": code,
        "standard_name": name,
        "reviewed_group_paths": group,
        "canonical_group_path": group,
        "specs": specs,
        "unit": unit,
        "source_count": "1",
        "source_statuses": "可建档",
        "alias_names": name,
        "source_rows": "Sheet1:1",
        "notes": notes,
        "merged_from_codes": code,
        "merge_reason": "single_candidate",
        "merge_confidence": confidence,
        "needs_human_review": needs_review,
    }


def alias_row(raw_name: str, code: str, name: str, specs: str, unit: str = "个") -> dict[str, str]:
    return {
        "raw_name": raw_name,
        "merged_item_code": code,
        "standard_name": name,
        "canonical_group_path": "五金备件/其他/紧固件",
        "specs": specs,
        "unit": unit,
        "source_proposed_item_codes": code,
        "alias_source": "alias_names",
    }


def conflict_row(
    conflict_type: str,
    name: str,
    candidate_codes: str,
    specs: str,
    units: str = "个",
) -> dict[str, str]:
    return {
        "conflict_type": conflict_type,
        "standard_name": name,
        "canonical_group_path": "五金备件/其他/紧固件",
        "unit_values": units,
        "specs_values": specs,
        "candidate_codes": candidate_codes,
        "source_rows": "Sheet1:1；Sheet1:2",
        "reason": "测试冲突",
    }


def run_resolver(
    tmp_path: Path,
    merged_rows: list[dict[str, str]],
    alias_rows: list[dict[str, str]],
    conflict_rows: list[dict[str, str]],
):
    merged_path = tmp_path / "merged_standard_item_catalog.csv"
    aliases_path = tmp_path / "merged_item_aliases.csv"
    conflicts_path = tmp_path / "merge_conflicts.csv"
    resolved_path = tmp_path / "resolved_standard_item_catalog.csv"
    queue_path = tmp_path / "material_conflict_resolution_queue.csv"
    alias_context_path = tmp_path / "material_alias_context_map.csv"
    summary_path = tmp_path / "summary.json"

    write_csv(merged_path, MERGED_FIELDS, merged_rows)
    write_csv(aliases_path, ALIAS_FIELDS, alias_rows)
    write_csv(conflicts_path, CONFLICT_FIELDS, conflict_rows)

    summary = module.resolve_material_conflicts(
        merged_catalog_path=merged_path,
        merged_aliases_path=aliases_path,
        conflicts_path=conflicts_path,
        resolved_catalog_path=resolved_path,
        resolution_queue_path=queue_path,
        alias_context_path=alias_context_path,
        summary_path=summary_path,
    )
    return summary, read_csv(resolved_path), read_csv(queue_path), read_csv(alias_context_path)


def test_specs_conflict_with_clear_specs_is_auto_resolved_as_distinct_items(tmp_path: Path) -> None:
    summary, resolved, queue, _aliases = run_resolver(
        tmp_path,
        [
            merged_row("REVIEW-MAT-00001", "内六角螺丝", "规格: 10*40"),
            merged_row("REVIEW-MAT-00002", "内六角螺丝", "规格: 16*50"),
        ],
        [
            alias_row("10*40内六角", "REVIEW-MAT-00001", "内六角螺丝", "规格: 10*40"),
            alias_row("16*50内六角", "REVIEW-MAT-00002", "内六角螺丝", "规格: 16*50"),
        ],
        [
            conflict_row(
                "specs_conflict",
                "内六角螺丝",
                "REVIEW-MAT-00001；REVIEW-MAT-00002",
                "规格: 10*40 || 规格: 16*50",
            )
        ],
    )

    assert {row["merged_item_code"] for row in resolved} == {"REVIEW-MAT-00001", "REVIEW-MAT-00002"}
    assert {row["resolution_status"] for row in resolved} == {"ready_distinct_specs"}
    assert queue == []
    assert summary["auto_resolved_conflicts"] == 1


def test_unit_and_low_precision_conflicts_are_kept_out_of_import_ready_pool(tmp_path: Path) -> None:
    summary, resolved, queue, _aliases = run_resolver(
        tmp_path,
        [
            merged_row("REVIEW-MAT-00001", "水泥", "型号: P.O 42.5", "吨"),
            merged_row("REVIEW-MAT-00002", "水泥", "型号: P.O 42.5", "袋"),
            merged_row("REVIEW-MAT-00003", "水泥", "型号缺失", "袋", needs_review="true", confidence="0.70"),
        ],
        [
            alias_row("水泥", "REVIEW-MAT-00001", "水泥", "型号: P.O 42.5", "吨"),
            alias_row("水泥", "REVIEW-MAT-00002", "水泥", "型号: P.O 42.5", "袋"),
        ],
        [
            conflict_row(
                "unit_conflict",
                "水泥",
                "REVIEW-MAT-00001；REVIEW-MAT-00002",
                "型号: P.O 42.5",
                "吨；袋",
            ),
            conflict_row(
                "low_precision_conflict",
                "水泥",
                "REVIEW-MAT-00001；REVIEW-MAT-00003",
                "型号: P.O 42.5 || 型号缺失",
                "吨；袋",
            ),
        ],
    )

    assert resolved == []
    assert {row["issue_type"] for row in queue} == {"unit_conflict", "low_precision_conflict"}
    assert summary["resolution_queue_rows"] == 2
    assert summary["unresolved_conflicts"] == 2


def test_alias_context_marks_ambiguous_aliases_for_confirmation(tmp_path: Path) -> None:
    _summary, resolved, _queue, aliases = run_resolver(
        tmp_path,
        [
            merged_row("REVIEW-MAT-00001", "螺丝", "规格: 10*40"),
            merged_row("REVIEW-MAT-00002", "膨胀螺丝", "规格: M12*80"),
        ],
        [
            alias_row("螺丝", "REVIEW-MAT-00001", "螺丝", "规格: 10*40"),
            alias_row("螺丝", "REVIEW-MAT-00002", "膨胀螺丝", "规格: M12*80"),
        ],
        [
            conflict_row(
                "alias_conflict",
                "螺丝",
                "REVIEW-MAT-00001；REVIEW-MAT-00002",
                "规格: 10*40 || 规格: M12*80",
            )
        ],
    )

    assert resolved == []
    alias = next(row for row in aliases if row["raw_name"] == "螺丝")
    assert alias["candidate_count"] == "2"
    assert alias["requires_confirmation"] == "true"
    assert alias["candidate_codes"] == "REVIEW-MAT-00001；REVIEW-MAT-00002"


def test_human_review_items_without_conflicts_are_added_to_queue(tmp_path: Path) -> None:
    _summary, resolved, queue, _aliases = run_resolver(
        tmp_path,
        [merged_row("REVIEW-MAT-00001", "办公室门锁", "规格型号缺失", needs_review="true", confidence="0.70")],
        [alias_row("办公室门锁", "REVIEW-MAT-00001", "办公室门锁", "规格型号缺失")],
        [],
    )

    assert resolved == []
    assert len(queue) == 1
    assert queue[0]["issue_type"] == "needs_human_review"
    assert queue[0]["candidate_codes"] == "REVIEW-MAT-00001"


def test_items_with_open_questions_in_notes_are_not_import_ready(tmp_path: Path) -> None:
    _summary, resolved, queue, _aliases = run_resolver(
        tmp_path,
        [
            merged_row(
                "REVIEW-MAT-00001",
                "灯管",
                "功率: 36W",
                notes="需不需要区分 LED/荧光灯、长度？",
            )
        ],
        [alias_row("36W灯管", "REVIEW-MAT-00001", "灯管", "功率: 36W")],
        [],
    )

    assert resolved == []
    assert len(queue) == 1
    assert queue[0]["issue_type"] == "needs_note_review"
