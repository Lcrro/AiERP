from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import zipfile

import pytest

from nexterp_agent.item_master.reference_catalog import ChatgptClassificationIndex, GpcReferenceIndex


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "material_master" / "import_gpc_reference.py"
SPEC = importlib.util.spec_from_file_location("import_gpc_reference", SCRIPT)
assert SPEC and SPEC.loader
IMPORTER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = IMPORTER
SPEC.loader.exec_module(IMPORTER)
TEXT_SCRIPT = ROOT / "scripts" / "material_master" / "translate_gpc_profile_texts.py"
TEXT_SPEC = importlib.util.spec_from_file_location("translate_gpc_profile_texts", TEXT_SCRIPT)
assert TEXT_SPEC and TEXT_SPEC.loader
TEXT_TRANSLATOR = importlib.util.module_from_spec(TEXT_SPEC)
sys.modules[TEXT_SPEC.name] = TEXT_TRANSLATOR
TEXT_SPEC.loader.exec_module(TEXT_TRANSLATOR)


def test_gpc_xml_fixture_builds_four_levels_and_brick_profile(tmp_path: Path) -> None:
    xml = tmp_path / "GPC 2026-05 EN.xml"
    xml.write_text(
        """<schema languageCode="EN" dateUtc="20/5/2026">
          <segment code="70000000" text="Arts" definition="Segment definition" active="true">
            <family code="70010000" text="Supplies" definition="Family definition" active="true">
              <class code="70010100" text="Brushes" definition="Class definition" active="true">
                <brick code="10001674" text="Artists Brushes" definition="Includes brushes" definitionExcludes="Excludes airbrushes" active="true">
                  <attType code="20001337" text="Brush type" definition="Type definition" active="true">
                    <attValue code="30000001" text="Flat" definition="Flat value" active="true" />
                  </attType>
                </brick>
              </class>
            </family>
          </segment>
        </schema>""",
        encoding="utf-8",
    )
    nodes, profiles, stats = IMPORTER.parse_gpc_xml(xml)
    profile_translations = [
        {"code": "20001337", "working_name": "画笔类型", "status": "machine", "source_hash": IMPORTER._sha256_bytes(b"Brush type")},
        {"code": "30000001", "working_name": "平头", "status": "machine", "source_hash": IMPORTER._sha256_bytes(b"Flat")},
    ]
    profile_text_translations = [
        {"source_hash": IMPORTER._sha256_bytes(b"Includes brushes"), "official_text": "Includes brushes", "working_text": "包括画笔", "status": "machine"},
        {"source_hash": IMPORTER._sha256_bytes(b"Excludes airbrushes"), "official_text": "Excludes airbrushes", "working_text": "不包括喷笔", "status": "machine"},
    ]
    index = GpcReferenceIndex(nodes, profiles, IMPORTER.build_translations(nodes), profile_translations, profile_text_translations, source_meta={"version": "2026-05", "hierarchy_complete": True})

    assert stats["segment"] == 1
    assert stats["family"] == 1
    assert stats["class"] == 1
    assert stats["brick"] == 1
    assert stats["attribute"] == 1
    assert stats["attribute_value"] == 1
    assert [row["code"] for row in index.path("10001674")] == ["70000000", "70010000", "70010100", "10001674"]
    assert [row["code"] for row in index.children("70010100")[0]["full_path"]] == ["70000000", "70010000", "70010100", "10001674"]
    profile = index.profile("10001674")
    assert profile["includes"] == "Includes brushes"
    assert profile["excludes"] == "Excludes airbrushes"
    assert profile["includes_working"] == "包括画笔"
    assert profile["includes_official"] == "Includes brushes"
    assert profile["excludes_working"] == "不包括喷笔"
    assert profile["excludes_official"] == "Excludes airbrushes"
    assert profile["attributes"][0]["values"][0]["code"] == "30000001"
    assert profile["attributes"][0]["working_name"] == "画笔类型"
    assert profile["attributes"][0]["values"][0]["working_name"] == "平头"
    assert index.search("airbrushes")["rows"][0]["code"] == "10001674"
    attribute_result = index.search("20001337")["rows"][0]
    assert attribute_result["result_type"] == "profile_term"
    assert attribute_result["kind"] == "attribute"
    assert attribute_result["working_name"] == "画笔类型"
    value_result = index.search("30000001")["rows"][0]
    assert value_result["result_type"] == "profile_term"
    assert value_result["kind"] == "attribute_value"
    assert value_result["working_name"] == "平头"
    assert value_result["usage_count"] == 1
    assert value_result["brick_count"] == 1
    assert value_result["references"][0]["attribute_code"] == "20001337"
    assert [row["code"] for row in value_result["references"][0]["path"]] == ["70000000", "70010000", "70010100", "10001674"]
    assert index.search("平头")["rows"][0]["code"] == "30000001"
    assert index.search("喷笔")["rows"][0]["code"] == "10001674"


