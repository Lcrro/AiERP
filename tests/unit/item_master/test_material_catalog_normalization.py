from __future__ import annotations

from nexterp_agent.item_master.material_catalog_normalization import (
    canonical_material_name,
    canonical_standard_type,
    hierarchical_child_code,
    normalize_workbench_catalog,
)


def test_fastener_name_has_one_fixed_business_order() -> None:
    actual = canonical_material_name({
        "standard_type": "外六角螺栓",
        "procurement_attributes": {
            "性能等级": "8.8级",
            "螺纹形式": "全牙",
            "规格": "M14×160 mm",
        },
        "price_drivers": {"表面处理": "镀锌"},
    })

    assert actual == "六角螺栓｜M14×160｜镀锌｜8.8级｜全牙"


def test_direct_gpc_material_is_moved_to_a_private_standard_type() -> None:
    materials = [{
        "material_id": "M-1",
        "procurement_profile_id": "P-1",
        "standard_type": "直管荧光灯",
        "material_name": "T5直管荧光灯｜28 W",
        "gpc_brick_code": "10000552",
        "classification_source": "gpc",
        "procurement_attributes": {"规格": "T5，28 W"},
        "price_drivers": {"质量要求": "可靠"},
        "gpc_notes": ["按 GPC Brick 10000552 归类", "只录入实际组合"],
        "specification_basis": "Nexterp内部类目 NXT-OLD-TYPE",
    }]
    profiles = [{
        "profile_id": "P-1",
        "standard_type": "直管荧光灯",
        "gpc_brick_code": "10000552",
        "sku_identity_fields": ["procurement_attributes.规格"],
    }]

    normalized_materials, normalized_profiles, extensions, report = normalize_workbench_catalog(
        materials, profiles, []
    )

    family_code = hierarchical_child_code("10000552", 1)
    expected = hierarchical_child_code(family_code, 1)
    assert normalized_materials[0]["gpc_brick_code"] == expected
    assert normalized_profiles[0]["gpc_brick_code"] == expected
    assert normalized_materials[0]["classification_source"] == "nexterp_internal"
    assert normalized_materials[0]["material_name"] == "直管荧光灯｜T5，28 W"
    assert normalized_materials[0]["gpc_notes"] == ["归入“直管荧光灯”标准类型", "只录入实际组合"]
    assert "NXT-" not in normalized_materials[0]["specification_basis"]
    assert [(row["kind"], row["working_name"]) for row in extensions] == [
        ("internal_family", "光源"),
        ("internal_type", "直管荧光灯"),
    ]
    assert all(row["catalog_origin"] == "nexterp" for row in extensions)
    assert report["direct_gpc_material_count"] == 0
    assert report["created_material_family_count"] == 1


def test_existing_material_family_is_reused_for_screw_types() -> None:
    family = {
        "code": "1000318101",
        "parent_code": "10003181",
        "kind": "internal_family",
        "level": 4,
        "working_name": "螺钉",
    }
    material = {
        "material_id": "M-2",
        "standard_type": "十字盘头自攻螺钉",
        "material_name": "十字盘头自攻螺钉｜ST4.2×32 mm",
        "gpc_brick_code": "10003181",
        "procurement_attributes": {"规格": "ST4.2×32 mm"},
        "price_drivers": {"表面处理": "镀锌"},
    }

    rows, _, extensions, _ = normalize_workbench_catalog([material], [], [family])

    target = next(row for row in extensions if row.get("kind") == "internal_type")
    assert target["parent_code"] == family["code"]
    assert rows[0]["gpc_brick_code"] == target["code"]


