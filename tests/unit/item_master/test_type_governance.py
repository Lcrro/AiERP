from __future__ import annotations

import pytest
from pydantic import ValidationError

from nexterp_agent.item_master.type_governance import (
    AttributeProposal,
    DecisionReview,
    DetailedFamilyMapping,
    DetailedFamilyReview,
    DetailedItemMapping,
    DetailedItemReview,
    DetailedMappingResult,
    DetailedMappingReviewResult,
    FamilyGenerationProposal,
    FamilyReview,
    GovernanceGenerationResult,
    GovernanceReviewResult,
    MaterialTypeProposal,
    NameDecisionProposal,
    approved_detail_family_keys,
    build_family_evidence,
    build_snapshot,
    pack_family_batches,
    stable_type_id,
)


def source_rows() -> list[dict[str, str]]:
    return [
        {
            "item_code": "TOOL-001",
            "item_name": "高速钢麻花钻头",
            "sku_name": "高速钢麻花钻头 Φ6×100mm",
            "required_specs": "材质：高速钢；直径：6mm；总长：100mm",
            "optional_specs": "",
            "aliases": "麻花钻",
            "stock_uom": "支",
            "top_group": "工具耗材",
            "material_family": "钻头",
        },
        {
            "item_code": "TOOL-002",
            "item_name": "高速钢麻花钻头",
            "sku_name": "高速钢麻花钻头 Φ8×120mm",
            "required_specs": "材质：高速钢；直径：8mm；总长：120mm",
            "optional_specs": "",
            "aliases": "麻花钻头",
            "stock_uom": "支",
            "top_group": "工具耗材",
            "material_family": "钻头",
        },
        {
            "item_code": "TOOL-003",
            "item_name": "SDS-Plus四坑冲击钻头",
            "sku_name": "SDS-Plus四坑冲击钻头 Φ12×350mm",
            "required_specs": "接口：SDS-Plus四坑；直径：12mm；总长：350mm",
            "optional_specs": "材质：硬质合金",
            "aliases": "四坑钻头",
            "stock_uom": "支",
            "top_group": "工具耗材",
            "material_family": "钻头",
        },
    ]


def approved_generation_and_review(source_hash: str):
    generation = GovernanceGenerationResult(
        families=[
            FamilyGenerationProposal(
                top_group="工具耗材",
                material_family="钻头",
                source_hash=source_hash,
                types=[
                    MaterialTypeProposal(
                        temporary_key="twist_drill",
                        standard_name="麻花钻头",
                        definition="采用螺旋排屑槽进行金属钻孔的钻头。",
                        includes="普通圆柄麻花钻头。",
                        excludes="冲击钻头和开孔器。",
                        aliases=["麻花钻"],
                        attributes=[
                            AttributeProposal(
                                attribute_key="diameter",
                                display_name="直径",
                                requirement="required",
                                value_type="number",
                                unit="mm",
                            )
                        ],
                    ),
                    MaterialTypeProposal(
                        temporary_key="sds_plus_impact_drill",
                        standard_name="SDS-Plus四坑冲击钻头",
                        definition="使用SDS-Plus接口的混凝土冲击钻头。",
                        includes="二坑二槽及四坑兼容接口。",
                        excludes="SDS-Max五坑接口。",
                        aliases=["四坑钻头"],
                        attributes=[
                            AttributeProposal(
                                attribute_key="diameter",
                                display_name="直径",
                                requirement="required",
                                value_type="number",
                                unit="mm",
                            )
                        ],
                    ),
                ],
                decisions=[
                    NameDecisionProposal(
                        current_name="高速钢麻花钻头",
                        action="rename",
                        target_keys=["twist_drill"],
                        reason="高速钢是SKU材质属性。",
                    ),
                    NameDecisionProposal(
                        current_name="SDS-Plus四坑冲击钻头",
                        action="keep",
                        target_keys=["sds_plus_impact_drill"],
                        reason="接口决定设备兼容性。",
                    ),
                ],
            )
        ]
    )
    review = GovernanceReviewResult(
        families=[
            FamilyReview(
                top_group="工具耗材",
                material_family="钻头",
                source_hash=source_hash,
                verdict="approve",
                type_reviews=[
                    {"temporary_key": "twist_drill", "verdict": "approve", "issue": ""},
                    {
                        "temporary_key": "sds_plus_impact_drill",
                        "verdict": "approve",
                        "issue": "",
                    },
                ],
                decision_reviews=[
                    {"current_name": "高速钢麻花钻头", "verdict": "approve", "issue": ""},
                    {
                        "current_name": "SDS-Plus四坑冲击钻头",
                        "verdict": "approve",
                        "issue": "",
                    },
                ],
                summary="名称维度和属性边界清晰。",
            )
        ]
    )
    return generation, review