def test_gpc_profile_text_extraction_deduplicates_definition_and_includes() -> None:
    rows = TEXT_TRANSLATOR.extract_profile_texts([
        {"code": "10000001", "official_name": "One", "definition": "Same text", "includes": "Same text", "excludes": "Other text"},
        {"code": "10000002", "official_name": "Two", "definition": "Same text", "includes": "Different text", "excludes": ""},
    ])
    assert len(rows) == 3
    same = next(row for row in rows if row["official_text"] == "Same text")
    assert same["usage_count"] == 3
    assert same["id"].startswith("T")
    assert len(TEXT_TRANSLATOR.pack_batches(rows, 1)) == 3
    source = {"source_hash": "hash", "official_text": "Excludes many different products including one, two, three, four and five."}
    assert not TEXT_TRANSLATOR.valid_translation(
        {"source_hash": "hash", "official_text": source["official_text"], "working_text": "排除其他产品。"},
        source,
    )
    assert TEXT_TRANSLATOR.valid_translation(
        {"source_hash": "hash", "official_text": source["official_text"], "working_text": "排除许多不同的产品，包括产品一、产品二、产品三、产品四和产品五。"},
        source,
    )


def test_gpc_index_rejects_missing_parent_and_cycle() -> None:
    with pytest.raises(ValueError, match="缺失父级"):
        GpcReferenceIndex([{"code": "10001674", "name": "Brick", "kind": "brick", "level": 3, "parent_code": "70010100"}])
    with pytest.raises(ValueError, match="循环引用"):
        GpcReferenceIndex([
            {"code": "70000000", "name": "Segment", "kind": "segment", "level": 0, "parent_code": "10001600"},
            {"code": "10001600", "name": "Segment 2", "kind": "segment", "level": 0, "parent_code": "70000000"},
        ])


def test_gpc_material_placements_keep_ancestor_paths_and_filter_empty_branches() -> None:
    nodes = [
        {"code": "70000000", "name": "Arts", "kind": "segment", "level": 0},
        {"code": "70010000", "name": "Supplies", "kind": "family", "level": 1, "parent_code": "70000000"},
        {"code": "70010100", "name": "Brushes", "kind": "class", "level": 2, "parent_code": "70010000"},
        {"code": "10001674", "name": "Artists Brushes", "kind": "brick", "level": 3, "parent_code": "70010100"},
        {"code": "80000000", "name": "Tools", "kind": "segment", "level": 0},
        {"code": "80010000", "name": "Hand Tools", "kind": "family", "level": 1, "parent_code": "80000000"},
        {"code": "80010100", "name": "Hammers", "kind": "class", "level": 2, "parent_code": "80010000"},
        {"code": "10009999", "name": "Hammers", "kind": "brick", "level": 3, "parent_code": "80010100"},
    ]
    placements = [{
        "material_id": "MAT-C001",
        "material_name": "平头画笔｜20 mm",
        "standard_type": "画笔",
        "gpc_brick_code": "10001674",
        "review_status": "待业务确认",
        "completeness_status": "完整",
        "specification_basis": "测试默认规格",
        "stock_uom": "支",
        "source_rows": [2],
        "procurement_attributes": {"宽度": "20 mm"},
        "price_drivers": {"材质等级": "专业级"},
        "gpc_notes": ["画笔应归入画笔 Brick"],
    }]
    index = GpcReferenceIndex(nodes, material_placements=placements)

    assert index.summary()["actual_material_count"] == 1
    assert index.summary()["materialized_counts"] == {
        "segment": 1,
        "family": 1,
        "class": 1,
        "brick": 1,
        "internal_brick": 0,
        "internal_family": 0,
        "internal_type": 0,
    }
    assert [row["code"] for row in index.children(None)] == ["70000000", "80000000"]
    assert [row["code"] for row in index.children(None, materialized_only=True)] == ["70000000"]
    assert index.children("70000000", materialized_only=True)[0]["actual_material_count"] == 1
    material = index.profile("10001674")["actual_materials"][0]
    assert material["material_name"] == "平头画笔｜20 mm"
    assert material["completeness_status"] == "完整"
    assert material["questions"] == []
    assert material["procurement_attributes"] == {"宽度": "20 mm"}
    assert material["price_drivers"] == {"材质等级": "专业级"}
    assert material["gpc_notes"] == ["画笔应归入画笔 Brick"]
    assert index.search("Artists", materialized_only=True)["rows"][0]["code"] == "10001674"
    assert index.search("平头画笔", materialized_only=True)["rows"][0]["code"] == "10001674"
    assert index.search("专业级", materialized_only=True)["rows"][0]["code"] == "10001674"
    assert index.search("Hammers", materialized_only=True)["rows"] == []

    with pytest.raises(ValueError, match="必须挂到有效 Brick"):
        GpcReferenceIndex(nodes, material_placements=[{
            "material_id": "BAD-1",
            "material_name": "错误物料",
            "standard_type": "错误类型",
            "gpc_brick_code": "70010100",
            "stock_uom": "件",
            "completeness_status": "完整",
            "procurement_attributes": {"规格": "测试"},
            "price_drivers": {"等级": "测试"},
            "gpc_notes": ["测试分类边界"],
        }])