def test_alias_profiles_are_merged_and_materials_are_repointed() -> None:
    extension = {
        "code": "1000318501",
        "parent_code": "10003185",
        "kind": "internal_type",
        "level": 4,
        "working_name": "六角螺栓",
    }
    materials = [
        {
            "material_id": "M-A",
            "procurement_profile_id": "P-OLD",
            "standard_type": "外六角螺栓",
            "material_name": "8.8级外六角螺栓｜M8×30",
            "gpc_brick_code": "1000318501",
            "procurement_attributes": {"规格": "M8×30", "性能等级": "8.8级"},
            "price_drivers": {"表面处理": "镀锌"},
        },
        {
            "material_id": "M-B",
            "procurement_profile_id": "P-REF",
            "standard_type": "六角螺栓",
            "material_name": "六角螺栓｜M10×40｜4.8级",
            "gpc_brick_code": "1000318501",
            "procurement_attributes": {"规格": "M10×40"},
            "price_drivers": {"性能/质量等级": "4.8级"},
        },
    ]
    profiles = [
        {"profile_id": "P-OLD", "standard_type": "外六角螺栓", "gpc_brick_code": "1000318501", "source_material_ids": ["M-A"]},
        {"profile_id": "P-REF", "standard_type": "六角螺栓", "gpc_brick_code": "1000318501", "source_material_ids": ["M-B", "M-C"]},
    ]

    rows, normalized_profiles, _, report = normalize_workbench_catalog(materials, profiles, [extension])

    assert len(normalized_profiles) == 1
    assert normalized_profiles[0]["profile_id"] == "P-REF"
    assert {row["procurement_profile_id"] for row in rows} == {"P-REF"}
    assert report["merged_profile_count"] == 1


def test_legacy_internal_tree_is_renumbered_by_two_digits_per_level() -> None:
    extensions = [
        {
            "code": "NXT-FAMILY",
            "parent_code": "10003185",
            "kind": "internal_family",
            "level": 4,
            "working_name": "螺栓",
        },
        {
            "code": "NXT-TYPE-HEX",
            "parent_code": "NXT-FAMILY",
            "kind": "internal_type",
            "level": 5,
            "working_name": "六角螺栓",
        },
    ]
    materials = [{
        "material_id": "M-HEX",
        "standard_type": "六角螺栓",
        "material_name": "六角螺栓｜M8×30",
        "gpc_brick_code": "NXT-TYPE-HEX",
        "internal_category_code": "NXT-TYPE-HEX",
        "procurement_attributes": {"规格": "M8×30"},
    }]

    rows, _, normalized_extensions, report = normalize_workbench_catalog(materials, [], extensions)

    assert [row["code"] for row in normalized_extensions] == ["1000318501", "100031850101"]
    assert rows[0]["gpc_brick_code"] == "100031850101"
    assert rows[0]["internal_category_code"] == "100031850101"
    assert report["legacy_nxt_reference_count"] == 0


