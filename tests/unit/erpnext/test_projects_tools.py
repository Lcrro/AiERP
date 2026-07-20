from __future__ import annotations

from nexterp_agent.erpnext import ERPNextAdapter
from nexterp_agent.erpnext.schemas import ToolCall, ToolResult


class ProjectsFakeClient:
    def __init__(self) -> None:
        self.calls = []

    def get_document(self, doctype, name) -> ToolResult:
        self.calls.append(("get_document", doctype, name))
        if doctype == "Project" and name == "PROJ-001":
            return ToolResult(
                ok=True,
                data={
                    "doctype": "Project",
                    "name": name,
                    "project_name": "Bridge Project",
                    "company": "Acme",
                    "cost_center": "Bridge - A",
                    "status": "Open",
                    "expected_start_date": "2026-06-01",
                    "expected_end_date": "2026-08-31",
                    "percent_complete": 35,
                    "total_costing_amount": 1200,
                    "total_billing_amount": 0,
                },
            )
        if doctype == "Stock Entry" and name == "STE-001":
            return ToolResult(
                ok=True,
                data={
                    "doctype": "Stock Entry",
                    "name": "STE-001",
                    "docstatus": 1,
                    "purpose": "Material Issue",
                    "stock_entry_type": "Material Issue",
                    "company": "Acme",
                    "posting_date": "2026-06-12",
                    "items": [
                        {
                            "name": "SED-001",
                            "item_code": "ITEM-001",
                            "item_name": "Test Item",
                            "qty": 3,
                            "uom": "Nos",
                            "s_warehouse": "Stores - A",
                            "project": "PROJ-001",
                            "cost_center": "Bridge - A",
                            "expense_account": "Materials Consumed - A",
                            "basic_rate": 8,
                            "basic_amount": 24,
                        }
                    ],
                },
            )
        if doctype == "Task" and name == "TASK-001":
            return ToolResult(ok=True, data={
                "doctype": "Task", "name": name, "project": "PROJ-001", "subject": "Foundation",
                "status": "Working", "progress": 40, "exp_start_date": "2026-06-01", "exp_end_date": "2026-06-20",
            })
        return ToolResult(ok=False, error_type="not_found", error="not found")

    def search_documents(self, doctype, **kwargs) -> ToolResult:
        self.calls.append(("search_documents", doctype, kwargs))
        if doctype == "Task":
            return ToolResult(ok=True, data=[{
                "name": "TASK-001", "subject": "Foundation", "status": "Working", "priority": "High",
                "progress": 40, "exp_end_date": "2026-06-20",
            }])
        if doctype == "Stock Entry":
            return ToolResult(ok=True, data=[{"name": "STE-001", "purpose": "Material Issue", "docstatus": 1}])
        if doctype == "Purchase Receipt":
            return ToolResult(ok=True, data=[{"name": "PR-001", "supplier": "SUP-001", "grand_total": 500, "docstatus": 1}])
        return ToolResult(ok=True, data=[])

    def get_stock_balance(self, item_code=None, **kwargs) -> ToolResult:
        self.calls.append(("get_stock_balance", item_code, kwargs))
        quantities = {"ITEM-001": 10, "ITEM-002": 2}
        return ToolResult(
            ok=True,
            data=[
                {
                    "item_code": item_code,
                    "warehouse": kwargs.get("warehouse"),
                    "actual_qty": quantities.get(item_code, 0),
                }
            ],
        )

    def get_stock_ledger_entries(self, **kwargs) -> ToolResult:
        self.calls.append(("get_stock_ledger_entries", kwargs))
        return ToolResult(ok=True, data=[{"item_code": "ITEM-001", "warehouse": "Stores - A", "actual_qty": -3, "stock_value_difference": -24}])

    def create_stock_entry_draft(self, data) -> ToolResult:
        self.calls.append(("create_stock_entry_draft", data))
        return ToolResult(ok=True, data={"doctype": "Stock Entry", "name": "MAT-STE-0001", "docstatus": 0})

    def create_document(self, doctype, data) -> ToolResult:
        self.calls.append(("create_document", doctype, data))
        return ToolResult(ok=True, data={"doctype": doctype, "name": "TASK-NEW-001"})

    def update_document(self, doctype, name, data) -> ToolResult:
        self.calls.append(("update_document", doctype, name, data))
        return ToolResult(ok=True, data={"doctype": doctype, "name": name, **data})