def test_gpc_material_catalog_filters_and_paginates_reviewed_materials() -> None:
    nodes = [
        {"code": "70000000", "name": "Arts", "kind": "segment", "level": 0},
        {"code": "70010000", "name": "Supplies", "kind": "family", "level": 1, "parent_code": "70000000"},
        {"code": "70010100", "name": "Brushes", "kind": "class", "level": 2, "parent_code": "70010000"},
        {"code": "10001674", "name": "Artists Brushes", "kind": "brick", "level": 3, "parent_code": "70010100"},
        {"code": "80000000", "name": "Tools", "kind": "segment", "level": 0},
        {"code": "80010000", "name": "Hand Tools", "kind": "family", "level": 1, "parent_code": "80000000"},
        {"code": "80010100", "name": "Hammers", "kind": "class", "level": 2, "parent_code": "80010000"},
        {"code": "10009999", "name": "Hammers", "kind": "brick", "level": 3, "parent_code": "80010100"},
    ]
    common = {
        "stock_uom": "件",
        "completeness_status": "完整",
        "procurement_attributes": {"等级": "施工级"},
        "price_drivers": {"质量": "耐用"},
        "gpc_notes": ["按实际用途归类"],
    }
    index = GpcReferenceIndex(nodes, material_placements=[
        {**common, "material_id": "MAT-BRUSH", "material_name": "平头画笔｜20 mm", "standard_type": "画笔", "gpc_brick_code": "10001674"},
        {**common, "material_id": "MAT-HAMMER", "material_name": "羊角锤｜500 g", "standard_type": "手锤", "gpc_brick_code": "10009999"},
    ])

    full = index.material_catalog(limit=1)
    assert full["total"] == 2
    assert len(full["rows"]) == 1
    assert {row["code"] for row in full["segments"]} == {"70000000", "80000000"}
    assert full["category_tree"][0]["children"][0]["children"][0]["children"][0]["code"] == "10001674"
    brush = index.material_catalog(query="20 mm", segment_code="70000000")
    assert [row["material_id"] for row in brush["rows"]] == ["MAT-BRUSH"]
    assert [node["code"] for node in brush["rows"][0]["classification_path"]] == [
        "70000000", "70010000", "70010100", "10001674",
    ]
    assert index.material_catalog(standard_type="手锤")["rows"][0]["segment_name"] == "Tools"
    assert [row["material_id"] for row in index.material_catalog(category_code="10009999")["rows"]] == ["MAT-HAMMER"]


