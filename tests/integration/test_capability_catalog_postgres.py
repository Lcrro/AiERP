from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from nexterp_agent.capability_service.catalog import CapabilityCatalogRepository
from nexterp_agent.capability_service.procurement_catalog import PROCUREMENT_CHAIN


load_dotenv()


@pytest.mark.integration
def test_capability_catalog_migration_is_repeatable() -> None:
    dsn = os.getenv("MATERIAL_CATALOG_DATABASE_URL")
    if not dsn:
        pytest.skip("MATERIAL_CATALOG_DATABASE_URL is not configured")
    repository = CapabilityCatalogRepository(dsn)

    first = repository.migrate()
    second = repository.migrate()
    bundle = repository.operation_bundle("op.material_request.create")

    assert first == second
    assert len(bundle["slots"]) == 11
    assert len(bundle["rules"]) == 4
    assert bundle["operation"]["compiler_key"] == "material_request.create.v1"
    assert bundle["operation"]["requires_confirmation"] is True


@pytest.mark.integration
def test_capability_catalog_search_accepts_an_empty_module_filter() -> None:
    dsn = os.getenv("MATERIAL_CATALOG_DATABASE_URL")
    if not dsn:
        pytest.skip("MATERIAL_CATALOG_DATABASE_URL is not configured")
    repository = CapabilityCatalogRepository(dsn)
    repository.migrate()

    matches = repository.search_nodes("帮我创建材料申请，合流项目后天需要水泥", module=None)

    assert matches
    assert matches[0]["node_id"] == "op.material_request.create"


@pytest.mark.integration
def test_procurement_chain_is_seeded_and_searchable() -> None:
    dsn = os.getenv("MATERIAL_CATALOG_DATABASE_URL")
    if not dsn:
        pytest.skip("MATERIAL_CATALOG_DATABASE_URL is not configured")
    repository = CapabilityCatalogRepository(dsn)
    repository.migrate()

    queries = {
        "询价": "op.request_for_quotation.from_material_request",
        "供应商报价": "op.supplier_quotation.from_request_for_quotation",
        "采购订单": "op.purchase_order.from_supplier_quotation",
        "采购收货": "op.purchase_receipt.from_purchase_order",
        "退货": "op.purchase_return.from_purchase_receipt",
    }
    for seed in PROCUREMENT_CHAIN:
        bundle = repository.operation_bundle(seed.operation_id)
        assert bundle["operation"]["tool_name"] == seed.tool_name
        assert bundle["operation"]["compiler_key"] == seed.compiler_key
        assert len(bundle["slots"]) == len(seed.slots)
        assert len(bundle["rules"]) == len(seed.rules)

    for query, operation_id in queries.items():
        matches = repository.search_nodes(query, module="buying", limit=5)
        assert operation_id in {row["node_id"] for row in matches}


@pytest.mark.integration
def test_material_classification_capability_is_seeded_as_analyze_only() -> None:
    dsn = os.getenv("MATERIAL_CATALOG_DATABASE_URL")
    if not dsn:
        pytest.skip("MATERIAL_CATALOG_DATABASE_URL is not configured")
    repository = CapabilityCatalogRepository(dsn)
    repository.migrate()

    matches = repository.search_nodes("新物料怎么分类", module="stock", limit=5)
    capability_guide = repository.load_guides(["cap.material_classification"])[0]
    guide = repository.load_guides(["op.material.classify"])[0]

    assert "cap.material_classification" in {row["node_id"] for row in matches}
    assert "op.material.classify" in {
        row["node_id"] for row in capability_guide["relations"]
    }
    assert guide["operation_mode"] == "analyze"
    assert guide["is_write"] is False
    assert "不得猜测缺失属性" in guide["prohibitions"]
