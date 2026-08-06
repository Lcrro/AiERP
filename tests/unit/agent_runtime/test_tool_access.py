from __future__ import annotations

from nexterp_agent.agent_runtime.tool_access import make_tool_access_policy


def test_procurement_can_prepare_and_submit_stock_transfer() -> None:
    policy = make_tool_access_policy("procurement")

    assert policy.decide("erpnext.stock.get_transfer_context").allowed
    assert policy.decide("erpnext.stock.create_transfer_draft").allowed
    assert policy.decide("erpnext.stock.verify_transfer_impact").allowed
    assert policy.decide("erpnext.stock.submit_document").allowed


def test_item_master_creation_is_limited_to_governance_roles() -> None:
    assert make_tool_access_policy("procurement").decide("erpnext.stock.create_item").allowed
    assert make_tool_access_policy("system_admin").decide("erpnext.stock.create_item").allowed
    assert not make_tool_access_policy("stock").decide("erpnext.stock.create_item").allowed
    assert not make_tool_access_policy("project").decide("erpnext.stock.create_item").allowed


def test_project_profile_can_issue_and_submit_but_not_create_transfer() -> None:
    policy = make_tool_access_policy("project")

    assert policy.decide("erpnext.projects.get_material_issue_context").allowed
    assert policy.decide("erpnext.projects.create_material_issue_draft").allowed
    assert policy.decide("erpnext.projects.verify_material_issue_cost_impact").allowed
    assert policy.decide("erpnext.stock.submit_document").allowed
    assert not policy.decide("erpnext.stock.create_transfer_draft").allowed


def test_master_data_profile_names_map_to_business_tool_policies() -> None:
    manager = make_tool_access_policy("manager_agent")
    equipment = make_tool_access_policy("material_equipment_agent")
    project_manager = make_tool_access_policy("project_agent")
    material_clerk = make_tool_access_policy("material_clerk_agent")
    operations = make_tool_access_policy("operations_agent")
    technical = make_tool_access_policy("technical_agent")
    admin = make_tool_access_policy("admin_agent")
    finance = make_tool_access_policy("finance_agent")

    assert manager.decide("erpnext.accounting.accounts_payable").allowed
    assert equipment.decide("erpnext.buying.create_purchase_order_draft").allowed
    assert equipment.decide("erpnext.stock.create_transfer_draft").allowed
    assert project_manager.decide("erpnext.projects.create_material_issue_draft").allowed
    assert material_clerk.decide("erpnext.buying.create_material_request_draft").allowed
    assert operations.decide("erpnext.buying.run_purchase_analysis").allowed
    assert not operations.decide("erpnext.buying.create_purchase_order_draft").allowed
    assert technical.decide("erpnext.stock.get_balance").allowed
    assert not technical.decide("erpnext.projects.create_material_issue_draft").allowed
    assert admin.decide("erpnext.users.preview_effective_permissions").allowed
    assert finance.decide("erpnext.accounting.accounts_payable").allowed
    assert not finance.decide("erpnext.buying.create_purchase_order_draft").allowed
