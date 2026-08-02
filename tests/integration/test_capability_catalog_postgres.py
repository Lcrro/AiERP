from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from nexterp_agent.capability_service.catalog import CapabilityCatalogRepository


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
