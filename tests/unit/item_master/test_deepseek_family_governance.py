from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "material_master" / "deepseek_family_governance.py"
SPEC = importlib.util.spec_from_file_location("deepseek_family_governance", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_family_prompt_discloses_full_family_but_only_targets_chunk() -> None:
    all_rows = [
        {"item_code": "A", "item_name": "钻头", "sku_name": "钻头 14*200"},
        {"item_code": "B", "item_name": "五坑钻头", "sku_name": "五坑钻头 14*400"},
    ]
    messages = MODULE.build_messages(
        top_group="工具耗材",
        material_family="钻头",
        all_family_rows=all_rows,
        target_rows=[all_rows[0]],
    )

    assert len(messages) == 2
    assert '"family_row_count": 2' in messages[1]["content"]
    assert '"target_item_codes": ["A"]' in messages[1]["content"]
    assert "SDS-Max五坑冲击钻头" in messages[1]["content"]


def test_validate_chunk_requires_exact_item_code_coverage() -> None:
    good_row = {
        "item_code": "A",
        "proposed_item_name": "高速钢麻花钻头",
        "proposed_sku_name": "高速钢麻花钻头 Φ14*200mm",
        "proposed_required_specs": "用途：金属；直径：14mm；总长：200mm",
        "proposed_stock_uom": "支",
        "change_reason": "统一名称和尺寸格式。",
    }

    rows, _ = MODULE.validate_chunk_result({"rows": [good_row]}, ["A"])
    assert rows[0]["proposed_sku_name"] == "高速钢麻花钻头 Φ14×200mm"

    try:
        MODULE.validate_chunk_result({"rows": [good_row]}, ["A", "B"])
    except ValueError as exc:
        assert "missing=['B']" in str(exc)
    else:
        raise AssertionError("Expected missing item code validation failure")


def test_preview_changes_only_selected_fields() -> None:
    source = {
        "item_code": "A",
        "item_name": "钻头",
        "sku_name": "钻头 14*200",
        "required_specs": "直径：14mm；长度：200mm",
        "optional_specs": "",
        "stock_uom": "只",
        "purchase_uom": "只",
        "aliases": "钻头",
        "brand": "",
        "model": "",
        "material_family": "钻头",
        "estimated_rate": "99.00",
        "governance_note": "",
    }
    proposed = {
        "item_code": "A",
        "proposed_item_name": "高速钢麻花钻头",
        "proposed_sku_name": "高速钢麻花钻头 Φ14×200mm",
        "proposed_required_specs": "用途：金属；直径：14mm；总长：200mm；材质：高速钢",
        "proposed_optional_specs": "",
        "proposed_stock_uom": "支",
        "proposed_aliases": "钻头",
        "proposed_brand": "",
        "proposed_model": "",
        "duplicate_with_item_code": "",
        "change_reason": "统一三级名称。",
    }

    preview = MODULE.apply_preview([source], [proposed])[0]

    assert preview["item_name"] == "高速钢麻花钻头"
    assert preview["stock_uom"] == "支"
    assert preview["purchase_uom"] == "支"
    assert preview["estimated_rate"] == "99.00"
    assert preview["material_family"] == "钻头"


def test_drill_family_formatting_is_deterministic() -> None:
    row = {
        "item_code": "A",
        "proposed_item_name": "SDS-Max五坑冲击钻头",
        "proposed_sku_name": "SDS-Max五坑冲击钻头 14mm*400mm",
        "proposed_required_specs": "柄型：SDS-Max五坑；直径：14mm；长度：400mm",
        "proposed_optional_specs": "",
        "proposed_stock_uom": "只",
        "proposed_aliases": "五坑钻头",
        "proposed_brand": "",
        "proposed_model": "",
        "duplicate_with_item_code": "",
        "change_reason": "统一名称。",
    }

    normalized = MODULE.normalize_family_output(row, "钻头")

    assert normalized["proposed_sku_name"] == "SDS-Max五坑冲击钻头 Φ14×400mm"
    assert normalized["proposed_required_specs"].startswith("接口：SDS-Max五坑")
    assert "总长：400mm" in normalized["proposed_required_specs"]
    assert normalized["proposed_stock_uom"] == "支"


def test_drill_family_preserves_evidence_and_does_not_invent_material() -> None:
    row = {
        "item_code": "A",
        "proposed_item_name": "不锈钢用高速钢麻花钻头",
        "proposed_sku_name": "不锈钢用高速钢麻花钻头 5×85mm",
        "proposed_required_specs": "用途：不锈钢；直径：5mm；总长：85mm",
        "proposed_optional_specs": "",
        "proposed_stock_uom": "只",
        "proposed_aliases": "不锈钢钻头",
        "proposed_brand": "",
        "proposed_model": "",
        "duplicate_with_item_code": "",
        "change_reason": "模型推断。",
    }
    source = {
        "item_code": "A",
        "item_name": "钻头",
        "sku_name": "不锈钢钻头 5*85 短型",
        "required_specs": "用途：不锈钢；直径：5mm；长度：85mm",
    }

    normalized = MODULE.normalize_family_output(row, "钻头", source)

    assert normalized["proposed_item_name"] == "不锈钢用钻头"
    assert normalized["proposed_sku_name"] == "不锈钢用钻头 Φ5×85mm"
    assert "高速钢" not in normalized["proposed_required_specs"]
    assert normalized["proposed_optional_specs"] == "类型：短型"


def test_drill_family_does_not_invent_concrete_use() -> None:
    row = {
        "item_code": "A",
        "proposed_item_name": "混凝土冲击钻头",
        "proposed_sku_name": "混凝土冲击钻头 6×100mm",
        "proposed_required_specs": "直径：6mm；总长：100mm",
        "proposed_optional_specs": "",
        "proposed_stock_uom": "支",
        "proposed_aliases": "冲击钻头",
        "proposed_brand": "",
        "proposed_model": "",
        "duplicate_with_item_code": "",
        "change_reason": "模型推断。",
    }
    source = {
        "item_code": "A",
        "item_name": "冲击钻头",
        "sku_name": "冲击钻头 6*100",
        "required_specs": "直径：6mm；长度：100mm",
    }

    normalized = MODULE.normalize_family_output(row, "钻头", source)

    assert normalized["proposed_item_name"] == "冲击钻头"
    assert normalized["proposed_sku_name"] == "冲击钻头 Φ6×100mm"
    assert "混凝土" not in normalized["change_reason"] or "不推断混凝土" in normalized["change_reason"]


def test_drill_family_does_not_invent_impact_use_for_square_shank() -> None:
    row = {
        "item_code": "A",
        "proposed_item_name": "方柄冲击钻头",
        "proposed_sku_name": "方柄冲击钻头 14×280mm",
        "proposed_required_specs": "柄型：方柄；直径：14mm；总长：280mm",
        "proposed_optional_specs": "",
        "proposed_stock_uom": "支",
        "proposed_aliases": "方柄钻头",
        "proposed_brand": "",
        "proposed_model": "",
        "duplicate_with_item_code": "",
        "change_reason": "模型推断。",
    }
    source = {
        "item_code": "A",
        "item_name": "方柄钻头",
        "sku_name": "方柄钻头 14*280",
        "required_specs": "柄型：方柄；直径：14mm；长度：280mm",
    }

    normalized = MODULE.normalize_family_output(row, "钻头", source)

    assert normalized["proposed_item_name"] == "方柄钻头"
    assert normalized["proposed_sku_name"] == "方柄钻头 Φ14×280mm"


def test_review_prompt_contains_family_rows() -> None:
    rows = [
        {
            "item_code": "TOOL-1",
            "original_item_name": "钻头",
            "original_sku_name": "钻头14",
            "original_required_specs": "规格：14",
            "original_optional_specs": "",
            "original_aliases": "钻头14",
            "original_brand": "博世",
            "original_model": "",
            "proposed_item_name": "高速钢麻花钻头",
            "proposed_sku_name": "高速钢麻花钻头 Φ14×200mm",
            "proposed_required_specs": "材质：高速钢；直径：14mm；总长：200mm",
            "proposed_optional_specs": "",
            "proposed_stock_uom": "支",
            "proposed_aliases": "钻头14",
            "proposed_brand": "博世",
            "proposed_model": "",
            "duplicate_with_item_code": "",
        }
    ]

    messages = MODULE.build_review_messages(
        top_group="工具耗材",
        material_family="钻头",
        comparison_rows=rows,
    )

    assert "独立的物料主数据质量审查员" in messages[0]["content"]
    assert "TOOL-1" in messages[1]["content"]


def test_review_rejects_unknown_item_code() -> None:
    result = {
        "issues": [
            {
                "item_code": "UNKNOWN",
                "severity": "high",
                "issue": "错误",
            }
        ]
    }

    try:
        MODULE.normalize_review_result(result, {"TOOL-1"})
    except ValueError as exc:
        assert "unknown item_code" in str(exc)
    else:
        raise AssertionError("Expected unknown review item code validation failure")


def test_family_guide_rejects_item_names_with_sku_dimensions() -> None:
    result = {
        "goal": "整理弯头",
        "preferred_item_names": ["弯头 DN25"],
        "normalization_notes": [],
        "prohibited_inferences": [],
        "required_specs_by_item_name": [],
        "uom_policy": "个",
    }

    try:
        MODULE.normalize_family_guide(result, "弯头")
    except ValueError as exc:
        assert "contain SKU dimensions" in str(exc)
    else:
        raise AssertionError("Expected family guide dimension validation failure")


def test_elbow_preserves_inner_thread_size_from_alias() -> None:
    row = {
        "item_code": "A",
        "proposed_item_name": "内丝弯头",
        "proposed_sku_name": "PPR内丝弯头 25mm",
        "proposed_required_specs": "材质：PPR；规格/口径：25mm；接口：内丝",
        "proposed_optional_specs": "",
        "proposed_stock_uom": "个",
        "proposed_aliases": "PPR25×4内牙弯头",
        "proposed_brand": "",
        "proposed_model": "",
        "duplicate_with_item_code": "",
        "change_reason": "归一名称。",
    }
    source = {
        "aliases": "PPR内牙弯头；PPR25*4内牙弯头",
        "required_specs": "材质：PPR；规格/口径：25mm；接口：内丝",
    }

    normalized = MODULE.normalize_family_output(row, "弯头", source)

    assert normalized["proposed_sku_name"] == "PPR内丝弯头 25mm×4分"
    assert "内丝端口径：4分" in normalized["proposed_required_specs"]


def test_hose_assembly_preserves_original_spec_notation() -> None:
    row = {
        "item_code": "A",
        "proposed_item_name": "胶管总成",
        "proposed_sku_name": "胶管总成 13mm 50米",
        "proposed_required_specs": "规格：13mm；长度：50米；接头形式：两端接头",
        "proposed_optional_specs": "",
        "proposed_stock_uom": "米",
        "proposed_aliases": "高压管带两端接头Φ13-50m",
        "proposed_brand": "",
        "proposed_model": "",
        "duplicate_with_item_code": "",
        "change_reason": "模型换算。",
    }
    source = {
        "required_specs": "规格：Φ13；长度：50m；接头形式：两端接头",
    }

    normalized = MODULE.normalize_family_output(row, "胶管总成", source)

    assert normalized["proposed_sku_name"] == "胶管总成 Φ13 50米"
    assert normalized["proposed_required_specs"].startswith("规格：Φ13；")
    assert normalized["proposed_stock_uom"] == "根"


def test_deepseek_retry_recovers_from_invalid_first_response() -> None:
    calls = 0
    original = MODULE.call_deepseek_json

    def fake_call(messages, *, settings):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("invalid json")
        return {"ok": True}

    MODULE.call_deepseek_json = fake_call
    try:
        result = MODULE.call_deepseek_json_with_retry([], settings=object())
    finally:
        MODULE.call_deepseek_json = original

    assert result == {"ok": True}
    assert calls == 2
