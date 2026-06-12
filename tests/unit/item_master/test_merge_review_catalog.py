import csv
import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "merge_review_catalog.py"
SPEC = importlib.util.spec_from_file_location("merge_review_catalog", SCRIPT_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


CATALOG_FIELDS = [
    "proposed_item_code",
    "standard_name",
    "item_group",
    "specs",
    "unit",
    "source_count",
    "source_statuses",
    "alias_names",
    "source_rows",
    "notes",
]


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def run_merge(tmp_path: Path, rows: list[dict[str, str]], mapping_rows: list[dict[str, str]] | None = None):
    catalog = tmp_path / "standard_item_catalog_from_review.csv"
    mapping = tmp_path / "material_group_canonical_mapping.csv"
    merged_catalog = tmp_path / "merged_standard_item_catalog.csv"
    merged_aliases = tmp_path / "merged_item_aliases.csv"
    conflicts = tmp_path / "merge_conflicts.csv"
    summary = tmp_path / "merge_summary.json"

    write_csv(catalog, CATALOG_FIELDS, rows)
    write_csv(
        mapping,
        [
            "reviewed_group_path",
            "canonical_group_path",
            "canonical_level1",
            "canonical_level2",
            "canonical_level3",
            "confidence",
            "rule_reason",
            "needs_human_review",
        ],
        mapping_rows
        or [
            {
                "reviewed_group_path": "电气材料/绝缘材料",
                "canonical_group_path": "电气与自动化/绝缘材料/绝缘材料",
                "needs_human_review": "false",
            },
            {
                "reviewed_group_path": "吊装索具/卸扣",
                "canonical_group_path": "吊装索具/吊装连接件/卸扣吊钩",
                "needs_human_review": "true",
            },
        ],
    )

    result = module.merge_review_catalog(
        catalog_path=catalog,
        mapping_path=mapping,
        merged_catalog_path=merged_catalog,
        merged_aliases_path=merged_aliases,
        conflicts_path=conflicts,
        summary_path=summary,
    )
    return result, read_csv(merged_catalog), read_csv(merged_aliases), read_csv(conflicts)


def row(
    code: str,
    name: str = "热缩管",
    group: str = "电气材料/绝缘材料",
    specs: str = "规格: 3CM",
    unit: str = "米",
    statuses: str = "可建档 | 可合并",
    aliases: str = "3CM热缩管",
    source_rows: str = "Sheet1:1",
    notes: str = "",
) -> dict[str, str]:
    return {
        "proposed_item_code": code,
        "standard_name": name,
        "item_group": group,
        "specs": specs,
        "unit": unit,
        "source_count": "1",
        "source_statuses": statuses,
        "alias_names": aliases,
        "source_rows": source_rows,
        "notes": notes,
    }


def test_same_name_specs_and_unit_auto_merge(tmp_path: Path) -> None:
    _summary, merged, aliases, conflicts = run_merge(
        tmp_path,
        [
            row("REVIEW-MAT-00001", specs="规格: 3CM", aliases="3CM热缩管", source_rows="Sheet1:1"),
            row("REVIEW-MAT-00002", specs="规格: 30mm", aliases="30mm热缩管", source_rows="Sheet1:2"),
        ],
    )

    assert len(merged) == 1
    assert merged[0]["merged_from_codes"] == "REVIEW-MAT-00001；REVIEW-MAT-00002"
    assert float(merged[0]["merge_confidence"]) >= 0.9
    assert {alias["raw_name"] for alias in aliases} >= {"3CM热缩管", "30mm热缩管"}
    assert conflicts == []


def test_same_name_different_specs_do_not_merge_and_create_conflict(tmp_path: Path) -> None:
    _summary, merged, _aliases, conflicts = run_merge(
        tmp_path,
        [
            row("REVIEW-MAT-00001", specs="规格: 2CM", aliases="2CM热缩管", source_rows="Sheet1:1"),
            row("REVIEW-MAT-00002", specs="规格: 3CM", aliases="3CM热缩管", source_rows="Sheet1:2"),
        ],
    )

    assert len(merged) == 2
    specs_conflicts = [conflict for conflict in conflicts if conflict["conflict_type"] == "specs_conflict"]
    assert len(specs_conflicts) == 1
    assert specs_conflicts[0]["candidate_codes"] == "REVIEW-MAT-00001；REVIEW-MAT-00002"


def test_unit_synonyms_can_merge(tmp_path: Path) -> None:
    _summary, merged, _aliases, conflicts = run_merge(
        tmp_path,
        [
            row("REVIEW-MAT-00001", unit="个", aliases="A插销", source_rows="Sheet1:1"),
            row("REVIEW-MAT-00002", unit="只", aliases="B插销", source_rows="Sheet1:2"),
        ],
    )

    assert len(merged) == 1
    assert merged[0]["unit"] == "个"
    assert not [conflict for conflict in conflicts if conflict["conflict_type"] == "unit_conflict"]


def test_group_mapping_human_review_flag_is_preserved(tmp_path: Path) -> None:
    _summary, merged, _aliases, _conflicts = run_merge(
        tmp_path,
        [
            row(
                "REVIEW-MAT-00001",
                name="卸扣",
                group="吊装索具/卸扣",
                specs="规格: 5T",
                unit="个",
                aliases="5T卸扣",
            )
        ],
    )

    assert merged[0]["canonical_group_path"] == "吊装索具/吊装连接件/卸扣吊钩"
    assert merged[0]["needs_human_review"] == "true"


def test_alias_source_rows_and_statuses_merge_with_dedupe(tmp_path: Path) -> None:
    _summary, merged, aliases, _conflicts = run_merge(
        tmp_path,
        [
            row(
                "REVIEW-MAT-00001",
                statuses="可建档 | 可合并",
                aliases="3CM热缩管 | 热缩管30mm",
                source_rows="Sheet1:1 | Sheet1:2",
                notes="与第1行同物料",
            ),
            row(
                "REVIEW-MAT-00002",
                specs="规格: 30mm",
                statuses="可合并",
                aliases="热缩管30mm | 30mm热缩管",
                source_rows="Sheet1:2 | Sheet1:3",
                notes="与第2行同物料",
            ),
        ],
    )

    assert len(merged) == 1
    assert merged[0]["alias_names"] == "30mm热缩管；3CM热缩管；热缩管30mm"
    assert merged[0]["source_rows"] == "Sheet1:1；Sheet1:2；Sheet1:3"
    assert set(merged[0]["source_statuses"].split(" | ")) == {"可建档", "可合并"}
    assert merged[0]["notes"] == "与第1行同物料 || 与第2行同物料"
    heat_alias = next(alias for alias in aliases if alias["raw_name"] == "热缩管30mm")
    assert heat_alias["source_proposed_item_codes"] == "REVIEW-MAT-00001；REVIEW-MAT-00002"
