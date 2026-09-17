from __future__ import annotations

from pathlib import Path
import time

import pytest

from nexterp_agent.item_master.tariff_extraction import (
    TARIFF_SOURCE_URL,
    TariffExtractionJobManager,
    TariffHierarchyState,
    TariffNode,
    attach_parent_codes,
    collapse_hierarchy_nodes,
    parse_tariff_page_words,
    parse_tariff_page_text,
    validate_nodes,
    validate_source_url,
)


def test_parse_tariff_page_text_extracts_codes_and_skips_headers() -> None:
    rows = parse_tariff_page_text(
        """
        序号 税则号列 货品名称
        1 7318.15.10 抗拉强度在 800 MPa 及以上的其他螺钉及螺栓
        2 7318.16.00 螺母
        注：本页为税则目录
        """,
        page=42,
    )

    assert [row.code for row in rows] == ["73181510", "73181600"]
    assert rows[0].name.startswith("抗拉强度")
    assert rows[0].page == 42
    assert rows[0].kind == "sku"


def test_source_url_is_allow_listed() -> None:
    assert validate_source_url(TARIFF_SOURCE_URL) == TARIFF_SOURCE_URL
    with pytest.raises(ValueError, match="白名单|财政部"):
        validate_source_url("https://example.com/tariff.pdf")


def test_coordinate_parser_ignores_footnote_codes_and_links_parent_heading() -> None:
    words = [
        (43.0, 89.0, 50.0, 98.0, "1", 0, 0, 0),
        (61.0, 88.0, 96.0, 98.0, "82.02", 0, 0, 1),
        (100.0, 88.0, 210.0, 98.0, "手工锯及各种锯的锯片", 0, 0, 2),
        (43.0, 112.0, 50.0, 121.0, "2", 0, 1, 0),
        (61.0, 111.0, 96.0, 121.0, "8202.1000", 0, 1, 1),
        (100.0, 111.0, 220.0, 121.0, "手工锯", 0, 1, 2),
        # A legal note can contain tax codes, but it is outside the code/name
        # columns and must not become a material node.
        (310.0, 140.0, 370.0, 150.0, "税号 51011100，2026 年触发水平", 0, 2, 0),
    ]

    nodes = attach_parent_codes(parse_tariff_page_words(words, page=100))

    assert [node.code for node in nodes] == ["8202", "82021000"]
    assert nodes[1].parent_code == "8202"
    assert nodes[0].kind == "heading"
    assert nodes[1].kind == "sku"
    assert nodes[1].name == "手工锯"


def test_coordinate_parser_restores_section_chapter_and_six_digit_hierarchy() -> None:
    section_words = [
        (270.0, 60.0, 330.0, 70.0, "第十五类", 0, 0, 0),
        (250.0, 76.0, 350.0, 86.0, "贱金属及其制品", 0, 1, 0),
    ]
    chapter_words = [
        (270.0, 60.0, 330.0, 70.0, "第七十三章", 0, 0, 0),
        (270.0, 76.0, 330.0, 86.0, "钢铁制品", 0, 1, 0),
        (61.0, 140.0, 96.0, 150.0, "73.18", 0, 2, 0),
        (100.0, 140.0, 220.0, 150.0, "钢铁制螺钉、螺栓", 0, 2, 1),
        (100.0, 160.0, 220.0, 170.0, "-螺纹制品", 0, 3, 0),
        (61.0, 180.0, 96.0, 190.0, "7318.1100", 0, 4, 0),
        (100.0, 180.0, 220.0, 190.0, "--方头螺钉", 0, 4, 1),
        (100.0, 200.0, 230.0, 210.0, "--其他螺钉及螺栓，不论是否带有螺母或垫圈", 0, 5, 0),
        (61.0, 220.0, 96.0, 230.0, "7318.1510", 0, 6, 0),
        (100.0, 220.0, 230.0, 230.0, "---抗拉强度在800MPa及以上的", 0, 6, 1),
    ]
    state = TariffHierarchyState()
    parsed = [
        *parse_tariff_page_words(
            section_words,
            page=894,
            include_hierarchy=True,
            hierarchy_state=state,
        ),
        *parse_tariff_page_words(
            chapter_words,
            page=929,
            include_hierarchy=True,
            hierarchy_state=state,
        ),
    ]
    nodes = attach_parent_codes(collapse_hierarchy_nodes(parsed))
    by_code = {node.code: node for node in nodes}

    assert by_code["S15"].name == "贱金属及其制品"
    assert by_code["73"].name == "钢铁制品"
    assert by_code["731815"].name == "螺纹制品 / 其他螺钉及螺栓，不论是否带有螺母或垫圈"
    assert by_code["73181510"].parent_code == "731815"
    assert by_code["731815"].parent_code == "7318"
    assert by_code["7318"].parent_code == "73"
    assert by_code["73"].parent_code == "S15"
    assert by_code["S15"].parent_code is None
    assert validate_nodes(nodes) == []


