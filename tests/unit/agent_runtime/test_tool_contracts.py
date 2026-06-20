from __future__ import annotations

import pytest

from nexterp_agent.agent_runtime.tool_contracts import (
    build_tool_contracts,
    get_tool_contract,
    load_tool_contract_overrides,
)
from nexterp_agent.agent_runtime.tool_access import ToolExposure
from nexterp_agent.erpnext.tool_registry import ERPNext_TOOL_SCHEMAS


def test_tool_contracts_cover_all_registered_schemas() -> None:
    contracts = build_tool_contracts()

    assert len(contracts) == len(ERPNext_TOOL_SCHEMAS)
    assert {contract.name for contract in contracts} == {schema["name"] for schema in ERPNext_TOOL_SCHEMAS}


def test_stock_get_balance_contract_has_business_constraints() -> None:
    contract = get_tool_contract("erpnext.stock.get_balance")

    assert contract.expose is ToolExposure.AGENT_VISIBLE
    assert contract.confirm == "none"
    assert "采购" in contract.allowed_roles
    assert "Bin" in contract.backend_mapping.doctypes

    params = {param.name: param for param in contract.parameters}
    assert params["item_code"].required == "conditional"
    assert params["item_code"].resolver == "item"
    assert "resolve_entity" in params["item_code"].repair
    assert params["warehouse"].resolver == "warehouse"


def test_generic_create_document_is_developer_only() -> None:
    contract = get_tool_contract("erpnext.create_document")

    assert contract.expose is ToolExposure.DEVELOPER_ONLY
    assert contract.allowed_roles == ("developer",)
    assert "任意 DocType" in contract.backend_mapping.doctypes


def test_runtime_internal_search_documents_contract() -> None:
    contract = get_tool_contract("erpnext.search_documents")

    assert contract.expose is ToolExposure.RUNTIME_INTERNAL
    assert contract.allowed_roles == ("Runtime",)
    assert contract.confirm == "none"
    assert "validate_before_execute" in contract.repair


def test_role_inference_covers_admin_and_asset_profiles() -> None:
    users_contract = get_tool_contract("erpnext.users.create_user_draft")
    asset_contract = get_tool_contract("erpnext.assets.create_asset_draft")

    assert "系统管理员" in users_contract.allowed_roles
    assert "资产管理员" in asset_contract.allowed_roles


def test_unknown_tool_override_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown ToolCall"):
        build_tool_contracts({"tools": {"erpnext.not_a_real_tool": {}}})


def test_override_directory_merges_module_files_and_rejects_duplicates(tmp_path) -> None:
    (tmp_path / "generic.yaml").write_text(
        "version: 1\nmodule: generic\ntools:\n  erpnext.search_documents:\n    expose: runtime_internal\n",
        encoding="utf-8",
    )
    (tmp_path / "stock.yaml").write_text(
        "version: 1\nmodule: stock\ntools:\n  erpnext.stock.get_balance:\n    expose: agent_visible\n",
        encoding="utf-8",
    )

    payload = load_tool_contract_overrides(tmp_path)

    assert sorted(payload["tools"]) == ["erpnext.search_documents", "erpnext.stock.get_balance"]

    (tmp_path / "duplicate.yaml").write_text(
        "version: 1\nmodule: duplicate\ntools:\n  erpnext.stock.get_balance:\n    expose: agent_visible\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate ToolCall overrides"):
        load_tool_contract_overrides(tmp_path)