def test_gpc_material_catalog_can_group_existing_skus_by_standard_type() -> None:
    nodes = [
        {"code": "70000000", "name": "Arts", "kind": "segment", "level": 0},
        {"code": "70010000", "name": "Supplies", "kind": "family", "level": 1, "parent_code": "70000000"},
        {"code": "70010100", "name": "Brushes", "kind": "class", "level": 2, "parent_code": "70010000"},
        {"code": "10001674", "name": "Artists Brushes", "kind": "brick", "level": 3, "parent_code": "70010100"},
    ]
    common = {
        "standard_type": "平头画笔",
        "gpc_brick_code": "10001674",
        "stock_uom": "支",
        "completeness_status": "完整",
        "price_drivers": {"材质等级": "专业级"},
        "gpc_notes": ["只保留实际存在的规格"],
    }
    index = GpcReferenceIndex(nodes, material_placements=[
        {**common, "material_id": "BRUSH-20", "material_name": "平头画笔｜20 mm", "procurement_attributes": {"材质": "尼龙", "宽度": "20 mm"}},
        {**common, "material_id": "BRUSH-30", "material_name": "平头画笔｜30 mm", "procurement_attributes": {"材质": "尼龙", "宽度": "30 mm"}},
    ])

    grouped = index.material_catalog(group_standard_type_codes={"10001674"})

    assert grouped["sku_total"] == 2
    assert grouped["total"] == 1
    assert grouped["grouped_type_count"] == 1
    row = grouped["rows"][0]
    assert row["record_kind"] == "standard_type_group"
    assert row["variant_type_code"] == "10001674"
    assert row["variant_count"] == 2
    assert row["variant_stock_uoms"] == ["支"]
    assert row["stock_uom"] == "支"
    assert row["item_code"] == "10001674"
    assert row["variant_attributes"] == {"宽度": "2 种可选", "材质": "尼龙", "材质等级": "专业级"}

    grouped_all = index.material_catalog(group_all_multi_sku_types=True)
    assert grouped_all["grouped_type_count"] == 1
    assert grouped_all["rows"][0]["record_kind"] == "standard_type_group"


def test_gpc_material_catalog_group_does_not_invent_one_uom_for_mixed_variants() -> None:
    nodes = [
        {"code": "70000000", "name": "Arts", "kind": "segment", "level": 0},
        {"code": "70010000", "name": "Supplies", "kind": "family", "level": 1, "parent_code": "70000000"},
        {"code": "70010100", "name": "Fasteners", "kind": "class", "level": 2, "parent_code": "70010000"},
        {"code": "10003185", "name": "Bolts", "kind": "brick", "level": 3, "parent_code": "70010100"},
    ]
    common = {
        "standard_type": "六角螺栓", "gpc_brick_code": "10003185",
        "completeness_status": "完整", "price_drivers": {"等级": "4.8"},
        "gpc_notes": ["测试"],
    }
    index = GpcReferenceIndex(nodes, material_placements=[
        {**common, "material_id": "B-1", "material_name": "六角螺栓｜M8", "stock_uom": "个", "procurement_attributes": {"规格": "M8"}},
        {**common, "material_id": "B-2", "material_name": "六角螺栓｜M10", "stock_uom": "套", "procurement_attributes": {"规格": "M10"}},
    ])

    row = index.material_catalog(group_all_multi_sku_types=True)["rows"][0]
    assert row["variant_stock_uoms"] == ["个", "套"]
    assert row["stock_uom"] == ""


def test_gpc_material_placements_enforce_procurement_minimum_and_compact_limits() -> None:
    nodes = [
        {"code": "70000000", "name": "Arts", "kind": "segment", "level": 0},
        {"code": "70010000", "name": "Supplies", "kind": "family", "level": 1, "parent_code": "70000000"},
        {"code": "70010100", "name": "Brushes", "kind": "class", "level": 2, "parent_code": "70010000"},
        {"code": "10001674", "name": "Artists Brushes", "kind": "brick", "level": 3, "parent_code": "70010100"},
    ]
    base = {
        "material_id": "MAT-COMPACT",
        "material_name": "平头画笔｜20 mm",
        "standard_type": "画笔",
        "gpc_brick_code": "10001674",
        "stock_uom": "支",
        "completeness_status": "完整",
        "procurement_attributes": {"宽度": "20 mm"},
        "price_drivers": {"材质等级": "专业级"},
        "gpc_notes": ["画笔应归入画笔 Brick"],
    }
    missing = dict(base, price_drivers={})
    with pytest.raises(ValueError, match="三组精简字段"):
        GpcReferenceIndex(nodes, material_placements=[missing])

    too_many = dict(base, procurement_attributes={f"字段{index}": "值" for index in range(5)})
    with pytest.raises(ValueError, match="精简上限"):
        GpcReferenceIndex(nodes, material_placements=[too_many])


