from __future__ import annotations

from nexterp_agent.capability_service.catalog import CapabilityCatalogRepository


def test_material_creation_guide_defines_query_attributes_contract() -> None:
    guide = CapabilityCatalogRepository._read_capability_guide("create_material")
    prohibition = CapabilityCatalogRepository._read_capability_prohibition("create_material")

    assert "query" in guide
    assert "attributes" in guide
    assert "本操作不使用 items" in guide
    assert "规格:M8×45" in guide
    assert "不得使用 items" in prohibition