def test_socket_head_screw_aliases_share_one_type_and_attribute_schema() -> None:
    extensions = [
        {
            "code": "1000318101",
            "parent_code": "10003181",
            "kind": "internal_family",
            "level": 4,
            "working_name": "螺钉",
        },
        {
            "code": "100031810104",
            "parent_code": "1000318101",
            "kind": "internal_type",
            "level": 5,
            "working_name": "内六角螺钉",
        },
        {
            "code": "100031810107",
            "parent_code": "1000318101",
            "kind": "internal_type",
            "level": 5,
            "working_name": "内六角圆柱头螺钉",
        },
    ]
    materials = [
        {
            "material_id": "SOCKET-8",
            "standard_type": "内六角圆柱头螺钉",
            "material_name": "内六角圆柱头螺钉｜M8×15｜发黑｜8.8级",
            "gpc_brick_code": "100031810107",
            "procurement_attributes": {"头型": "圆柱头", "性能等级": "8.8级", "规格": "M8×15"},
            "price_drivers": {"表面处理": "发黑", "质量要求": "内六角孔无变形"},
        },
        {
            "material_id": "SOCKET-12",
            "standard_type": "内六角螺钉",
            "material_name": "内六角螺钉｜M12×40",
            "gpc_brick_code": "100031810104",
            "procurement_attributes": {"供货范围": "单件", "规格": "M12×40 mm"},
            "price_drivers": {"性能/质量等级": "4.8级", "材质/表面处理": "碳钢常规防锈"},
        },
    ]

    profiles = [
        {
            "profile_id": "SOCKET-GENERAL",
            "standard_type": "内六角螺钉",
            "gpc_brick_code": "100031810104",
            "source_material_ids": ["SOCKET-12"],
            "sku_identity_fields": ["procurement_attributes.规格"],
        },
        {
            "profile_id": "SOCKET-CAP",
            "standard_type": "内六角圆柱头螺钉",
            "gpc_brick_code": "100031810107",
            "source_material_ids": ["SOCKET-8"],
            "sku_identity_fields": ["procurement_attributes.头型"],
        },
    ]
    rows, normalized_profiles, normalized_extensions, _ = normalize_workbench_catalog(materials, profiles, extensions)

    assert {row["standard_type"] for row in rows} == {"内六角螺钉"}
    assert {row["gpc_brick_code"] for row in rows} == {"100031810104"}
    assert [row["code"] for row in normalized_extensions] == ["1000318101", "100031810104"]
    assert {tuple(row["procurement_attributes"]) for row in rows} == {
        ("头型", "规格", "供货范围"),
        ("供货范围", "规格", "头型"),
    }
    assert all("性能/质量等级" in row["price_drivers"] for row in rows)
    assert all("材质/表面处理" in row["price_drivers"] for row in rows)
    assert len(normalized_profiles) == 1
    assert normalized_profiles[0]["sku_identity_fields"] == [
        "procurement_attributes.规格",
        "procurement_attributes.头型",
        "procurement_attributes.供货范围",
        "price_drivers.材质/表面处理",
        "price_drivers.性能/质量等级",
    ]


def test_uniform_hierarchy_is_idempotent() -> None:
    material = {
        "material_id": "M-LAMP",
        "standard_type": "直管荧光灯",
        "material_name": "直管荧光灯｜T5，28 W",
        "gpc_brick_code": "10000552",
        "procurement_attributes": {"规格": "T5，28 W"},
    }

    first = normalize_workbench_catalog([material], [], [])
    second = normalize_workbench_catalog(first[0], first[1], first[2])

    assert second[0] == first[0]
    assert second[1] == first[1]
    assert second[2] == first[2]
    assert second[3]["created_material_family_count"] == 0
    assert second[3]["reparented_standard_type_count"] == 0


def test_fastener_default_provenance_does_not_create_false_selector_values() -> None:
    material = {
        "material_id": "BOLT-1",
        "standard_type": "头型待识别螺栓",
        "material_name": "螺栓",
        "gpc_brick_code": "10003185",
        "procurement_attributes": {"规格": "M10×25 mm", "供货范围": "按原表成套供货"},
        "price_drivers": {
            "材质/表面处理": "碳钢常规防锈（常用默认）",
            "性能/质量等级": "4.8级（同系列常用默认）",
        },
        "confidence": "默认常用规格",
        "specification_basis": "历史原文并按常用默认补齐",
    }

    rows, _, _, report = normalize_workbench_catalog([material], [], [])

    assert rows[0]["standard_type"] == "通用螺栓"
    assert rows[0]["procurement_attributes"]["供货范围"] == "成套供货"
    assert rows[0]["price_drivers"] == {
        "材质/表面处理": "碳钢常规防锈",
        "性能/质量等级": "4.8级",
    }
    assert rows[0]["confidence"] == "默认常用规格"
    assert "常用默认" in rows[0]["specification_basis"]
    assert report["canonicalized_fastener_value_count"] == 3


def test_fastener_explicit_accessories_remain_a_distinct_selectable_scope() -> None:
    material = {
        "material_id": "BOLT-SET",
        "standard_type": "六角螺栓",
        "material_name": "外六角螺栓,螺帽,平垫,弹垫",
        "gpc_brick_code": "10003185",
        "procurement_attributes": {"规格": "M22×100 mm", "供货范围": "按原表成套供货"},
        "price_drivers": {"性能/质量等级": "4.8级", "材质/表面处理": "碳钢常规防锈"},
        "specification_basis": "历史原名：外六角螺栓,螺帽,平垫,弹垫；原规格：22*100",
    }

    rows, _, _, _ = normalize_workbench_catalog([material], [], [])

    assert rows[0]["procurement_attributes"]["供货范围"] == "成套供货（含螺母及垫圈）"
    assert rows[0]["material_name"].endswith("｜成套供货（含螺母及垫圈）")