def test_nexterp_internal_leaf_is_explicitly_non_gpc_and_keeps_one_attribute() -> None:
    nodes = [
        {"code": "91000000", "name": "Safety", "kind": "segment", "level": 0},
        {"code": "91030000", "name": "Home Safety", "kind": "family", "level": 1, "parent_code": "91000000"},
        {"code": "91030300", "name": "Home/Business Fire Extinguishers", "kind": "class", "level": 2, "parent_code": "91030000"},
        {"code": "10005410", "name": "Variety Packs", "kind": "brick", "level": 3, "parent_code": "91030300"},
    ]
    extensions = [{
        "code": "9103030001",
        "parent_code": "91030300",
        "kind": "internal_brick",
        "level": 3,
        "working_name": "灭火器附属设备",
    }, {
        "code": "910303000101",
        "parent_code": "9103030001",
        "kind": "internal_family",
        "level": 4,
        "working_name": "灭火器箱体",
    }, {
        "code": "91030300010101",
        "parent_code": "910303000101",
        "kind": "internal_type",
        "level": 5,
        "working_name": "灭火器箱",
        "attributes": [{
            "code": "9103030001010101",
            "name": "适配灭火器配置",
            "values": [{"code": "910303000101010101", "name": "2×2 kg手提式灭火器"}],
        }],
    }]
    placements = [{
        "material_id": "LH-GPC-P0043",
        "material_name": "双具灭火器箱｜适配2×2 kg手提式灭火器｜不含灭火器",
        "standard_type": "灭火器箱",
        "gpc_brick_code": "91030300010101",
        "classification_source": "nexterp_internal",
        "stock_uom": "个",
        "completeness_status": "完整",
        "procurement_attributes": {"适配灭火器配置": "2×2 kg手提式灭火器"},
        "price_drivers": {"供货范围": "仅箱体，不含灭火器"},
        "gpc_notes": ["归入灭火器箱标准类型"],
    }]

    index = GpcReferenceIndex(nodes, material_placements=placements, internal_extensions=extensions)

    internal = index.children("910303000101")[0]
    assert internal["code"] == "91030300010101"
    assert internal["is_gpc"] is False
    assert internal["kind_label_zh"] == "标准类型"
    assert [row["code"] for row in index.path(internal["code"])] == [
        "91000000", "91030000", "91030300", "9103030001", "910303000101", "91030300010101",
    ]
    profile = index.profile(internal["code"])
    assert profile["is_gpc"] is False
    assert profile["attributes"][0]["working_name"] == "适配灭火器配置"
    assert profile["actual_materials"][0]["classification_source"] == "nexterp_internal"
    assert index.summary()["counts"]["brick"] == 1
    assert index.summary()["internal_extension_count"] == 3
    assert [level["kind"] for level in index.summary()["levels"]] == [
        "segment", "family", "class", "brick", "internal_family", "internal_type",
    ]


def test_internal_material_family_and_standard_type_extend_an_official_brick() -> None:
    nodes = [
        {"code": "83000000", "name": "Building Products", "kind": "segment", "level": 0},
        {"code": "83010000", "name": "Fixings", "kind": "family", "level": 1, "parent_code": "83000000"},
        {"code": "83011900", "name": "Fasteners", "kind": "class", "level": 2, "parent_code": "83010000"},
        {"code": "10003185", "name": "Bolts/Threaded Rods", "kind": "brick", "level": 3, "parent_code": "83011900"},
    ]
    extensions = [
        {
            "code": "100031850101",
            "parent_code": "1000318501",
            "kind": "internal_type",
            "level": 5,
            "working_name": "六角螺栓",
        },
        {
            "code": "1000318501",
            "parent_code": "10003185",
            "kind": "internal_family",
            "level": 4,
            "working_name": "螺栓",
        },
    ]
    placements = [{
        "material_id": "REF-BOLT-001",
        "material_name": "六角螺栓｜M20×80｜8.8级",
        "standard_type": "六角螺栓",
        "gpc_brick_code": "100031850101",
        "classification_source": "nexterp_internal",
        "stock_uom": "只",
        "completeness_status": "完整",
        "procurement_attributes": {"规格": "M20×80"},
        "price_drivers": {"性能等级": "8.8级"},
        "gpc_notes": ["归入六角螺栓标准类型"],
    }]

    index = GpcReferenceIndex(nodes, material_placements=placements, internal_extensions=extensions)

    family = index.children("10003185")[0]
    assert family["kind"] == "internal_family"
    assert family["kind_label_zh"] == "物料族"
    assert family["actual_material_count"] == 1
    standard_type = index.children(family["code"])[0]
    assert standard_type["kind"] == "internal_type"
    assert standard_type["level"] == 5
    assert standard_type["direct_material_count"] == 1
    assert [row["code"] for row in index.path(standard_type["code"])] == [
        "83000000",
        "83010000",
        "83011900",
        "10003185",
        "1000318501",
        "100031850101",
    ]
    assert index.summary()["internal_counts"] == {
        "internal_brick": 0,
        "internal_family": 1,
        "internal_type": 1,
    }