def test_duplicate_six_digit_candidates_collapse_to_their_common_parent_path() -> None:
    nodes = collapse_hierarchy_nodes(
        [
            TariffNode("010130", "驴 / 改良种用", 3, page=18, kind="subheading"),
            TariffNode("01013010", "驴：改良种用", 4, page=18, kind="sku"),
            TariffNode("010130", "驴 / 其他", 3, page=18, kind="subheading"),
            TariffNode("01013090", "其他", 4, page=18, kind="sku"),
        ]
    )

    assert [node.name for node in nodes if node.code == "010130"] == ["驴"]


def test_coordinate_parser_replaces_same_depth_sibling_before_naming_subheading() -> None:
    words = [
        (61.0, 100.0, 96.0, 110.0, "28.01", 0, 0, 0),
        (100.0, 100.0, 220.0, 110.0, "氟、氯、溴及碘：", 0, 0, 1),
        (61.0, 120.0, 96.0, 130.0, "2801.1000", 0, 1, 0),
        (100.0, 120.0, 220.0, 130.0, "-氯", 0, 1, 1),
        (61.0, 140.0, 96.0, 150.0, "2801.2000", 0, 2, 0),
        (100.0, 140.0, 220.0, 150.0, "-碘", 0, 2, 1),
    ]

    nodes = collapse_hierarchy_nodes(
        parse_tariff_page_words(words, page=301, include_hierarchy=True)
    )
    names = {node.code: node.name for node in nodes}

    assert names["280110"] == "氯"
    assert names["280120"] == "碘"
    assert names["28011000"] == "氯"
    assert names["28012000"] == "碘"


def test_coordinate_parser_carries_bottom_parent_context_to_next_page() -> None:
    state = TariffHierarchyState()
    page_301 = [
        (61.0, 100.0, 96.0, 110.0, "28.01", 0, 0, 0),
        (100.0, 100.0, 220.0, 110.0, "氟、氯、溴及碘：", 0, 0, 1),
        (61.0, 120.0, 96.0, 130.0, "2801.2000", 0, 1, 0),
        (100.0, 120.0, 220.0, 130.0, "-碘", 0, 1, 1),
        (100.0, 150.0, 220.0, 160.0, "-氟；溴：", 0, 2, 0),
    ]
    page_302 = [
        (61.0, 100.0, 96.0, 110.0, "2801.3010", 0, 0, 0),
        (100.0, 100.0, 220.0, 110.0, "---氟", 0, 0, 1),
        (61.0, 120.0, 96.0, 130.0, "2801.3020", 0, 1, 0),
        (100.0, 120.0, 220.0, 130.0, "---溴", 0, 1, 1),
    ]

    parsed = [
        *parse_tariff_page_words(
            page_301,
            page=301,
            include_hierarchy=True,
            hierarchy_state=state,
        ),
        *parse_tariff_page_words(
            page_302,
            page=302,
            include_hierarchy=True,
            hierarchy_state=state,
        ),
    ]
    names = {node.code: node.name for node in collapse_hierarchy_nodes(parsed)}

    assert names["280130"] == "氟；溴："
    assert names["28013010"] == "氟"
    assert names["28013020"] == "溴"


def test_cross_page_context_does_not_absorb_rate_footer_text() -> None:
    state = TariffHierarchyState()
    previous_page = [
        (61.0, 100.0, 96.0, 110.0, "02.07", 0, 0, 0),
        (100.0, 100.0, 220.0, 110.0, "家禽肉及食用杂碎", 0, 0, 1),
        (61.0, 120.0, 96.0, 130.0, "0207.2700", 0, 1, 0),
        (100.0, 120.0, 220.0, 130.0, "--块及杂碎，冻的", 0, 1, 1),
        (100.0, 654.0, 220.0, 664.0, "-鸭：", 0, 2, 0),
        (66.0, 738.0, 124.0, 748.0, "最惠国税率：0.5", 0, 3, 0),
        (126.0, 738.0, 180.0, 748.0, "元/千克。", 0, 3, 0),
        (66.0, 748.5, 116.0, 758.5, "普通税率：3.2", 0, 4, 0),
        (118.0, 748.5, 180.0, 758.5, "元/千克。", 0, 4, 0),
    ]
    next_page = [
        (61.0, 100.0, 96.0, 110.0, "0207.4100", 0, 0, 0),
        (100.0, 100.0, 220.0, 110.0, "--整只，鲜或冷的", 0, 0, 1),
    ]

    parse_tariff_page_words(
        previous_page,
        page=38,
        include_hierarchy=True,
        hierarchy_state=state,
    )
    nodes = parse_tariff_page_words(
        next_page,
        page=39,
        include_hierarchy=True,
        hierarchy_state=state,
    )
    names = {node.code: node.name for node in collapse_hierarchy_nodes(nodes)}

    assert names["020741"] == "鸭： / 整只，鲜或冷的"
    assert names["02074100"] == "整只，鲜或冷的"