def test_build_family_evidence_compacts_skus_by_current_name() -> None:
    families = build_family_evidence(source_rows())

    assert len(families) == 1
    assert families[0].name_count == 2
    evidence_by_name = {item.current_name: item for item in families[0].names}
    assert evidence_by_name["高速钢麻花钻头"].sku_count == 2
    assert families[0].source_hash
    assert "直径" in evidence_by_name["高速钢麻花钻头"].observed_spec_keys


def test_pack_batches_never_splits_a_family() -> None:
    families = build_family_evidence(source_rows())
    batches = pack_family_batches(families, max_names=1)

    assert len(batches) == 1
    assert batches[0].families[0].name_count == 2
    assert batches[0].batch_id.startswith("MGB-")


def test_standard_type_rejects_sku_dimensions() -> None:
    with pytest.raises(ValidationError, match="SKU dimensions"):
        MaterialTypeProposal(
            temporary_key="bad_type",
            standard_name="麻花钻头 Φ12×350mm",
            definition="bad",
            includes="bad",
            excludes="bad",
        )


def test_attribute_proposal_supports_boolean_values() -> None:
    attribute = AttributeProposal(
        attribute_key="is_flame_retardant",
        display_name="是否阻燃",
        requirement="optional",
        value_type="boolean",
    )

    assert attribute.value_type == "boolean"


def test_approved_family_maps_every_exact_name_sku() -> None:
    family = build_family_evidence(source_rows())[0]
    batch = pack_family_batches([family])[0]
    generation, review = approved_generation_and_review(family.source_hash)

    snapshot = build_snapshot(
        batch,
        generation,
        review,
        source_rows(),
        model="generator",
        review_model="reviewer",
    )

    assert snapshot.batch["status"] == "frozen"
    assert len(snapshot.type_dictionary) == 2
    assert len(snapshot.sku_mappings) == 3
    assert not snapshot.issues
    assert {row["standard_name"] for row in snapshot.sku_mappings} == {
        "麻花钻头",
        "SDS-Plus四坑冲击钻头",
    }


def test_reviewer_rejection_blocks_mapping() -> None:
    family = build_family_evidence(source_rows())[0]
    batch = pack_family_batches([family])[0]
    generation, review = approved_generation_and_review(family.source_hash)
    review.families[0].verdict = "revise"
    review.families[0].summary = "名称仍混入材质维度。"

    snapshot = build_snapshot(
        batch,
        generation,
        review,
        source_rows(),
        model="generator",
        review_model="reviewer",
    )

    assert snapshot.batch["status"] == "review_required"
    assert not snapshot.sku_mappings
    assert any(row["issue_type"] == "family_review_not_approved" for row in snapshot.issues)


def test_rejected_family_is_not_sent_to_detailed_mapping() -> None:
    family = build_family_evidence(source_rows())[0]
    family.names[0].current_name = "钻头"
    batch = pack_family_batches([family])[0]
    generation, review = approved_generation_and_review(family.source_hash)
    generation.families[0].decisions[0] = NameDecisionProposal(
        current_name="钻头",
        action="split",
        target_keys=["twist_drill", "sds_plus_impact_drill"],
        reason="需要逐SKU拆分。",
    )
    review.families[0].verdict = "revise"

    assert approved_detail_family_keys(batch, generation, review) == set()


