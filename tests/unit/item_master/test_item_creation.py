from __future__ import annotations

from nexterp_agent.item_master import ItemMasterCreationPlanner, MaterialTypeClassifier


def test_new_sku_is_compiled_from_frozen_type_and_existing_codes() -> None:
    classifier = MaterialTypeClassifier()
    planner = ItemMasterCreationPlanner(classifier)
    classification = planner.classify(
        "内六角螺丝 M9*47 碳钢",
        attributes={"spec": "M9*47", "material": "碳钢", "strength_grade": "8.8"},
        material_family_hint="螺丝/螺栓",
    )

    assert classification.status == "new_sku"
    draft = planner.build_draft(classification, existing_item_codes=["FAST-999999"])

    assert draft.type_id == "MT-275FAE855873"
    assert draft.item_code == "FAST-1000000"
    assert draft.sku_name == "内六角螺丝 M9*47 碳钢 8.8"
    assert draft.item_group == "紧固件与连接件/螺丝/螺栓"
    assert draft.stock_uom == "个"
    assert draft.required_specs == "规格：M9*47；材质：碳钢"
    assert draft.optional_specs == "强度等级：8.8"
    assert draft.item_doc["item_code"] == draft.item_code
    assert draft.item_doc["item_name"] == draft.sku_name


def test_existing_sku_cannot_be_compiled_as_a_new_item() -> None:
    planner = ItemMasterCreationPlanner()
    classification = planner.classify(
        "SDS-Plus四坑冲击钻头 12mm 350mm",
        attributes={"interface": "SDS-Plus四坑", "diameter": "12mm", "length": "350mm"},
        material_family_hint="钻头",
    )

    assert classification.status == "existing_sku"


def test_different_drill_diameter_does_not_reuse_resolver_top_hit() -> None:
    classification = ItemMasterCreationPlanner().classify(
        "麻花钻头",
        attributes={"diameter": "3.2mm", "uom": "盒"},
        material_family_hint="钻头",
    )

    assert classification.status != "existing_sku"


def test_generic_partial_alias_does_not_turn_mig_gun_into_plastic_welding_gun() -> None:
    classification = ItemMasterCreationPlanner().classify(
        "二保焊枪",
        attributes={"model": "500A", "length": "6m"},
    )

    assert classification.status == "new_type_review"


def test_common_size_is_aligned_to_type_specific_gauge() -> None:
    classification = ItemMasterCreationPlanner().classify(
        "铁丝",
        attributes={"size": "14#"},
    )

    assert classification.normalized_attributes["gauge"] == "14#"
    assert classification.status == "existing_sku"
    assert classification.existing_sku["item_code"] == "METAL-000067"


def test_common_diameter_is_aligned_to_cutting_disc_outer_diameter() -> None:
    classification = ItemMasterCreationPlanner().classify(
        "切割片",
        attributes={"diameter": "100mm"},
    )

    assert classification.normalized_attributes["outer_diameter"] == "100mm"
    assert {item["attribute_key"] for item in classification.missing_attributes} == {
        "thickness",
        "bore_diameter",
        "abrasive_material",
    }
