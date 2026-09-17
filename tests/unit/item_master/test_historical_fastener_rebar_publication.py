from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "scripts/material_master/publish_historical_fastener_rebar_variants.py"
SPEC = importlib.util.spec_from_file_location("historical_fastener_rebar_publication", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_historical_rows_are_split_by_gpc_boundary_and_deduplicated() -> None:
    rows = [
        {
            "source_sheet_row": 10,
            "target": "bolt",
            "编码": 703020013,
            "名称": "六角螺丝",
            "规格型号": "20*80",
            "资源分类": "螺栓",
            "单位": "套",
        },
        {
            "source_sheet_row": 11,
            "target": "bolt",
            "编码": 703020014,
            "名称": "六角螺栓",
            "规格型号": "M20×80",
            "资源分类": "其他材料其他",
            "单位": "套",
        },
        {
            "source_sheet_row": 12,
            "target": "bolt",
            "编码": 703020015,
            "名称": "自攻螺丝",
            "规格型号": "",
            "资源分类": "螺栓",
            "单位": "只",
        },
        {
            "source_sheet_row": 20,
            "target": "rebar",
            "编码": 101040020,
            "名称": "螺纹钢",
            "规格型号": "HRB400 φ25（Ⅲ级钢）",
            "资源分类": "螺纹钢",
            "单位": "吨",
        },
        {
            "source_sheet_row": 21,
            "target": "rebar",
            "编码": 101040021,
            "名称": "热轧带肋钢筋",
            "规格型号": "Φ25",
            "资源分类": "螺纹钢",
            "单位": "吨",
        },
    ]

    materials, profiles, report = MODULE.build_publication(rows)

    assert report["published_material_count"] == 2
    assert report["duplicate_rows_merged"] == 2
    assert report["excluded_count"] == 1
    bolt = next(row for row in materials if row["standard_type"] == "六角螺栓")
    assert bolt["gpc_brick_code"] == "100031850101"
    assert bolt["procurement_attributes"]["规格"] == "M20×80 mm"
    assert bolt["source_rows"] == [10, 11]
    rebar = next(row for row in materials if row["standard_type"] == "热轧带肋钢筋")
    assert rebar["material_name"] == "热轧带肋钢筋｜HRB400｜Φ25｜直条"
    assert rebar["source_rows"] == [20, 21]
    assert {profile["profile_id"] for profile in profiles} == {
        "REF-TYPE-BOLT-HEX",
        "REF-TYPE-REBAR-HOT-ROLLED",
    }


def test_rebar_incomplete_identity_is_not_published_as_a_sku() -> None:
    normalized, reason = MODULE.normalize_rebar({
        "名称": "盘螺",
        "规格型号": "HRB400",
        "资源分类": "螺纹钢",
        "单位": "吨",
    })

    assert normalized is None
    assert reason == "牌号或公称直径不完整"


def test_bolt_types_use_structure_evidence_instead_of_strength_or_usage() -> None:
    cases = [
        ("10.9级六角螺栓", "30*150", "六角螺栓", "100031850101"),
        ("高强度螺丝", "16*85", "头型待识别螺栓", "100031850103"),
        ("G627绞制孔螺栓", "16*65", "绞制孔螺栓", "100031850104"),
        ("预埋件螺栓", "M30*120", "预埋螺栓", "100031850105"),
        ("M36环向螺栓", "36*604", "环向/纵向连接螺栓", "100031850106"),
        ("带孔螺栓 16*1.5*25", "", "带孔螺栓", "100031850107"),
        ("不锈钢螺栓", "M12*110", "头型待识别螺栓", "100031850103"),
    ]

    for index, (name, specification, expected_type, expected_code) in enumerate(cases, start=1):
        normalized, reason = MODULE.normalize_fastener({
            "source_sheet_row": index,
            "编码": f"CASE-{index}",
            "名称": name,
            "规格型号": specification,
            "单位": "套",
        })
        assert reason == ""
        assert normalized is not None
        assert normalized["material"]["standard_type"] == expected_type
        assert normalized["material"]["gpc_brick_code"] == expected_code


def test_strength_grade_remains_a_sku_attribute_for_unidentified_bolt_head() -> None:
    normalized, reason = MODULE.normalize_fastener({
        "source_sheet_row": 1,
        "编码": "CASE-STRENGTH",
        "名称": "高强度螺丝",
        "规格型号": "M20*130 10.9级",
        "单位": "套",
    })

    assert reason == ""
    assert normalized is not None
    material = normalized["material"]
    assert material["standard_type"] == "头型待识别螺栓"
    assert material["price_drivers"]["性能/质量等级"] == "10.9级"
