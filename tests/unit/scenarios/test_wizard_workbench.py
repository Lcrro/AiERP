from __future__ import annotations

from datetime import date

from nexterp_agent.erpnext.risk_policy import infer_risk_level
from nexterp_agent.erpnext.tool_registry import ERPNext_TOOL_SCHEMAS
from nexterp_agent.scenarios.wizard_workbench import build_wizard_tools, grouped_wizard_catalog


def test_curated_wizard_tools_are_registered() -> None:
    registered = {schema["name"] for schema in ERPNext_TOOL_SCHEMAS}

    missing = [tool.tool for tool in build_wizard_tools(date(2026, 6, 12)) if tool.tool not in registered]

    assert missing == []


def test_wizard_catalog_has_setup_and_write_guard_metadata() -> None:
    catalog = grouped_wizard_catalog(date(2026, 6, 12))
    tools = {tool["id"]: tool for group in catalog["groups"] for tool in group["tools"]}

    assert catalog["default_profile"] == "civil"
    assert "scripts/seed_civil_company_scenario.py" in catalog["setup"]["apply_command"]
    assert tools["mr-create-gloves"]["writes"] is True
    assert tools["mr-create-gloves"]["risk_level"] == infer_risk_level("erpnext.buying.create_material_request_draft")
    assert tools["auth-current-user"]["writes"] is False
    assert tools["auth-current-user"]["risk_level"] == "L0"


def test_wizard_dates_are_stable_when_today_is_provided() -> None:
    tools = {tool.id: tool for tool in build_wizard_tools(date(2026, 6, 12))}

    assert tools["mr-create-gloves"].arguments["schedule_date"] == "2026-06-13"
    assert tools["finance-ap"].arguments["from_date"] == "2026-06-01"
    assert tools["finance-ap"].arguments["to_date"] == "2026-06-12"
