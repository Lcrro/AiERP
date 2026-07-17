from __future__ import annotations

from nexterp_agent.agent_runtime.tool_access import make_tool_access_policy


def test_procurement_can_prepare_and_submit_stock_transfer() -> None:
    policy = make_tool_access_policy("procurement")

    assert policy.decide("erpnext.stock.get_transfer_context").allowed
    assert policy.decide("erpnext.stock.create_transfer_draft").allowed
    assert policy.decide("erpnext.stock.verify_transfer_impact").allowed
    assert policy.decide("erpnext.stock.submit_document").allowed


def test_project_profile_can_issue_and_submit_but_not_create_transfer() -> None:
    policy = make_tool_access_policy("project")

    assert policy.decide("erpnext.projects.get_material_issue_context").allowed
    assert policy.decide("erpnext.projects.create_material_issue_draft").allowed
    assert policy.decide("erpnext.projects.verify_material_issue_cost_impact").allowed
    assert policy.decide("erpnext.stock.submit_document").allowed
    assert not policy.decide("erpnext.stock.create_transfer_draft").allowed
