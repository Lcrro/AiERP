from __future__ import annotations

from nexterp_agent.item_master import (
    BatchFactExtraction,
    BatchMaterialIntakeAnalyzer,
    ExtractedMaterialFacts,
    MaterialIntakeRow,
)
from nexterp_agent.item_master.batch_intake import _normalize_extraction_payload


def test_batch_intake_preserves_rows_and_builds_business_queues() -> None:
    rows = [
        MaterialIntakeRow(row_id="1", raw_name="SDS-Plus四坑冲击钻头", raw_spec="φ12*350", qty=1, uom="支"),
        MaterialIntakeRow(row_id="2", raw_name="内六角螺丝", raw_spec="M9*47 碳钢 8.8", qty=20, uom="个"),
        MaterialIntakeRow(row_id="3", raw_name="火星装置", raw_spec="", qty=1, uom="套"),
    ]

    def extract(_: list[MaterialIntakeRow]) -> BatchFactExtraction:
        return BatchFactExtraction(rows=[
            ExtractedMaterialFacts(
                row_id="1",
                query="SDS-Plus四坑冲击钻头",
                attributes={"interface": "SDS-Plus四坑", "diameter": "12mm", "length": "350mm"},
                material_family_hint="钻头",
            ),
            ExtractedMaterialFacts(
                row_id="2",
                query="内六角螺丝",
                attributes={"spec": "M9*47", "material": "碳钢", "strength_grade": "8.8"},
                material_family_hint="螺丝/螺栓",
            ),
            ExtractedMaterialFacts(
                row_id="3",
                query="火星装置",
                ambiguity_note="名称不能确定具体产品。",
            ),
        ])

    result = BatchMaterialIntakeAnalyzer(fact_extractor=extract).analyze(rows)

    assert result.total_rows == 3
    assert result.queue_counts == {"existing_sku": 0, "new_sku": 2, "new_type": 1, "needs_input": 0}
    assert result.decisions[0].queue == "new_sku"
    assert result.decisions[1].standard_name == "内六角螺丝"
    assert result.decisions[2].ambiguity_note == "名称不能确定具体产品。"
    assert result.writes_erpnext is False
    assert [step.stage for step in result.processing_trace] == [
        "read", "extract", "match", "complete", "queue"
    ]
    assert result.processing_trace[0].input_rows == 3
    assert result.processing_trace[1].output_rows == 3
    assert any("已有 SKU 0 行" in item for item in result.processing_trace[-1].details)
    assert any("现有类型新增 SKU 2 行" in item for item in result.processing_trace[-1].details)


def test_batch_intake_rejects_incomplete_deepseek_rows() -> None:
    rows = [MaterialIntakeRow(row_id="1", raw_name="活动扳手", qty=1, uom="把")]

    def extract(_: list[MaterialIntakeRow]) -> BatchFactExtraction:
        return BatchFactExtraction(rows=[ExtractedMaterialFacts(row_id="2", query="活动扳手")])

    try:
        BatchMaterialIntakeAnalyzer(fact_extractor=extract).analyze(rows)
    except ValueError as exc:
        assert "返回行不完整" in str(exc)
    else:
        raise AssertionError("expected incomplete batch to fail")


def test_existing_sku_keeps_field_purchase_unit_without_blocking_intake() -> None:
    rows = [MaterialIntakeRow(row_id="1", raw_name="铁丝14#", qty=10, uom="卷")]

    def extract(_: list[MaterialIntakeRow]) -> BatchFactExtraction:
        return BatchFactExtraction(rows=[
            ExtractedMaterialFacts(row_id="1", query="铁丝", attributes={"spec": "14#"})
        ])

    result = BatchMaterialIntakeAnalyzer(fact_extractor=extract).analyze(rows)

    assert result.decisions[0].queue == "existing_sku"
    assert "报价或收货阶段" in result.decisions[0].standard_completion_note


def test_missing_system_attributes_are_completed_from_standard_sku() -> None:
    rows = [MaterialIntakeRow(row_id="1", raw_name="切割片100", qty=1, uom="盒")]

    def extract(_: list[MaterialIntakeRow]) -> BatchFactExtraction:
        return BatchFactExtraction(rows=[
            ExtractedMaterialFacts(row_id="1", query="切割片", attributes={"diameter": "100mm"})
        ])

    decision = BatchMaterialIntakeAnalyzer(fact_extractor=extract).analyze(rows).decisions[0]

    assert decision.queue == "needs_input"
    assert decision.item_code == ""
    assert {item["attribute_key"] for item in decision.missing_attributes} == {
        "thickness", "bore_diameter", "abrasive_material"
    }


def test_new_sku_inherits_common_defaults_from_standard_type() -> None:
    rows = [MaterialIntakeRow(row_id="1", raw_name="麻花钻头", raw_spec="φ3.2", qty=1, uom="盒")]

    def extract(_: list[MaterialIntakeRow]) -> BatchFactExtraction:
        return BatchFactExtraction(rows=[
            ExtractedMaterialFacts(row_id="1", query="麻花钻头", attributes={"diameter": "3.2mm"})
        ])

    decision = BatchMaterialIntakeAnalyzer(fact_extractor=extract).analyze(rows).decisions[0]

    assert decision.queue == "new_sku"
    assert decision.normalized_attributes["material"] == "高速钢"
    assert decision.normalized_attributes["length"] == "150mm"


def test_field_wording_is_preserved_to_select_standard_welding_rod() -> None:
    rows = [MaterialIntakeRow(row_id="1", raw_name="422型2.5焊条", qty=1, uom="箱")]

    def extract(_: list[MaterialIntakeRow]) -> BatchFactExtraction:
        return BatchFactExtraction(rows=[
            ExtractedMaterialFacts(
                row_id="1",
                query="焊条",
                attributes={"spec": "422型2.5", "diameter": "2.5mm"},
            )
        ])

    decision = BatchMaterialIntakeAnalyzer(fact_extractor=extract).analyze(rows).decisions[0]

    assert decision.queue == "new_sku"
    assert decision.item_code == ""


def test_deepseek_copied_source_columns_are_ignored_at_contract_boundary() -> None:
    normalized = _normalize_extraction_payload({
        "rows": [{
            "row_id": "1",
            "query": "活动扳手",
            "attributes": {"size": "12寸"},
            "top_group_hint": "工具量具",
            "material_family_hint": "扳手",
            "ambiguity_note": "",
            "qty": 1,
            "uom": "把",
        }]
    })

    extraction = BatchFactExtraction.model_validate(normalized)
    assert extraction.rows[0].query == "活动扳手"
