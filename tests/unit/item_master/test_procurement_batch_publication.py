from __future__ import annotations

from nexterp_agent.item_master.procurement_batch_publication import (
    ProcurementBatchGpcPublisher,
    _split_value,
)


def test_split_value_only_explodes_an_exact_number_of_source_variants() -> None:
    assert _split_value("M12×40/M8×30/M10×20", 3) == ["M12×40", "M8×30", "M10×20"]
    assert _split_value("M12/M8", 3) is None
    assert _split_value("单一规格", 1) is None


def test_duplicate_actual_materials_merge_source_provenance_without_cartesian_generation() -> None:
    base = {
        "material_id": "LH-GPC-P0054",
        "source_rows": [54],
        "standard_type": "大号垃圾袋",
        "gpc_brick_code": "10001761",
        "procurement_attributes": {"尺寸": "1200×1400 mm", "颜色": "黑色", "材质": "PE"},
    }
    duplicate = {**base, "material_id": "LH-GPC-P0101", "source_rows": [101]}

    merged = ProcurementBatchGpcPublisher._merge_duplicate_materials([base, duplicate])

    assert len(merged) == 1
    assert merged[0]["material_id"] == "LH-GPC-P0054"
    assert merged[0]["source_rows"] == [54, 101]


def test_existing_workbench_material_collects_repeated_purchase_rows() -> None:
    materials = [{"material_id": "LH-GPC-C003", "source_rows": [4, 10]}]
    decisions = [{
        "queue": "existing_candidate",
        "source_rows": [4, 10, 83],
        "material_candidate": {"material_id": "LH-GPC-C003"},
    }]

    merged = ProcurementBatchGpcPublisher._merge_existing_source_rows(materials, decisions)

    assert merged[0]["source_rows"] == [4, 10, 83]


def test_reviewed_material_can_receive_traceable_post_freeze_curation() -> None:
    publisher = object.__new__(ProcurementBatchGpcPublisher)
    publisher._base_placement = lambda **kwargs: kwargs
    release = {"reviews": [{
        "cluster_id": "CL-HOSE",
        "materialization": "ready",
        "source_rows": [37],
        "action": "approved",
        "rationale": "original frozen rationale",
        "final_material": {
            "standard_type": "透明钢丝增强软管",
            "gpc_brick_code": "10003254",
            "main_template_id": "linear_cut_material",
            "constraint_ids": ["pressure_fluid"],
            "stock_uom": "米",
            "procurement_attributes": {"公称直径": "Φ50"},
            "price_drivers": {"质量等级": "合格品"},
        },
    }]}
    curation = {"CL-HOSE": {
        "standard_type": "排水泵用透明钢丝增强吸水软管",
        "gpc_brick_code": "10008364",
        "gpc_mapping_quality": "broad_fallback",
        "specification_basis": "用户确认用于工地排水泵",
        "variants": [{
            "source_rows": [37],
            "material_name": "排水泵用透明钢丝增强吸水软管｜Φ50",
            "procurement_attributes": {"公称直径": "Φ50", "用途": "排水泵吸水端"},
            "price_drivers": {"质量要求": "耐负压防吸扁"},
        }],
    }}

    materials, specs = publisher._reviewed_materials("job", release, curation)

    assert len(materials) == 1
    assert materials[0]["gpc_code"] == "10008364"
    assert materials[0]["standard_type"] == "排水泵用透明钢丝增强吸水软管"
    assert materials[0]["mapping_quality"] == "broad_fallback"
    assert materials[0]["specification_basis"] == "用户确认用于工地排水泵"
    assert specs[("排水泵用透明钢丝增强吸水软管", "10008364")] == {
        "main_template_id": "linear_cut_material",
        "constraint_ids": ["pressure_fluid"],
    }
