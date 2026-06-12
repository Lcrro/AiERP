import csv
import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "build_standard_item_master_draft.py"
SPEC = importlib.util.spec_from_file_location("build_standard_item_master_draft", SCRIPT_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def write_input(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=module.INPUT_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def candidate_row(
    name: str,
    specs: str,
    group: str,
    unit: str = "个",
    grade: str = "A",
    aliases: str = "",
    basis: str = "",
) -> dict[str, str]:
    return {
        "标准名称": name,
        "必填规格": specs,
        "辅助规格": "",
        "标准分组": group,
        "标准单位": unit,
        "别名/土名": aliases,
        "放行等级": grade,
        "整理依据": basis,
    }


def test_exact_duplicate_candidates_merge_to_one_draft_sku(tmp_path: Path) -> None:
    input_path = tmp_path / "candidates.tsv"
    write_input(
        input_path,
        [
            candidate_row("尼龙扎带", "规格：10*500；材质：尼龙", "电气材料/扎带", "包", "B", "扎带"),
            candidate_row("尼龙扎带", "材质：尼龙；规格：10×500", "电气材料/扎带", "包", "B", "扎带"),
        ],
    )

    drafts, dedupe_issues, questions, import_ready, summary = module.build_outputs(input_path)

    assert summary["source_candidate_rows"] == 2
    assert summary["draft_sku_count"] == 1
    assert drafts[0]["candidate_count"] == "2"
    assert drafts[0]["code_prefix"] == "ELEC-TIE"
    assert dedupe_issues[0]["issue_type"] == "exact_duplicate_auto_merged"
    assert import_ready[0]["import_status"] == "confirm_then_import"
    assert questions == []


def test_group_context_beats_name_token_for_category() -> None:
    row = candidate_row("热缩管", "规格：3cm", "电气材料/绝缘材料", "米", "A")

    category = module.match_category(row)

    assert category.key == "electrical"
    assert category.code_prefix == "ELEC"


def test_c_grade_generates_missing_spec_question(tmp_path: Path) -> None:
    input_path = tmp_path / "candidates.tsv"
    write_input(
        input_path,
        [
            candidate_row(
                "门锁",
                "用途：办公室门",
                "五金备件/门锁锁具",
                "个",
                "C",
                "办公室门锁",
                "锁体型号/开孔规格缺失，无法区分不同门锁SKU",
            )
        ],
    )

    drafts, _, questions, import_ready, _ = module.build_outputs(input_path)

    assert drafts[0]["code_prefix"] == "HW-LOCK"
    assert not import_ready
    assert questions[0]["missing_specs"]
    assert "门锁" in questions[0]["question"]
