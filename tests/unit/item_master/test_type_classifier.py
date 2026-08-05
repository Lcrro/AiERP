from __future__ import annotations

from nexterp_agent.item_master import MaterialTypeClassifier


def test_classifier_resolves_compatibility_alias_to_existing_sku() -> None:
    result = MaterialTypeClassifier().classify(
        "SDS-Plus四坑冲击钻头 12x350mm",
        attributes={
            "interface": "SDS-Plus四坑",
            "diameter": "12mm",
            "overall_length": "350mm",
            "material": "硬质合金",
        },
        material_family_hint="钻头",
    )

    assert result.status == "existing_sku"
    assert result.selected_type is not None
    assert result.selected_type.standard_name == "二坑二槽钻头"
    assert result.existing_sku is not None
    assert result.existing_sku["item_code"] == "TOOL-000328"
    assert result.normalized_attributes["length"] == "350mm"
    diameter = next(row for row in result.selected_type.attributes if row["attribute_key"] == "diameter")
    assert diameter["description"] == "成品、接口或加工直径，使用明确数值和单位。"


def test_classifier_requires_choice_for_a_broad_family_name() -> None:
    result = MaterialTypeClassifier().classify("钻头", material_family_hint="钻头")

    assert result.status == "needs_choice"
    assert len(result.type_candidates) >= 2
    assert result.ready_to_create is False


def test_classifier_does_not_invent_required_attributes() -> None:
    result = MaterialTypeClassifier().classify(
        "内六角螺丝 M9*47",
        attributes={"spec": "M9*47"},
        material_family_hint="螺丝/螺栓",
    )

    assert result.status == "needs_input"
    assert [row["attribute_key"] for row in result.missing_attributes] == ["material"]
    assert result.ready_to_create is False


def test_classifier_identifies_a_complete_new_sku_without_writing() -> None:
    result = MaterialTypeClassifier().classify(
        "内六角螺丝 M9*47 碳钢 12.9级 发黑",
        attributes={
            "spec": "M9*47",
            "material": "碳钢",
            "strength_grade": "12.9",
            "surface_treatment": "发黑",
        },
        material_family_hint="螺丝/螺栓",
    )

    assert result.status == "new_sku"
    assert result.selected_type is not None
    assert result.selected_type.standard_name == "内六角螺丝"
    assert result.existing_sku is None
    assert result.ready_to_create is True


def test_classifier_escalates_an_unknown_type() -> None:
    result = MaterialTypeClassifier().classify("一种全新的量子施工材料")

    assert result.status == "new_type_review"
    assert result.selected_type is None
    assert result.ready_to_create is False
