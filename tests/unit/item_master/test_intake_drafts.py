from nexterp_agent.item_master import (
    HighRecallBatchResult,
    MaterialIntakeDecision,
    MaterialTypeClassifier,
    build_material_drafts,
)


def _fixture_result(classifier: MaterialTypeClassifier) -> HighRecallBatchResult:
    type_row = next(item for item in classifier.types if classifier.release_rows_for_type(item.type_id))
    release_row = classifier.release_rows_for_type(type_row.type_id)[0]
    decision = MaterialIntakeDecision(
        row_id="1",
        raw_name=type_row.standard_name,
        raw_spec="测试规格",
        qty=2,
        uom=str(release_row.get("stock_uom") or "个"),
        queue="new_sku",
        queue_label="现有类型新增 SKU",
        type_id=type_row.type_id,
        normalized_attributes={"uom": str(release_row.get("stock_uom") or "个"), "material": "测试材质"},
        reason="测试用的已复核结论",
    )
    return HighRecallBatchResult(
        total_rows=1,
        queue_counts={"existing_sku": 0, "new_sku": 1, "new_type": 0, "needs_input": 0},
        decisions=[decision],
    )


def test_build_material_drafts_is_deterministic_and_does_not_write():
    classifier = MaterialTypeClassifier()
    batch = build_material_drafts("analysis-1", _fixture_result(classifier), classifier)

    assert batch.analysis_id == "analysis-1"
    assert batch.writes_erpnext is False
    assert len(batch.drafts) == 1
    assert batch.drafts[0].item_code
    assert batch.drafts[0].item_doc["item_code"] == batch.drafts[0].item_code
    assert batch.processing_step["stage"] == "draft"


def test_duplicate_new_sku_decisions_are_merged_into_one_draft():
    classifier = MaterialTypeClassifier()
    result = _fixture_result(classifier)
    duplicate = result.decisions[0].model_copy(update={"row_id": "2", "raw_name": "同义叫法"})
    result = result.model_copy(
        update={
            "total_rows": 2,
            "queue_counts": {"existing_sku": 0, "new_sku": 2, "new_type": 0, "needs_input": 0},
            "decisions": [result.decisions[0], duplicate],
        }
    )

    batch = build_material_drafts("analysis-2", result, classifier)

    assert len(batch.drafts) == 1
    assert batch.drafts[0].source_rows == ["1", "2"]
    assert batch.drafts[0].source_names == [result.decisions[0].raw_name, "同义叫法"]


def test_existing_sku_decision_is_skipped():
    classifier = MaterialTypeClassifier()
    result = _fixture_result(classifier)
    result = result.model_copy(
        update={
            "queue_counts": {"existing_sku": 1, "new_sku": 0, "new_type": 0, "needs_input": 0},
            "decisions": [result.decisions[0].model_copy(update={"queue": "existing_sku", "queue_label": "已有 SKU"})],
        }
    )

    batch = build_material_drafts("analysis-3", result, classifier)

    assert batch.drafts == []
    assert batch.skipped[0]["row_id"] == "1"