def test_gpc_material_placements_reject_incomplete_actual_materials() -> None:
    nodes = [
        {"code": "70000000", "name": "Arts", "kind": "segment", "level": 0},
        {"code": "70010000", "name": "Supplies", "kind": "family", "level": 1, "parent_code": "70000000"},
        {"code": "70010100", "name": "Brushes", "kind": "class", "level": 2, "parent_code": "70010000"},
        {"code": "10001674", "name": "Artists Brushes", "kind": "brick", "level": 3, "parent_code": "70010100"},
    ]
    with pytest.raises(ValueError, match="必须完整"):
        GpcReferenceIndex(nodes, material_placements=[{
            "material_id": "MAT-PENDING",
            "material_name": "画笔｜规格待确认",
            "standard_type": "画笔",
            "gpc_brick_code": "10001674",
            "stock_uom": "支",
            "completeness_status": "待补",
            "questions": ["宽度待确认"],
        }])


def test_zip_extraction_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape.txt", "bad")
    with pytest.raises(ValueError, match="路径越界"):
        IMPORTER.safe_extract(archive, tmp_path / "out")


def test_official_source_url_is_allow_listed() -> None:
    assert IMPORTER.validate_official_url("https://ref.gs1.org/standards/gpc/2026-05/")
    with pytest.raises(ValueError, match="官方 HTTPS"):
        IMPORTER.validate_official_url("https://example.com/gpc.zip")


def test_names_translation_defaults_to_one_request_and_binds_source_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    import nexterp_agent.agent_runtime.deepseek_material_request as deepseek

    class Settings:
        model = "test-deepseek"

    calls = []

    monkeypatch.setattr(deepseek, "load_deepseek_settings", lambda: Settings())

    def fake_call(messages, *, settings, **kwargs):
        calls.append(messages)
        payload = json.loads(messages[-1]["content"])
        return {"translations": {item["code"]: f"中文-{item['code']}" for item in payload["items"]}}

    monkeypatch.setattr(deepseek, "call_deepseek_json", fake_call)
    nodes = [{"code": "70000000", "official_name": "Arts"}, {"code": "10001674", "official_name": "Artists Brushes"}]
    rows, metadata = IMPORTER.translate_with_deepseek(nodes)
    assert len(calls) == 1
    assert metadata["mode"] == "deepseek_one_shot"
    assert metadata["status"] == "complete"
    assert metadata["translated_items"] == 2
    assert all(row["status"] == "machine" and row["source_hash"] for row in rows)