def test_project_cost_context_reads_project_related_documents() -> None:
    client = ProjectsFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.projects.get_project_cost_context",
            "arguments": {"project": "PROJ-001", "company": "Acme", "from_date": "2026-06-01", "to_date": "2026-06-30"},
        }
    )

    assert result.ok
    assert result.data["doctype"] == "Project"
    assert result.data["status"] == "Project Cost Context Ready"
    assert result.data["project"]["cost_center"] == "Bridge - A"
    assert result.data["tasks"][0]["name"] == "TASK-001"
    assert result.data["stock_entries"][0]["name"] == "STE-001"
    assert result.data["purchase_receipts"][0]["name"] == "PR-001"
    assert result.data["risk"] == {"level": "L0", "writes_document": False}
    assert client.calls[0] == ("get_document", "Project", "PROJ-001")
    assert client.calls[2] == (
        "search_documents",
        "Stock Entry",
        {
            "filters": {"project": "PROJ-001", "company": "Acme", "posting_date": ["between", ["2026-06-01", "2026-06-30"]]},
            "fields": [
                "name", "stock_entry_type", "purpose", "posting_date", "docstatus", "company", "project", "modified",
            ],
            "limit": 20,
            "order_by": "posting_date desc, modified desc",
        },
    )


def test_project_exceptions_detect_overdue_tasks_and_project_date() -> None:
    result = ERPNextAdapter(ProjectsFakeClient()).execute({
        "tool": "erpnext.projects.get_project_exceptions",
        "arguments": {"project": "PROJ-001", "as_of_date": "2026-09-01"},
    })
    assert result.ok
    assert result.data["status"] == "Review Required"
    assert {signal["type"] for signal in result.data["signals"]} == {
        "project_end_date_overdue", "overdue_tasks",
    }
    assert result.data["overdue_tasks"][0]["name"] == "TASK-001"


def test_create_project_task_uses_resolved_project_and_controlled_fields() -> None:
    client = ProjectsFakeClient()
    result = ERPNextAdapter(client).execute({
        "tool": "erpnext.projects.create_task",
        "arguments": {
            "project": "PROJ-001", "subject": "完成井壁验收", "priority": "High",
            "exp_start_date": "2026-07-20", "exp_end_date": "2026-07-22",
        },
    })
    assert result.ok
    assert client.calls[-1] == ("create_document", "Task", {
        "doctype": "Task", "project": "PROJ-001", "subject": "完成井壁验收",
        "priority": "High", "status": "Open", "exp_start_date": "2026-07-20", "exp_end_date": "2026-07-22",
    })


def test_update_project_task_only_updates_allowed_fields() -> None:
    client = ProjectsFakeClient()
    result = ERPNextAdapter(client).execute({
        "tool": "erpnext.projects.update_task",
        "arguments": {"task": "TASK-001", "status": "Completed", "progress": 100},
    })
    assert result.ok
    assert client.calls[-1] == ("update_document", "Task", "TASK-001", {"status": "Completed", "progress": 100})


def test_project_material_issue_context_reports_shortages() -> None:
    client = ProjectsFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.projects.get_material_issue_context",
            "arguments": {
                "project": "PROJ-001",
                "source_warehouse": "Stores - A",
                "items": [{"item_code": "ITEM-001", "qty": 8}, {"item_code": "ITEM-002", "qty": 5}],
            },
        }
    )

    assert result.ok
    assert result.data["status"] == "Has Shortage"
    assert result.data["items"][0]["can_issue"] is True
    assert result.data["items"][1]["shortage_qty"] == 3.0
    assert result.data["shortages"] == [result.data["items"][1]]
    assert result.data["risk"] == {"level": "L1", "writes_document": False}


