from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from nexterp_agent.erpnext.schemas import ToolResult
from nexterp_agent.item_master import MaterialRules, MaterialSearch, generate_next_item_code, prepare_item_from_intent
from nexterp_agent.item_master.postgres_catalog import (
    CatalogPaths,
    build_filter_sql,
    dict_from_row,
    normalize_search_text,
    parent_group_path,
    split_group_path,
)


def test_rules_load_and_cold_sheet_needs_standard() -> None:
    rules = MaterialRules.load()

    result = prepare_item_from_intent(
        {
            "raw_text": "新增一个 1.5 冷板，SPCC，宽 1250，卷料，单位公斤",
            "raw_name": "1.5 冷板",
            "item_name": "冷轧钢卷",
            "stock_uom": "Kg",
            "specs": {
                "material": "SPCC",
                "thickness": "1.5mm",
                "width": "1250mm",
                "form": "卷料",
            },
        },
        rules=rules,
    )

    assert result["status"] == "needs_clarification"
    assert result["matched_group"] == "raw_metal_sheet"
    assert result["missing_specs"] == ["standard"]
    assert "执行标准" in result["questions"][0]


def test_complete_cold_sheet_intent_builds_item_doc() -> None:
    rules = MaterialRules.load()

    result = prepare_item_from_intent(
        {
            "raw_name": "1.5 冷板",
            "item_name": "冷轧钢卷",
            "stock_uom": "Kg",
            "specs": {
                "material": "SPCC",
                "thickness": "1.5mm",
                "width": "1250mm",
                "form": "卷料",
                "standard": "GB/T 708",
            },
        },
        rules=rules,
        item_code="RM-MET-SHT-000001",
    )

    assert result["status"] == "ready"
    assert result["item_doc"]["item_code"] == "RM-MET-SHT-000001"
    assert result["item_doc"]["item_group"] == "原材料"
    assert result["item_doc"]["has_batch_no"] == 1
    assert result["item_doc"]["material"] == "SPCC"
    assert "GB/T 708" in result["item_doc"]["specification"]


def test_generate_next_item_code_increments_existing_prefix() -> None:
    assert generate_next_item_code("RM-MET-SHT", ["RM-MET-SHT-000001", "RM-MET-SHT-000009"]) == "RM-MET-SHT-000010"


class FixtureSearchClient:
    def __init__(self, *, failing_fields: set[str] | None = None) -> None:
        fixture_path = Path(__file__).resolve().parents[2] / "fixtures" / "material_search_items.json"
        self.rows = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.failing_fields = failing_fields or set()

    def get_document(self, doctype, name) -> ToolResult:
        assert doctype == "Item"
        for row in self.rows:
            if name in {row["name"], row["item_code"]}:
                return ToolResult(ok=True, data=row)
        return ToolResult(ok=False, error_type="not_found")

    def search_documents(self, doctype, **kwargs) -> ToolResult:
        assert doctype == "Item"
        filters = kwargs.get("filters") or []
        if filters and filters[0][0] in self.failing_fields:
            return ToolResult(ok=False, error="Unknown column", error_type="validation_error")
        return ToolResult(ok=True, data=self._search(filters))

    def _search(self, filters):
        rows = self.rows
        for field, operator, value in filters:
            if operator == "like":
                needle = str(value).replace("%", "").lower()
                rows = [row for row in rows if needle in str(row.get(field) or "").lower()]
            elif operator == "=" and field == "disabled":
                rows = [row for row in rows if row.get("disabled") == value]
        return rows


def test_search_exact_item_code_returns_ready_candidate() -> None:
    search = MaterialSearch(FixtureSearchClient())

    result = search.search_items("RM-MET-SHT-000123")

    assert result["status"] == "ready"
    assert result["candidates"][0]["item_code"] == "RM-MET-SHT-000123"
    assert result["candidates"][0]["score"] >= 90


def test_search_alias_and_specs_returns_candidate_reason() -> None:
    search = MaterialSearch(FixtureSearchClient())

    result = search.search_items("冷板", specs={"material": "SPCC", "thickness": "1.5mm"})

    assert result["candidates"]
    assert result["candidates"][0]["item_code"] == "RM-MET-SHT-000123"
    assert "别名/土名精确命中" in result["candidates"][0]["match_reason"]
    assert "规格字段精确命中 material=SPCC" in result["candidates"][0]["match_reason"]


def test_search_specs_can_disambiguate_similar_items() -> None:
    search = MaterialSearch(FixtureSearchClient())

    result = search.search_items("高压接头", specs={"model": "M36*2"})

    assert result["candidates"][0]["item_code"] == "PIPE-FIT-000002"
    assert "规格字段精确命中 model=M36*2" in result["candidates"][0]["match_reason"]


def test_search_returns_multiple_candidates_when_query_is_ambiguous() -> None:
    search = MaterialSearch(FixtureSearchClient())

    result = search.search_items("高压接头")

    assert result["status"] == "needs_confirmation"
    assert [candidate["item_code"] for candidate in result["candidates"][:2]] == ["PIPE-FIT-000001", "PIPE-FIT-000002"]
    assert result["questions"]


def test_search_low_confidence_generic_query_asks_for_clarification() -> None:
    search = MaterialSearch(FixtureSearchClient())

    result = search.search_items("接头")

    assert result["status"] == "needs_clarification"
    assert "过于宽泛" in result["questions"][0]


def test_search_skips_missing_custom_field_and_records_warning() -> None:
    search = MaterialSearch(FixtureSearchClient(failing_fields={"alias_names", "raw_name"}))

    result = search.search_items("冷板", specs={"material": "SPCC"})

    assert result["candidates"][0]["item_code"] == "RM-MET-SHT-000123"
    assert result["warnings"]
    assert any("alias_names" in warning for warning in result["warnings"])