def test_service_unified_summary_and_gpc_search(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nexterp_agent.workbench.server import AgentWorkbenchService

    version_root = tmp_path / "2026-05"
    version_root.mkdir()
    nodes = [
        {"code": "70000000", "official_name": "Arts", "name": "Arts", "kind": "segment", "level": 0, "parent_code": None},
        {"code": "10001674", "official_name": "Artists Brushes", "name": "Artists Brushes", "kind": "brick", "level": 3, "parent_code": "70010100"},
    ]
    # The service loader validates full parent chains, so include the small
    # fixture's intermediate levels as well.
    nodes.insert(1, {"code": "70010000", "official_name": "Supplies", "name": "Supplies", "kind": "family", "level": 1, "parent_code": "70000000"})
    nodes.insert(2, {"code": "70010100", "official_name": "Brushes", "name": "Brushes", "kind": "class", "level": 2, "parent_code": "70010000"})
    (version_root / "nodes.jsonl").write_text("\n".join(json.dumps(row) for row in nodes) + "\n", encoding="utf-8")
    (version_root / "brick-profiles.jsonl").write_text('{"code":"10001674","includes":"Includes brushes","attributes":[{"code":"20001337","name":"Type","values":[{"code":"30000001","name":"FLAT"}]}]}\n', encoding="utf-8")
    (version_root / "translations.zh-CN.jsonl").write_text("\n".join(json.dumps({"code": row["code"], "working_name": "", "status": "missing"}) for row in nodes) + "\n", encoding="utf-8")
    (version_root / "profile-translations.zh-CN.jsonl").write_text(
        "\n".join([
            json.dumps({"code":"20001337","working_name":"类型","status":"machine","source_hash":IMPORTER._sha256_bytes(b"Type")}),
            json.dumps({"code":"30000001","working_name":"平头","status":"machine","source_hash":IMPORTER._sha256_bytes(b"FLAT")}),
        ]) + "\n",
        encoding="utf-8",
    )
    official_text = "Includes brushes"
    (version_root / "profile-text-translations.zh-CN.jsonl").write_text(
        json.dumps({"id":"Tfixture","source_hash":IMPORTER._sha256_bytes(official_text.encode()),"official_text":official_text,"working_text":"包括画笔","status":"machine"}) + "\n",
        encoding="utf-8",
    )
    (version_root / "manifest.json").write_text('{"catalog":"gpc","version":"2026-05","hierarchy_complete":true,"counts":{"segment":1,"family":1,"class":1,"brick":1}}', encoding="utf-8")
    import nexterp_agent.workbench.server as server_module
    monkeypatch.setattr(server_module, "GPC_REFERENCE_RUNTIME_ROOT", tmp_path)
    monkeypatch.setattr(server_module, "GPC_MATERIAL_PLACEMENTS_PATH", tmp_path / "no-materials.jsonl")
    service = object.__new__(AgentWorkbenchService)
    summary = service.reference_catalog_summary("gpc")
    assert summary["catalog"] == "gpc"
    assert summary["source_version"] == "2026-05"
    assert summary["levels"][-1]["kind"] == "internal_type"
    assert summary["levels"][-1]["label_zh"] == "标准类型"
    result = service.reference_catalog_search("gpc", "Artists Brushes", limit=1)
    assert result["rows"][0]["code"] == "10001674"
    term = service.reference_catalog_search("gpc", "30000001", limit=1)["rows"][0]
    assert term["result_type"] == "profile_term"
    assert term["working_name"] == "平头"
    assert term["references"][0]["brick_code"] == "10001674"
    assert service.reference_catalog_profile("gpc", "10001674")["attributes"][0]["working_name"] == "类型"
    assert service.reference_catalog_profile("gpc", "10001674")["includes_working"] == "包括画笔"


def test_chatgpt_classification_index_exposes_three_level_preview_and_keeps_colliding_family_codes_separate() -> None:
    payload = {
        "generated_at": "2026-09-02",
        "release_hash": "release-test",
        "classification_label": "ChatGPT 分类（龙华 V4）",
        "rows": [
            {
                "item_code": "MAT0178-V001", "family_code": "MAT0178", "standard_type": "高压清洗机软管",
                "material_name": "高压清洗机软管｜DN20", "top_group": "工具", "sub_group": "清洗设备",
                "segment_code": "CHATGPT-L1-工具", "category_code": "CHATGPT-L2-工具|清洗设备",
                "stock_uom": "条", "procurement_attributes": {"规格": "DN20"}, "price_drivers": {"规格": "DN20"},
            },
            {
                "item_code": "MAT0178-V002", "family_code": "MAT0178", "standard_type": "高压清洗机软管",
                "material_name": "高压清洗机软管｜DN25", "top_group": "管材", "sub_group": "清洗管件",
                "segment_code": "CHATGPT-L1-管材", "category_code": "CHATGPT-L2-管材|清洗管件",
                "stock_uom": "条", "procurement_attributes": {"规格": "DN25"}, "price_drivers": {"规格": "DN25"},
            },
        ],
    }
    index = ChatgptClassificationIndex(payload)
    summary = index.summary()
    assert summary["actual_material_count"] == 2
    assert summary["root_count"] == 2
    type_nodes = index.search("高压清洗机软管", kind="internal_type", limit=10)["rows"]
    assert len(type_nodes) == 2
    codes = {node["code"] for node in type_nodes}
    assert "MAT0178" in codes and len(codes) == 2
    assert any(code.startswith("MAT0178-") for code in codes)
    for node in type_nodes:
        assert node["display_code"].isdigit()
        assert len(node["display_code"]) == 6
        profile = index.profile(node["code"])
        assert profile["actual_material_count"] == 1
        assert profile["classification_source"] == "chatgpt_v4"