def test_split_decision_requires_detailed_mapping() -> None:
    family = build_family_evidence(source_rows())[0]
    batch = pack_family_batches([family])[0]
    generation, review = approved_generation_and_review(family.source_hash)
    generation.families[0].decisions[0] = NameDecisionProposal(
        current_name="高速钢麻花钻头",
        action="split",
        target_keys=["twist_drill", "sds_plus_impact_drill"],
        reason="现有名称下可能混入两种结构。",
    )

    snapshot = build_snapshot(
        batch,
        generation,
        review,
        source_rows(),
        model="generator",
        review_model="reviewer",
    )

    assert len(snapshot.sku_mappings) == 1
    assert any(row["issue_type"] == "detailed_mapping_required" for row in snapshot.issues)


def test_generic_family_name_uses_full_detailed_sku_mapping() -> None:
    rows = [
        {
            "item_code": "TOOL-GENERIC-001",
            "item_name": "钻头",
            "sku_name": "高速钢麻花钻头 6mm",
            "required_specs": "材质：高速钢；直径：6mm",
            "optional_specs": "",
            "aliases": "麻花钻",
            "stock_uom": "支",
            "top_group": "工具耗材",
            "material_family": "钻头",
        },
        {
            "item_code": "TOOL-GENERIC-002",
            "item_name": "钻头",
            "sku_name": "SDS-Plus冲击钻头 12mm",
            "required_specs": "接口：SDS-Plus；直径：12mm",
            "optional_specs": "",
            "aliases": "四坑钻",
            "stock_uom": "支",
            "top_group": "工具耗材",
            "material_family": "钻头",
        },
    ]
    family = build_family_evidence(rows)[0]
    batch = pack_family_batches([family])[0]
    generation = GovernanceGenerationResult(
        families=[
            FamilyGenerationProposal(
                top_group="工具耗材",
                material_family="钻头",
                source_hash=family.source_hash,
                types=[
                    MaterialTypeProposal(
                        temporary_key="twist_drill",
                        standard_name="麻花钻头",
                        definition="具有螺旋排屑槽的钻头。",
                        includes="金属钻孔麻花钻头。",
                        excludes="冲击钻头。",
                    ),
                    MaterialTypeProposal(
                        temporary_key="sds_plus_drill",
                        standard_name="SDS-Plus冲击钻头",
                        definition="使用SDS-Plus接口的冲击钻头。",
                        includes="四坑兼容冲击钻头。",
                        excludes="普通麻花钻头。",
                    ),
                ],
                decisions=[
                    NameDecisionProposal(
                        current_name="钻头",
                        action="split",
                        target_keys=["twist_drill", "sds_plus_drill"],
                        reason="旧名称混合了两种结构，必须逐SKU判断。",
                    )
                ],
            )
        ]
    )
    review = GovernanceReviewResult(
        families=[
            FamilyReview(
                top_group="工具耗材",
                material_family="钻头",
                source_hash=family.source_hash,
                verdict="approve",
                type_reviews=[
                    {"temporary_key": "twist_drill", "verdict": "approve"},
                    {"temporary_key": "sds_plus_drill", "verdict": "approve"},
                ],
                decision_reviews=[{"current_name": "钻头", "verdict": "approve"}],
                summary="边界清晰。",
            )
        ]
    )
    detailed = DetailedMappingResult(
        families=[
            DetailedFamilyMapping(
                top_group="工具耗材",
                material_family="钻头",
                source_hash=family.source_hash,
                mappings=[
                    DetailedItemMapping(
                        item_code="TOOL-GENERIC-001",
                        target_key="twist_drill",
                        extracted_attributes={"material": "高速钢"},
                        reason="SKU名称明确写明麻花钻头。",
                        confidence=0.98,
                    ),
                    DetailedItemMapping(
                        item_code="TOOL-GENERIC-002",
                        target_key="sds_plus_drill",
                        extracted_attributes={"interface": "SDS-Plus"},
                        reason="SKU名称和规格均明确接口。",
                        confidence=0.99,
                    ),
                ],
            )
        ]
    )
    detailed_review = DetailedMappingReviewResult(
        families=[
            DetailedFamilyReview(
                top_group="工具耗材",
                material_family="钻头",
                source_hash=family.source_hash,
                verdict="approve",
                item_reviews=[
                    DetailedItemReview(item_code="TOOL-GENERIC-001", verdict="approve"),
                    DetailedItemReview(item_code="TOOL-GENERIC-002", verdict="approve"),
                ],
                summary="两条SKU证据足以区分类型。",
            )
        ]
    )

    snapshot = build_snapshot(
        batch,
        generation,
        review,
        rows,
        model="generator",
        review_model="reviewer",
        detailed_mapping=detailed,
        detailed_review=detailed_review,
    )

    assert snapshot.batch["status"] == "frozen"
    assert len(snapshot.sku_mappings) == 2
    assert {row["mapping_method"] for row in snapshot.sku_mappings} == {"detailed_evidence"}
    assert {row["standard_name"] for row in snapshot.sku_mappings} == {
        "麻花钻头",
        "SDS-Plus冲击钻头",
    }


