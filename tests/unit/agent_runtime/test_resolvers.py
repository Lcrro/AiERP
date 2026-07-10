from __future__ import annotations

from datetime import date

from nexterp_agent.agent_runtime.resolvers import EntityResolverRegistry


def test_project_short_name_resolves_to_stable_project_code() -> None:
    result = EntityResolverRegistry().resolve_project("合流1.3标")

    assert result.status == "resolved"
    assert result.value == "PRJ-HL-13"


def test_project_full_name_and_warehouse_short_name_resolve() -> None:
    registry = EntityResolverRegistry()

    project = registry.resolve_project("合流污水一期复线工程（其他部分）FXQ1.3标4-15井")
    warehouse = registry.resolve_warehouse("合流1.3标仓库")

    assert project.value == "PRJ-HL-13"
    assert warehouse.value == "合流1.3标仓库 - SD"


def test_relative_date_is_deterministic() -> None:
    result = EntityResolverRegistry().resolve_date("明天", current_date=date(2026, 7, 10))

    assert result.status == "resolved"
    assert result.value == "2026-07-11"