def test_ppr_fittings_merge_into_one_selectable_type_without_pipe_or_valve() -> None:
    extensions = [
        {"code": "1000800901", "parent_code": "10008009", "kind": "internal_family", "level": 4, "working_name": "管道连接件"},
        {"code": "100080090102", "parent_code": "1000800901", "kind": "internal_type", "level": 5, "working_name": "PPR弯头"},
        {"code": "100080090103", "parent_code": "1000800901", "kind": "internal_type", "level": 5, "working_name": "PPR异径三通"},
    ]
    materials = [
        {
            "material_id": "PPR-ELBOW", "standard_type": "PPR弯头",
            "material_name": "PPR弯头｜水｜PN1.6 MPa｜Φ110｜PPR｜45°",
            "gpc_brick_code": "100080090102", "stock_uom": "件",
            "procurement_attributes": {"公称直径": "Φ110", "公称压力": "PN1.6 MPa", "材质": "PPR"},
        },
        {
            "material_id": "PPR-TEE", "standard_type": "PPR异径三通",
            "material_name": "PPR异径三通｜Φ110｜Φ50",
            "gpc_brick_code": "100080090103", "stock_uom": "件",
            "procurement_attributes": {"主管直径": "Φ110", "支管直径": "Φ50", "公称压力": "PN1.6 MPa"},
        },
    ]

    rows, _, normalized_extensions, _ = normalize_workbench_catalog(materials, [], extensions)

    assert {row["standard_type"] for row in rows} == {"PPR接头"}
    assert len({row["gpc_brick_code"] for row in rows}) == 1
    assert {row["procurement_attributes"]["接头类型"] for row in rows} == {"弯头", "异径三通"}
    elbow = next(row for row in rows if row["material_id"] == "PPR-ELBOW")
    assert elbow["procurement_attributes"]["规格"] == "Φ110×45°"
    assert "介质" not in elbow["procurement_attributes"]
    assert elbow["price_drivers"]["材质"] == "PPR"
    assert all(len(row["procurement_attributes"]) <= 4 for row in rows)
    tee = next(row for row in rows if row["material_id"] == "PPR-TEE")
    assert tee["procurement_attributes"]["规格"] == "Φ110×Φ50"
    assert len([row for row in normalized_extensions if row.get("kind") == "internal_type"]) == 1
    assert canonical_standard_type("PPR给水管") == "PPR给水管"
    assert canonical_standard_type("PPR截止阀") == "PPR截止阀"


def test_class_level_extension_receives_local_brick_and_family() -> None:
    extension = {
        "code": "9103030001",
        "parent_code": "91030300",
        "kind": "internal_type",
        "level": 3,
        "working_name": "灭火器箱",
    }
    material = {
        "material_id": "M-CABINET",
        "standard_type": "灭火器箱",
        "material_name": "灭火器箱｜2具",
        "gpc_brick_code": "9103030001",
        "procurement_attributes": {"适配数量": "2具"},
    }

    rows, _, extensions, report = normalize_workbench_catalog([material], [], [extension])

    assert [(row["kind"], row["level"]) for row in extensions] == [
        ("internal_type", 5),
        ("internal_brick", 3),
        ("internal_family", 4),
    ]
    by_code = {row["code"]: row for row in extensions}
    target = by_code[rows[0]["gpc_brick_code"]]
    family = by_code[target["parent_code"]]
    brick = by_code[family["parent_code"]]
    assert [brick["working_name"], family["working_name"], target["working_name"]] == [
        "灭火器附属设备",
        "灭火器箱体",
        "灭火器箱",
    ]
    assert report["created_internal_brick_count"] == 1