def test_search_disabled_exact_code_is_not_ready_by_default() -> None:
    search = MaterialSearch(FixtureSearchClient())

    result = search.search_items("DIS-ITEM-000001")

    assert result["status"] == "needs_confirmation"
    assert result["candidates"][0]["enabled"] is False
    assert "已禁用" in result["questions"][0]


def test_search_generic_query_with_specs_recalls_and_ranks_candidate() -> None:
    search = MaterialSearch(FixtureSearchClient())

    result = search.search_items("接头", specs={"model": "M36*2"})

    assert result["status"] in {"ready", "needs_confirmation"}
    assert result["candidates"][0]["item_code"] == "PIPE-FIT-000002"
    assert "规格字段精确命中 model=M36*2" in result["candidates"][0]["match_reason"]
    assert result["decision_reason"]
    assert result["debug"]["score_gap"] >= 0
    assert not any("过于宽泛" in question for question in result["questions"])


def test_search_empty_query_with_specs_recalls_without_error() -> None:
    search = MaterialSearch(FixtureSearchClient())

    result = search.search_items("", specs={"model": "M36*2"})

    assert result["status"] in {"needs_clarification", "needs_confirmation", "ready"}
    assert result["candidates"]
    assert result["candidates"][0]["item_code"] == "PIPE-FIT-000002"


def test_search_real_ppr_purchase_phrase_hits_standard_candidate() -> None:
    search = MaterialSearch(FixtureSearchClient())

    result = search.search_items("公元25PPR弯头", specs={"brand": "公元", "model": "25", "material": "PPR"})

    assert result["candidates"][0]["item_code"] == "PPR-FIT-000001"
    assert "别名/土名精确命中" in result["candidates"][0]["match_reason"]


def test_search_real_fire_hose_and_rigging_phrases_hit_candidates() -> None:
    search = MaterialSearch(FixtureSearchClient())

    fire_hose = search.search_items("65消防水管", specs={"model": "65"})
    sling = search.search_items("5T*6m国标彩色吊带", specs={"model": "5T*6m", "standard": "国标"})

    assert fire_hose["candidates"][0]["item_code"] == "FIRE-HOSE-000065"
    assert sling["candidates"][0]["item_code"] == "RIG-SLING-000506"


def test_search_real_cable_welding_and_shackle_phrases_hit_candidates() -> None:
    search = MaterialSearch(FixtureSearchClient())

    cable = search.search_items("3*6+1起帆电缆", specs={"brand": "起帆", "model": "3*6+1"})
    wire = search.search_items("1.2药芯焊丝", specs={"model": "1.2mm"})
    shackle = search.search_items("8T卸扣", specs={"model": "8T"})

    assert cable["candidates"][0]["item_code"] == "ELE-CAB-000346"
    assert wire["candidates"][0]["item_code"] == "WELD-WIRE-000012"
    assert shackle["candidates"][0]["item_code"] == "RIG-SHACKLE-000008"


def test_search_normalizes_thread_model_variants_for_spec_recall() -> None:
    search = MaterialSearch(FixtureSearchClient())

    result = search.search_items("接头", specs={"model": "36×2"})

    assert result["candidates"][0]["item_code"] == "PIPE-FIT-000002"
    assert "规格字段精确命中 model=36×2" in result["candidates"][0]["match_reason"]


def test_search_normalizes_mm_suffix_for_welding_wire() -> None:
    search = MaterialSearch(FixtureSearchClient())

    result = search.search_items("药芯焊丝", specs={"model": "1.2"})

    assert result["candidates"][0]["item_code"] == "WELD-WIRE-000012"
    assert "规格字段精确命中 model=1.2" in result["candidates"][0]["match_reason"]


def test_postgres_catalog_paths_from_review_directory() -> None:
    paths = CatalogPaths.from_dir("data/material_purchase_2024")

    assert paths.catalog.name == "standard_item_catalog_from_review.csv"
    assert paths.aliases.name == "item_aliases_from_review.csv"
    assert paths.manual_review.name == "manual_review_queue_from_review.csv"
    assert paths.services.name == "non_stock_services_from_review.csv"
    assert paths.group_mapping.name == "material_group_canonical_mapping.csv"


def test_postgres_catalog_splits_group_path_levels() -> None:
    assert split_group_path("管件/镀锌管件") == ("管件", "镀锌管件", None)
    assert split_group_path("安全消防/消防接头/铝合金") == ("安全消防", "消防接头", "铝合金")
    assert parent_group_path("安全消防/消防接头/铝合金") == "安全消防/消防接头"
    assert parent_group_path("管件") is None


def test_postgres_catalog_builds_search_filter_sql() -> None:
    where_sql, params = build_filter_sql([["alias_names", "like", "%冷板%"], ["disabled", "=", 0]])

    assert "alias_names ilike" in where_sql
    assert "normalized_search_text ilike" in where_sql
    assert "disabled = %s" in where_sql
    assert params == ["%冷板%", "%冷板%", False]


def test_postgres_catalog_normalizes_search_text() -> None:
    assert normalize_search_text(" M36 × 2 冷 板 ") == "m36*2冷板"


def test_postgres_catalog_result_rows_are_json_safe() -> None:
    row = {
        "item_code": "REVIEW-MAT-1",
        "group_mapping_confidence": Decimal("0.98"),
    }

    assert dict_from_row(row)["group_mapping_confidence"] == 0.98
