from nexterp_agent.item_master import (
    HighRecallBatchResult,
    MaterialIntakeDecision,
    MaterialTypeClassifier,
    RuntimeMaterialPublicationStore,
    build_material_drafts,
    revise_material_drafts,
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


def test_new_type_decision_builds_editable_type_and_first_sku_draft():
    classifier = MaterialTypeClassifier()
    decision = MaterialIntakeDecision(
        row_id="9",
        raw_name="特种测试喷头",
        raw_spec="X1",
        qty=1,
        uom="个",
        queue="new_type",
        queue_label="需要新增标准类型",
        top_group_hint="工具耗材",
        material_family_hint="喷头",
        normalized_attributes={"model": "X1", "uom": "个"},
        reason="没有可信现有类型候选",
    )
    result = HighRecallBatchResult(
        total_rows=1,
        queue_counts={"existing_sku": 0, "new_sku": 0, "new_type": 1, "needs_input": 0},
        decisions=[decision],
    )

    batch = build_material_drafts("analysis-new-type", result, classifier)
    draft = batch.drafts[0]

    assert draft.action == "create_type_and_sku"
    assert draft.material_type.is_new is True
    assert draft.material_type.standard_name == "特种测试喷头"
    assert draft.material_type.attributes[0]["attribute_key"] == "model"
    assert draft.item_code.startswith("MAT-")
    assert draft.validation_errors == []
    assert draft.frozen_hash


def test_draft_revision_recompiles_new_type_without_accepting_raw_item_doc():
    classifier = MaterialTypeClassifier()
    decision = MaterialIntakeDecision(
        row_id="10",
        raw_name="临时喷头",
        raw_spec="X2",
        qty=1,
        uom="个",
        queue="new_type",
        queue_label="需要新增标准类型",
        normalized_attributes={"model": "X2", "uom": "个"},
        reason="测试",
    )
    result = HighRecallBatchResult(
        total_rows=1,
        queue_counts={"existing_sku": 0, "new_sku": 0, "new_type": 1, "needs_input": 0},
        decisions=[decision],
    )
    batch = build_material_drafts("analysis-revise", result, classifier)
    draft_id = batch.drafts[0].draft_id

    revised = revise_material_drafts(batch, [{
        "draft_id": draft_id,
        "top_group": "工具耗材",
        "material_family": "喷头",
        "standard_name": "特种测试喷头",
        "item_group": "工具耗材",
        "code_prefix": "TEST-NOZZLE",
        "normalized_attributes": {"model": "X2"},
        "stock_uom": "个",
    }], classifier)

    assert revised.drafts[0].revision == 2
    assert revised.drafts[0].item_code == "TEST-NOZZLE-000001"
    assert revised.drafts[0].item_name == "特种测试喷头 X2"
    assert revised.drafts[0].validation_errors == []

    try:
        revise_material_drafts(batch, [{"draft_id": draft_id, "item_doc": {"disabled": 1}}], classifier)
    except ValueError as exc:
        assert "不允许" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("raw item_doc update should be rejected")


def test_verified_runtime_publication_is_recalled_as_existing_sku(tmp_path):
    store = RuntimeMaterialPublicationStore(tmp_path / "publications.jsonl")
    item_doc = {
        "item_code": "1000999900001",
        "item_name": "特种测试喷头 X1",
        "item_group": "工具耗材",
        "stock_uom": "个",
        "description": "test",
        "disabled": 0,
        "is_stock_item": 1,
        "is_purchase_item": 1,
        "is_sales_item": 0,
        "include_item_in_manufacturing": 0,
    }
    store.record_verified(
        request_id="publish-1",
        draft_id="draft-1",
        analysis_id="analysis-1",
        confirmed_by="buyer@example.com",
        material_type={
            "type_id": "MT-TEST-NOZZLE",
            "top_group": "工具耗材",
            "material_family": "喷头",
            "standard_name": "特种测试喷头",
            "definition": "测试类型",
            "includes": "特种测试喷头",
            "excludes": "",
            "aliases": ["测试喷头"],
            "attributes": [{
                "attribute_key": "model",
                "display_name": "型号",
                "requirement": "required",
                "value_type": "text",
                "unit": "",
                "enum_values": [],
                "affects_sku_identity": True,
                "description": "型号",
            }],
            "item_group": "工具耗材",
        "code_prefix": "10009999",
            "is_new": True,
        },
        sku={
            "item_code": item_doc["item_code"],
            "type_id": "MT-TEST-NOZZLE",
            "standard_name": "特种测试喷头",
            "item_name": item_doc["item_name"],
            "sku_name": item_doc["item_name"],
            "item_group": item_doc["item_group"],
            "stock_uom": item_doc["stock_uom"],
            "required_specs": "型号：X1",
            "optional_specs": "",
            "item_doc": item_doc,
            "erpnext_readback": {**item_doc, "name": item_doc["item_code"]},
        },
    )

    classifier = MaterialTypeClassifier(runtime_publications=store.active())
    result = classifier.classify(
        item_doc["item_code"],
        attributes={"model": "X1", "uom": "个"},
        top_group_hint="工具耗材",
        material_family_hint="喷头",
    )

    assert result.status == "existing_sku"
    assert result.existing_sku["item_code"] == "1000999900001"
