from __future__ import annotations

import json
from pathlib import Path

from nexterp_agent.item_master.tariff_family_review import (
    build_decision_template,
    build_review_package,
    build_review_slice,
    freeze_review_package,
    map_tariff_nodes,
    normalize_tariff_name,
)


def test_normalize_tariff_name_only_collapses_pdf_whitespace() -> None:
    assert normalize_tariff_name("  其他  螺栓： ") == "其他 螺栓"


def test_fastener_codes_map_to_specific_internal_families() -> None:
    rows = map_tariff_nodes(
        [
            {"code": "7318", "name": "钢铁制的螺钉、螺栓、螺母", "kind": "heading"},
            {"code": "731815", "name": "螺纹制品 / 其他螺钉及螺栓", "kind": "subheading"},
            {"code": "73181510", "name": "其他螺钉及螺栓：抗拉强度在800兆帕及以上", "kind": "sku", "parent_code": "731815", "page": 945},
            {"code": "73181600", "name": "螺母", "kind": "sku", "parent_code": "7318", "page": 946},
            {"code": "73182200", "name": "其他垫圈", "kind": "sku", "parent_code": "7318", "page": 946},
        ]
    )
    by_code = {row.code: row for row in rows}
    assert by_code["73181510"].suggested_material_family == "螺丝/螺栓"
    assert by_code["73181600"].suggested_material_family == "螺母"
    assert by_code["73182200"].suggested_material_family == "垫圈/垫片"
    assert all(row.review_status == "candidate" for row in rows)
    assert by_code["73181510"].parent_name == "螺纹制品 / 其他螺钉及螺栓"
    assert by_code["73181510"].chapter_context == "HS第73章"


def test_mixed_keyword_leaf_stays_ambiguous_without_a_precise_prefix() -> None:
    row = map_tariff_nodes(
        [{"code": "74153390", "name": "其他螺纹制品：螺钉、螺栓及螺母", "kind": "sku", "parent_code": "7415", "page": 1}]
    )[0]
    assert row.review_status == "ambiguous"
    assert row.suggested_material_family == ""
    assert len(row.candidate_families) >= 2


def test_precise_copper_fastener_prefixes_are_supported() -> None:
    rows = map_tariff_nodes(
        [
            {"code": "74151000", "name": "钉、平头钉、U形钉", "kind": "sku", "parent_code": "7415", "page": 1},
            {"code": "74152100", "name": "垫圈（包括弹簧垫圈）", "kind": "sku", "parent_code": "7415", "page": 1},
            {"code": "74153310", "name": "木螺钉", "kind": "sku", "parent_code": "7415", "page": 1},
        ]
    )
    by_code = {row.code: row for row in rows}
    assert by_code["74151000"].suggested_material_family == "钉类"
    assert by_code["74152100"].suggested_material_family == "垫圈/垫片"
    assert by_code["74153310"].suggested_material_family == "螺丝/螺栓"


def test_unmapped_rows_are_not_promoted() -> None:
    rows = map_tariff_nodes(
        [{"code": "99999999", "name": "未建立规则的品目", "kind": "sku", "parent_code": "", "page": 1}]
    )
    assert rows[0].review_status == "unmapped"
    assert rows[0].suggested_material_family == ""
    assert rows[0].confidence == 0


def test_build_review_package_preserves_all_skus_and_marks_no_erpnext_write(tmp_path: Path) -> None:
    source = tmp_path / "tariff-nodes.jsonl"
    source.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in (
                {"code": "7318", "name": "紧固件", "kind": "heading"},
                {"code": "73181510", "name": "螺钉及螺栓", "kind": "sku", "parent_code": "7318", "page": 1},
                {"code": "99999999", "name": "未知", "kind": "sku", "parent_code": "", "page": 2},
            )
        ),
        encoding="utf-8",
    )
    internal = tmp_path / "release.tsv"
    internal.write_text("top_group\tmaterial_family\n紧固件与连接件\t螺丝/螺栓\n", encoding="utf-8-sig")
    summary = build_review_package(source, tmp_path / "out", internal)
    assert summary["row_count"] == 2
    assert summary["status_counts"] == {"candidate": 1, "unmapped": 1}
    assert summary["erpnext_written"] is False
    assert (tmp_path / "out/tariff_family_candidates.tsv").exists()
    assert (tmp_path / "out/tariff_family_summary.json").exists()


