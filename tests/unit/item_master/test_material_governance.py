import csv
import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "govern_material_catalog.py"
SPEC = importlib.util.spec_from_file_location("govern_material_catalog", SCRIPT_PATH)
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

COMPOSITION_FIELDS = [
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

GROUP_OVERRIDE_FIELDS = [
    "canonical_group_pattern",
    "group_rule_key",
    "required_all",
    "required_any",
    "default_uom",
    "unit_policy",
    "alias_policy",
    "release_grade",
    "governance_reason",
    "disabled",
]

ITEM_OVERRIDE_FIELDS = [
    "merged_item_code",
    "governance_grade",
    "issue_type",
    "missing_specs",
    "next_action",
    "governance_reason",
    "reviewed_by",
    "reviewed_at",
    "disabled",
]

ALIAS_OVERRIDE_FIELDS = [
    "raw_name",
    "normalized_raw_name",
    "candidate_codes",
    "alias_policy",
    "recommended_candidate_code",
    "requires_confirmation",
    "governance_reason",
    "disabled",
]

RULES_YAML = """
version: 0.2
defaults:
  required_any: [规格, 型号]
blocking_issue_types: [alias_conflict, unit_conflict]
low_precision_issue_types: [low_precision_conflict, needs_human_review, needs_note_review]
open_question_markers: ["?", "？", 是否, 需不需要, 未说明]
group_rules:
  - key: fastener
    label: 紧固件
    canonical_group_patterns: [紧固件]
    required_any: [规格, 型号]
    recommended_next_action: 确认紧固件规格。
  - key: cement
    label: 水泥砂石
    canonical_group_patterns: [水泥]
    required_any: [强度等级, 包装规格, 型号]
    recommended_next_action: 确认强度等级和包装规格。
"""


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
    group: str = "五金备件/其他/紧固件",
    notes: str = "",
    needs_review: str = "false",
) -> dict[str, str]:
    return {
        "merged_item_code": code,
        "standard_name": name,
        "reviewed_group_paths": group,
        "canonical_group_path": group,
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


def composition_row(row: dict[str, str]) -> dict[str, str]:
    return {
        "merged_item_code": row["merged_item_code"],
        "standard_name": row["standard_name"],
        "canonical_group_path": row["canonical_group_path"],
        "specs": row["specs"],
        "unit": row["unit"],
        "source_count": row["source_count"],
        "source_candidate_count": "1",
        "merge_source_type": "单条候选保留",
        "merge_reason": row["merge_reason"],
        "merge_confidence": row["merge_confidence"],
        "confidence_bucket": "高置信度 >= 0.95",
        "needs_human_review": row["needs_human_review"],
        "note_has_open_question": "false",
        "related_conflict_types": "",
        "resolution_issue_types": "",
        "composition_bucket": "测试",
        "composition_reason": "测试",
        "source_rows": row["source_rows"],
        "alias_names": row["alias_names"],
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
        "reason": "测试冲突",
        "suggested_action": "测试建议",
    }


def alias_context(raw_name: str, codes: str, requires_confirmation: str = "true") -> dict[str, str]:
    return {
        "raw_name": raw_name,
        "normalized_raw_name": module.normalize_for_key(raw_name),
        "candidate_count": str(len(module.split_multi(codes))),
        "candidate_codes": codes,
        "import_ready_candidate_codes": "",
        "requires_confirmation": requires_confirmation,
        "ambiguity_reason": "测试别名歧义",
        "candidate_contexts": "测试候选",
    }


def run_governance(
    tmp_path: Path,
    merged_rows: list[dict[str, str]],
    queue_rows: list[dict[str, str]] | None = None,
    alias_rows: list[dict[str, str]] | None = None,
    group_overrides: list[dict[str, str]] | None = None,
    item_overrides: list[dict[str, str]] | None = None,
    alias_overrides: list[dict[str, str]] | None = None,
):
    rules_path = tmp_path / "rules.yaml"
    merged_path = tmp_path / "merged.csv"
    composition_path = tmp_path / "composition.csv"
    queue_path = tmp_path / "queue.csv"
    alias_context_path = tmp_path / "alias_context.csv"
    group_override_path = tmp_path / "group_overrides.csv"
    item_override_path = tmp_path / "item_overrides.csv"
    alias_override_path = tmp_path / "alias_overrides.csv"
    governed_path = tmp_path / "governed.csv"
    release_path = tmp_path / "release.csv"
    governance_queue_path = tmp_path / "governance_queue.csv"
    breakdown_path = tmp_path / "breakdown.csv"
    summary_path = tmp_path / "summary.json"

    rules_path.write_text(RULES_YAML, encoding="utf-8")
    write_csv(merged_path, MERGED_FIELDS, merged_rows)
    write_csv(composition_path, COMPOSITION_FIELDS, [composition_row(row) for row in merged_rows])
    write_csv(queue_path, QUEUE_FIELDS, queue_rows or [])
    write_csv(alias_context_path, ALIAS_CONTEXT_FIELDS, alias_rows or [])
    write_csv(group_override_path, GROUP_OVERRIDE_FIELDS, group_overrides or [])
    write_csv(item_override_path, ITEM_OVERRIDE_FIELDS, item_overrides or [])
    write_csv(alias_override_path, ALIAS_OVERRIDE_FIELDS, alias_overrides or [])

    summary = module.govern_material_catalog(
        rules_path=rules_path,
        merged_catalog_path=merged_path,
        composition_items_path=composition_path,
        resolution_queue_path=queue_path,
        alias_context_path=alias_context_path,
        group_overrides_path=group_override_path,
        item_overrides_path=item_override_path,
        alias_overrides_path=alias_override_path,
        governed_catalog_path=governed_path,
        release_candidates_path=release_path,
        governance_queue_path=governance_queue_path,
        breakdown_path=breakdown_path,
        summary_path=summary_path,
    )
    return summary, read_csv(governed_path), read_csv(release_path), read_csv(governance_queue_path)


def test_outputs_all_rows_and_grade_counts_sum_to_input(tmp_path: Path) -> None:
    rows = [
        merged_row("REVIEW-MAT-00001", "热缩管", "规格: 3CM"),
        merged_row("REVIEW-MAT-00002", "未知物料", ""),
        merged_row("REVIEW-MAT-00003", "灯管", "规格: 36W", notes="是否需要区分 LED？"),
    ]

    summary, governed, release, queue = run_governance(tmp_path, rows)

    assert summary["merged_rows"] == 3
    assert summary["governed_rows"] == 3
    assert summary["grade_total"] == 3
    assert len(governed) == 3
    assert len(release) == 1
    assert len(queue) == 2
    assert {row["governance_grade"] for row in governed} == {"A", "B", "C"}


def test_conflicts_and_low_precision_map_to_expected_grades(tmp_path: Path) -> None:
    rows = [
        merged_row("REVIEW-MAT-00001", "螺丝", "规格: M12"),
        merged_row("REVIEW-MAT-00002", "水泥", "型号: P.O 42.5", group="工程建材/水泥砂石"),
        merged_row("REVIEW-MAT-00003", "门锁", "规格: 通用", needs_review="true"),
    ]

    _summary, governed, _release, _queue = run_governance(
        tmp_path,
        rows,
        queue_rows=[
            queue_row("alias_conflict", "REVIEW-MAT-00001"),
            queue_row("unit_conflict", "REVIEW-MAT-00002"),
            queue_row("low_precision_conflict", "REVIEW-MAT-00003"),
        ],
    )

    by_code = {row["merged_item_code"]: row for row in governed}
    assert by_code["REVIEW-MAT-00001"]["governance_grade"] == "D"
    assert by_code["REVIEW-MAT-00001"]["issue_type"] == "alias_conflict"
    assert by_code["REVIEW-MAT-00002"]["governance_grade"] == "D"
    assert by_code["REVIEW-MAT-00002"]["issue_type"] == "unit_conflict"
    assert by_code["REVIEW-MAT-00003"]["governance_grade"] == "C"
    assert by_code["REVIEW-MAT-00003"]["has_low_precision"] == "true"


def test_group_override_changes_required_specs(tmp_path: Path) -> None:
    rows = [merged_row("REVIEW-MAT-00001", "螺丝", "规格: M12")]

    _summary, governed, _release, _queue = run_governance(
        tmp_path,
        rows,
        group_overrides=[
            {
                "canonical_group_pattern": "紧固件",
                "group_rule_key": "fastener_strict",
                "required_all": "材质",
                "required_any": "规格",
                "default_uom": "",
                "unit_policy": "",
                "alias_policy": "",
                "release_grade": "",
                "governance_reason": "紧固件必须确认材质",
                "disabled": "",
            }
        ],
    )

    assert governed[0]["governance_grade"] == "C"
    assert governed[0]["matched_rule_key"] == "fastener_strict"
    assert governed[0]["rule_source"] == "group_override"
    assert governed[0]["missing_specs"] == "材质"


def test_item_override_has_highest_priority(tmp_path: Path) -> None:
    rows = [merged_row("REVIEW-MAT-00001", "螺丝", "")]

    _summary, governed, release, _queue = run_governance(
        tmp_path,
        rows,
        queue_rows=[queue_row("alias_conflict", "REVIEW-MAT-00001")],
        item_overrides=[
            {
                "merged_item_code": "REVIEW-MAT-00001",
                "governance_grade": "A",
                "issue_type": "manual_release",
                "missing_specs": "",
                "next_action": "人工确认后可发布。",
                "governance_reason": "业务已确认。",
                "reviewed_by": "tester",
                "reviewed_at": "2026-06-09",
                "disabled": "",
            }
        ],
    )

    assert governed[0]["governance_grade"] == "A"
    assert governed[0]["issue_type"] == "manual_release"
    assert governed[0]["override_source"] == "item_override"
    assert len(release) == 1


def test_alias_override_can_resolve_ambiguous_alias_for_recommended_candidate(tmp_path: Path) -> None:
    rows = [
        merged_row("REVIEW-MAT-00001", "螺丝", "规格: M12"),
        merged_row("REVIEW-MAT-00002", "膨胀螺丝", "规格: M12"),
    ]

    _summary, governed, _release, _queue = run_governance(
        tmp_path,
        rows,
        alias_rows=[alias_context("螺丝", "REVIEW-MAT-00001；REVIEW-MAT-00002")],
        alias_overrides=[
            {
                "raw_name": "螺丝",
                "normalized_raw_name": module.normalize_for_key("螺丝"),
                "candidate_codes": "REVIEW-MAT-00001；REVIEW-MAT-00002",
                "alias_policy": "unique",
                "recommended_candidate_code": "REVIEW-MAT-00001",
                "requires_confirmation": "false",
                "governance_reason": "业务确认螺丝默认指普通螺丝。",
                "disabled": "",
            }
        ],
    )

    by_code = {row["merged_item_code"]: row for row in governed}
    assert by_code["REVIEW-MAT-00001"]["governance_grade"] == "A"
    assert by_code["REVIEW-MAT-00002"]["governance_grade"] == "D"
    assert by_code["REVIEW-MAT-00002"]["issue_type"] == "alias_conflict"


def test_single_candidate_alias_context_is_not_alias_conflict(tmp_path: Path) -> None:
    rows = [merged_row("REVIEW-MAT-00001", "彩钢瓦", "规格: 0.5")]

    _summary, governed, _release, _queue = run_governance(
        tmp_path,
        rows,
        alias_rows=[alias_context("0.5彩钢瓦", "REVIEW-MAT-00001", requires_confirmation="true")],
    )

    assert governed[0]["governance_grade"] == "A"
    assert governed[0]["has_alias_conflict"] == "false"
