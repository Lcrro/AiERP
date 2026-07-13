from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "agent_workbench.py"
SPEC = importlib.util.spec_from_file_location("agent_workbench", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_employee_catalog_does_not_expose_credentials() -> None:
    employees = MODULE.employee_catalog()

    assert len(employees) == 6
    assert all("api_key" not in employee and "api_secret" not in employee for employee in employees)
    assert {employee["employee_name"] for employee in employees} >= {"张振光", "潘丰", "毛晓泉"}


def test_result_document_links_build_erpnext_route() -> None:
    result = {
        "tool_result": {"data": {"doctype": "Material Request", "name": "MAT-MR-2026-00001"}},
        "tool_results": [],
    }

    assert MODULE.result_document_links(result, "http://localhost:8002") == [
        {
            "doctype": "Material Request",
            "name": "MAT-MR-2026-00001",
            "url": "http://localhost:8002/app/material-request/MAT-MR-2026-00001",
        }
    ]


def test_project_catalog_contains_project_specific_and_organization_employees() -> None:
    projects = {row["project_code"]: row for row in MODULE.project_catalog()}
    names = {row["employee_name"] for row in projects["PRJ-HL-13"]["employees"]}

    assert projects["PRJ-HL-13"]["project_short_name"] == "合流1.3标"
    assert {"张振光", "林乔航", "毛晓泉", "徐溥祺"} <= names
    assert "梁志华" not in names