def test_decision_template_and_frozen_release_require_explicit_approval(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.tsv"
    candidates.write_text(
        "code\tsource_name\tnormalized_name\tparent_code\tparent_name\tchapter_code\tchapter_context\tpage\tsuggested_top_group\tsuggested_material_family\tcandidate_families\tmatching_rule\tconfidence\treview_status\n"
        "73181510\t螺栓\t螺栓\t7318\t紧固件\t73\tHS第73章\t945\t紧固件与连接件\t螺丝/螺栓\t紧固件与连接件/螺丝/螺栓\ths7318-fastener\t0.96\tcandidate\n"
        "99999999\t未知\t未知\t\t\t99\tHS第99章\t1\t\t\t\tnone\t0\tunmapped\n",
        encoding="utf-8",
    )
    decisions = tmp_path / "decisions.tsv"
    metadata = build_decision_template(candidates, decisions)
    assert metadata["row_count"] == 2
    rows = decisions.read_text(encoding="utf-8-sig").splitlines()
    rows[1] = rows[1].replace("\t\t紧固件与连接件\t螺丝/螺栓\t\t", "\tapprove\t紧固件与连接件\t螺丝/螺栓\t审阅员A\t")
    rows[2] = rows[2].replace("\t\t\t\t\t", "\treject\t\t\t审阅员A\t无法映射")
    decisions.write_text("\n".join(rows) + "\n", encoding="utf-8-sig")
    internal = tmp_path / "internal.tsv"
    internal.write_text("top_group\tmaterial_family\n紧固件与连接件\t螺丝/螺栓\n", encoding="utf-8-sig")
    summary = freeze_review_package(candidates, decisions, tmp_path / "release", internal)
    assert summary["release_row_count"] == 1
    assert summary["decision_counts"] == {"approve": 1, "reject": 1}
    assert summary["erpnext_written"] is False
    assert (tmp_path / "release/tariff_family_release.tsv").exists()


def test_freeze_rejects_a_stale_decision_template(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.tsv"
    candidates.write_text("code\tsuggested_top_group\tsuggested_material_family\n1\tA\tB\n", encoding="utf-8")
    decisions = tmp_path / "decisions.tsv"
    build_decision_template(candidates, decisions)
    candidates.write_text("code\tsuggested_top_group\tsuggested_material_family\n2\tA\tB\n", encoding="utf-8")
    internal = tmp_path / "internal.tsv"
    internal.write_text("top_group\tmaterial_family\nA\tB\n", encoding="utf-8-sig")
    try:
        freeze_review_package(candidates, decisions, tmp_path / "release", internal)
    except ValueError as exc:
        assert "哈希" in str(exc)
    else:
        raise AssertionError("stale decision template should be rejected")


def test_review_slice_preserves_scope_and_generates_bound_template(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.tsv"
    candidates.write_text(
        "code\tsource_name\tnormalized_name\tparent_code\tparent_name\tchapter_code\tchapter_context\tpage\tsuggested_top_group\tsuggested_material_family\tcandidate_families\tmatching_rule\tconfidence\treview_status\n"
        "73181510\t螺栓\t螺栓\t7318\t紧固件\t73\tHS第73章\t945\t紧固件与连接件\t螺丝/螺栓\t\ths7318-fastener\t0.96\tcandidate\n"
        "84139100\t泵件\t泵件\t8413\t泵\t84\tHS第84章\t100\t\t\t\tnone\t0\tunmapped\n",
        encoding="utf-8",
    )
    summary = build_review_slice(candidates, tmp_path / "slice", ["7317", "7318"])
    assert summary["row_count"] == 1
    assert summary["status_counts"] == {"candidate": 1}
    assert (tmp_path / "slice/tariff_family_candidates.tsv").exists()
    assert (tmp_path / "slice/tariff_family_decisions.tsv.meta.json").exists()
