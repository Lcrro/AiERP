from __future__ import annotations

from pathlib import Path
import zipfile

from nexterp_agent.item_master.procurement_frequency_discovery import (
    build_clusters,
    build_fuzzy_review_candidates,
    read_source_rows,
)


def _write_xlsx(path: Path, business_rows: list[list[object]]) -> None:
    rows = [["日期", "材料", "数量", "单位", "工序序号", "市场单价"], *business_rows]
    row_xml = []
    for row_number, values in enumerate(rows, start=1):
        cells = []
        for column_number, value in enumerate(values, start=1):
            column = chr(ord("A") + column_number - 1)
            reference = f"{column}{row_number}"
            if isinstance(value, (int, float)):
                cells.append(f'<c r="{reference}"><v>{value}</v></c>')
            elif value not in (None, ""):
                cells.append(f'<c r="{reference}" t="inlineStr"><is><t>{value}</t></is></c>')
        row_xml.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", """
            <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheets><sheet name="实际采购清单" sheetId="1" r:id="rId1"/></sheets>
            </workbook>
        """)
        archive.writestr("xl/_rels/workbook.xml.rels", """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/>
            </Relationships>
        """)
        archive.writestr("xl/worksheets/sheet1.xml", f"""
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>{''.join(row_xml)}</sheetData>
            </worksheet>
        """)


def test_explicit_type_groups_specs_but_keeps_similar_panel_types_separate(tmp_path: Path) -> None:
    source = tmp_path / "采购.xlsx"
    _write_xlsx(source, [
        [44853, "公元PPRΦ110/45度弯头", 2, "只", 14, 38.2],
        [44854, "公元PPRΦ110/90度弯头", 2, "只", 14, 137],
        [44855, "公牛86型五孔插座面板", 1, "件", 14, 10.8],
        [44856, "公牛86型五孔面板底座", 1, "件", 14, 10.8],
    ])

    clusters = build_clusters(read_source_rows(source))

    ppr = next(row for row in clusters if row["standard_type_candidate"] == "PPR弯头")
    assert ppr["line_count"] == 2
    assert ppr["variant_count"] == 2
    assert ppr["queue"] == "多规格整合候选"
    assert {row["standard_type_candidate"] for row in clusters} >= {
        "公牛五孔插座面板", "公牛五孔面板底座",
    }


def test_known_false_merges_are_separated(tmp_path: Path) -> None:
    source = tmp_path / "采购.xlsx"
    _write_xlsx(source, [
        [44853, "钢丝绳20*8m", 1, "件", 1, 1],
        [44854, "伍尔特钢丝绳喷雾防锈剂500mL", 1, "瓶", 1, 1],
        [44855, "手拉葫芦1T*3m", 1, "件", 1, 1],
        [44856, "手拉葫芦保险扣1T", 1, "件", 1, 1],
        [44857, "m8x15内六角螺丝", 1, "件", 1, 1],
        [44858, "六角螺栓M8x20", 1, "件", 1, 1],
    ])

    clusters = build_clusters(read_source_rows(source))
    by_type = {row["standard_type_candidate"]: row for row in clusters}
    assert by_type["钢丝绳"]["line_count"] == 1
    assert by_type["钢丝绳防锈剂"]["line_count"] == 1
    assert by_type["手拉葫芦"]["line_count"] == 1
    assert by_type["手拉葫芦保险扣"]["line_count"] == 1
    assert by_type["内六角螺钉"]["line_count"] == 1
    assert by_type["六角螺栓"]["line_count"] == 1


def test_unknown_heads_are_review_candidates_not_auto_merged(tmp_path: Path) -> None:
    source = tmp_path / "采购.xlsx"
    _write_xlsx(source, [
        [44853, "特殊接头A M10", 1, "件", 1, 1],
        [44854, "特殊接头B M10", 1, "件", 1, 1],
    ])

    clusters = build_clusters(read_source_rows(source))
    assert len(clusters) == 2
    assert all(row["grouping_confidence"] == "not_auto_grouped" for row in clusters)
    fuzzy = build_fuzzy_review_candidates(clusters)
    assert len(fuzzy) == 1
    assert fuzzy[0]["decision"] == "人工复核，不自动合并"


def test_distinct_event_count_is_auditable(tmp_path: Path) -> None:
    source = tmp_path / "采购.xlsx"
    _write_xlsx(source, [
        [44853, "黄沙", 1, "吨", 1, 100],
        [44853, "黄沙", 1, "吨", 1, 100],
        [44854, "黄沙", 2, "吨", 2, 110],
    ])

    cluster = next(row for row in build_clusters(read_source_rows(source)) if row["standard_type_candidate"] == "建筑用天然砂")
    assert cluster["line_count"] == 3
    assert cluster["distinct_event_count_approx"] == 2
    assert cluster["quantity_by_uom"] == {"吨": 4.0}
    assert cluster["market_value_sum"] == 420.0
    assert cluster["frequency_rank"] == 1
    assert cluster["integration_rank"] == 1


def test_mixed_units_are_not_ready_for_multi_attribute_integration(tmp_path: Path) -> None:
    source = tmp_path / "采购.xlsx"
    _write_xlsx(source, [
        [44853, "公元PPRΦ110/45度弯头", 1, "只", 1, 1],
        [44854, "公元PPRΦ110/90度弯头", 1, "把", 1, 1],
    ])

    cluster = next(row for row in build_clusters(read_source_rows(source)) if row["standard_type_candidate"] == "PPR弯头")
    assert cluster["queue"] == "单位冲突/待复核"