def test_left_margin_rate_formula_is_not_appended_to_last_material_row() -> None:
    words = [
        (61.0, 100.0, 96.0, 110.0, "52.04", 0, 0, 0),
        (100.0, 100.0, 220.0, 110.0, "棉制缝纫线，不论是否供零售用：", 0, 0, 1),
        (100.0, 120.0, 220.0, 130.0, "-非供零售用：", 0, 1, 0),
        (61.0, 140.0, 96.0, 150.0, "5204.1100", 0, 2, 0),
        (100.0, 140.0, 220.0, 150.0, "--按重量计含棉量在85％及以上", 0, 2, 1),
        (65.9, 686.2, 205.0, 696.2, "进口棉花完税价格高于14.000", 0, 3, 0),
        (210.1, 686.2, 275.0, 696.2, "元/千克时，按0.280", 0, 3, 1),
        (73.9, 706.9, 105.0, 716.9, "Ri=9.0/Pi", 0, 4, 0),
        (106.9, 706.9, 150.0, 716.9, "+2.69%×Pi", 0, 4, 1),
    ]

    nodes = parse_tariff_page_words(words, page=646, include_hierarchy=True)
    names = {node.code: node.name for node in collapse_hierarchy_nodes(nodes)}

    assert names["52041100"] == "非供零售用： 按重量计含棉量在85％及以上"


def test_single_xx00_subheading_inherits_heading_and_uncoded_leaf_group() -> None:
    state = TariffHierarchyState()
    page_270 = [
        (61.0, 100.0, 96.0, 110.0, "25.01", 0, 0, 0),
        (100.0, 100.0, 230.0, 110.0, "盐（包括精制盐及变性盐）及纯氯化钠；海水：", 0, 0, 1),
        (100.0, 120.0, 220.0, 130.0, "---盐：", 0, 1, 0),
        (61.0, 140.0, 96.0, 150.0, "2501.0011", 0, 2, 0),
        (100.0, 140.0, 220.0, 150.0, "----食用盐", 0, 2, 1),
    ]
    page_271 = [
        (61.0, 100.0, 96.0, 110.0, "2501.0019", 0, 0, 0),
        (100.0, 100.0, 220.0, 110.0, "----其他", 0, 0, 1),
        (61.0, 120.0, 96.0, 130.0, "2501.0020", 0, 1, 0),
        (100.0, 120.0, 220.0, 130.0, "---纯氯化钠", 0, 1, 1),
        (61.0, 140.0, 96.0, 150.0, "2501.0030", 0, 2, 0),
        (100.0, 140.0, 220.0, 150.0, "---海水", 0, 2, 1),
    ]

    parsed = [
        *parse_tariff_page_words(
            page_270,
            page=270,
            include_hierarchy=True,
            hierarchy_state=state,
        ),
        *parse_tariff_page_words(
            page_271,
            page=271,
            include_hierarchy=True,
            hierarchy_state=state,
        ),
    ]
    names = {node.code: node.name for node in collapse_hierarchy_nodes(parsed)}

    assert names["250100"] == "盐（包括精制盐及变性盐）及纯氯化钠；海水："
    assert names["25010011"] == "盐： 食用盐"
    assert names["25010019"] == "盐： 其他"
    assert names["25010020"] == "纯氯化钠"
    assert names["25010030"] == "海水"


def test_demo_job_reports_progress_and_writes_only_candidate_manifest(tmp_path: Path) -> None:
    manager = TariffExtractionJobManager(tmp_path)
    created = manager.start({"mode": "demo"})
    seen_stages: set[str] = set()

    for _ in range(100):
        snapshot = manager.snapshot(created["job_id"])
        seen_stages.add(snapshot["stage"])
        if snapshot["status"] == "completed":
            break
        time.sleep(0.03)
    else:  # pragma: no cover - protects against a hung worker
        pytest.fail("演示任务未在预期时间内完成")

    assert snapshot["overall_progress"] == 1.0
    assert snapshot["nodes_found"] == 4
    assert snapshot["leaf_codes_found"] == 3
    assert {"inspecting", "extracting", "normalizing", "validating", "writing", "completed"} <= seen_stages
    assert snapshot["output_files"]
    assert all("erpnext" not in Path(path).name.lower() for path in snapshot["output_files"])


def test_full_job_requires_explicit_confirmation(tmp_path: Path) -> None:
    manager = TariffExtractionJobManager(tmp_path)
    with pytest.raises(ValueError, match="明确确认"):
        manager.start({"mode": "full", "confirmed": False})