def test_detailed_mapping_must_cover_every_sku() -> None:
    rows = source_rows()
    rows[0]["item_name"] = "钻头"
    rows[1]["item_name"] = "钻头"
    family = build_family_evidence(rows)[0]
    batch = pack_family_batches([family])[0]
    generation, review = approved_generation_and_review(family.source_hash)
    generation.families[0].decisions[0] = NameDecisionProposal(
        current_name="钻头",
        action="split",
        target_keys=["twist_drill", "sds_plus_impact_drill"],
        reason="旧名称需要逐SKU拆分。",
    )
    generation.families[0].decisions = [generation.families[0].decisions[0], generation.families[0].decisions[1]]
    review.families[0].decision_reviews[0] = DecisionReview(
        current_name="钻头", verdict="approve"
    )
    detailed = DetailedMappingResult(
        families=[
            DetailedFamilyMapping(
                top_group="工具耗材",
                material_family="钻头",
                source_hash=family.source_hash,
                mappings=[
                    DetailedItemMapping(
                        item_code="TOOL-001",
                        target_key="twist_drill",
                        reason="只故意提供一条映射。",
                        confidence=0.99,
                    )
                ],
            )
        ]
    )
    detailed_review = DetailedMappingReviewResult(
        families=[
            DetailedFamilyReview(
                top_group="工具耗材",
                material_family="钻头",
                source_hash=family.source_hash,
                verdict="approve",
                item_reviews=[DetailedItemReview(item_code="TOOL-001", verdict="approve")],
                summary="复核通过输入中已有的一条。",
            )
        ]
    )

    snapshot = build_snapshot(
        batch,
        generation,
        review,
        rows,
        model="generator",
        review_model="reviewer",
        detailed_mapping=detailed,
        detailed_review=detailed_review,
    )

    assert snapshot.batch["status"] == "review_required"
    assert not snapshot.sku_mappings
    assert any(row["issue_type"] == "detailed_mapping_coverage" for row in snapshot.issues)


def test_every_unmapped_sku_gets_an_explicit_issue() -> None:
    rows = source_rows()
    family = build_family_evidence(rows)[0]
    batch = pack_family_batches([family])[0]
    generation, review = approved_generation_and_review(family.source_hash)
    generation.families[0].decisions[0] = NameDecisionProposal(
        current_name="高速钢麻花钻头",
        action="split",
        target_keys=["twist_drill", "sds_plus_impact_drill"],
        reason="测试延期详细映射。",
    )

    snapshot = build_snapshot(
        batch,
        generation,
        review,
        rows,
        model="generator",
        review_model="reviewer",
    )

    mapped_codes = {row["item_code"] for row in snapshot.sku_mappings}
    issue_codes = {
        row["item_code"]
        for row in snapshot.issues
        if row["issue_type"] == "sku_mapping_unresolved"
    }
    assert {row["item_code"] for row in rows} == mapped_codes | issue_codes
    assert snapshot.batch["status"] == "review_required"


def test_type_id_is_stable() -> None:
    first = stable_type_id("工具耗材", "钻头", "麻花钻头")
    second = stable_type_id("工具耗材", "钻头", " 麻花钻头 ")

    assert first == second
    assert first.startswith("MT-")