def test_project_material_issue_draft_blocks_shortage_by_default() -> None:
    client = ProjectsFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.projects.create_material_issue_draft",
            "arguments": {
                "project": "PROJ-001",
                "source_warehouse": "Stores - A",
                "items": [{"item_code": "ITEM-002", "qty": 5}],
            },
        }
    )

    assert not result.ok
    assert result.error_type == "insufficient_stock"
    assert result.data["status"] == "Blocked By Shortage"
    assert "create_stock_entry_draft" not in [call[0] for call in client.calls]


def test_project_material_issue_draft_creates_stock_entry_with_project_context() -> None:
    client = ProjectsFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.projects.create_material_issue_draft",
            "arguments": {
                "project": "PROJ-001",
                "source_warehouse": "Stores - A",
                "expense_account": "Materials Consumed - A",
                "items": [{"item_code": "ITEM-001", "qty": 6, "uom": "Bag", "description": "Concrete work"}],
            },
        }
    )

    assert result.ok
    assert result.data["doctype"] == "Stock Entry"
    assert result.data["status"] == "Draft"
    assert result.data["project"] == "PROJ-001"
    assert result.data["source_warehouse"] == "Stores - A"
    assert result.data["risk"] == {
        "level": "L3",
        "requires_confirmation_for_submit": True,
        "submit_tool": "erpnext.stock.submit_document",
    }
    assert client.calls[-1] == (
        "create_stock_entry_draft",
        {
            "stock_entry_type": "Material Issue",
            "purpose": "Material Issue",
            "company": "Acme",
            "remarks": "Project material issue for PROJ-001",
            "items": [
                {
                    "item_code": "ITEM-001",
                    "s_warehouse": "Stores - A",
                    "qty": 6.0,
                    "uom": "Bag",
                    "expense_account": "Materials Consumed - A",
                    "cost_center": "Bridge - A",
                    "project": "PROJ-001",
                    "description": "Concrete work",
                }
            ],
        },
    )


def test_project_material_issue_cost_impact_verifies_submitted_stock_entry() -> None:
    client = ProjectsFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.projects.verify_material_issue_cost_impact",
            "arguments": {"stock_entry": "STE-001", "project": "PROJ-001"},
        }
    )

    assert result.ok
    assert result.data["status"] == "Verified"
    assert result.data["totals"] == {
        "item_issue_qty": 3.0,
        "item_issue_amount": 24.0,
        "ledger_out_qty": 3.0,
        "ledger_value_difference": -24.0,
    }
    assert result.data["projects"] == ["PROJ-001"]
    assert result.data["warnings"] == []
    assert result.data["risk"] == {"level": "L0", "writes_document": False, "moves_stock": False}
    assert client.calls == [
        ("get_document", "Stock Entry", "STE-001"),
        ("get_stock_ledger_entries", {"voucher_type": "Stock Entry", "voucher_no": "STE-001", "limit": 200}),
    ]


def test_project_tools_infer_expected_risk_levels() -> None:
    assert ToolCall.from_dict({"tool": "erpnext.projects.get_project_exceptions"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.projects.create_task"}).risk_level == "L3"
    assert ToolCall.from_dict({"tool": "erpnext.projects.update_task"}).risk_level == "L3"
    assert ToolCall.from_dict({"tool": "erpnext.projects.get_project_cost_context"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.projects.get_material_issue_context"}).risk_level == "L1"
    assert ToolCall.from_dict({"tool": "erpnext.projects.create_material_issue_draft"}).risk_level == "L3"
    assert ToolCall.from_dict({"tool": "erpnext.projects.verify_material_issue_cost_impact"}).risk_level == "L0"
