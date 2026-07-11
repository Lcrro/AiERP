from __future__ import annotations

from nexterp_agent.erpnext import ERPNextAdapter
from nexterp_agent.erpnext.schemas import ToolCall, ToolResult


class BuyingFakeClient:
    def __init__(self) -> None:
        self.calls = []

    def get_document(self, doctype, name) -> ToolResult:
        self.calls.append(("get_document", doctype, name))
        if doctype == "Supplier" and name == "SUP-BLOCKED":
            return ToolResult(
                ok=True,
                data={
                    "doctype": "Supplier",
                    "name": name,
                    "supplier_name": "Blocked Supplier",
                    "supplier_group": "Raw Material",
                    "supplier_type": "Company",
                    "disabled": 0,
                    "on_hold": 0,
                    "prevent_pos": 1,
                    "warn_rfqs": 1,
                },
            )
        if doctype == "Item" and name == "ITEM-001":
            return ToolResult(ok=True, data={"doctype": "Item", "name": name, "item_code": name, "item_name": "Test Item", "stock_uom": "Nos", "disabled": 0})
        if doctype == "Item":
            return ToolResult(ok=False, error_type="not_found", error="not found")
        if doctype == "Material Request" and name == "MR-001":
            return ToolResult(
                ok=True,
                data={
                    "doctype": "Material Request",
                    "name": "MR-001",
                    "docstatus": 1,
                    "material_request_type": "Purchase",
                    "company": "Acme",
                    "schedule_date": "2026-06-12",
                    "items": [
                        {
                            "name": "MRI-001",
                            "item_code": "ITEM-001",
                            "item_name": "Test Item",
                            "qty": 10,
                            "ordered_qty": 2,
                            "uom": "Nos",
                            "warehouse": "Stores - A",
                            "project": "PROJ-001",
                            "cost_center": "Bridge - A",
                            "description": "Project material demand",
                        }
                    ],
                },
            )
        if doctype == "Material Request" and name == "MR-DRAFT":
            return ToolResult(
                ok=True,
                data={
                    "doctype": "Material Request",
                    "name": "MR-DRAFT",
                    "docstatus": 0,
                    "material_request_type": "Purchase",
                    "items": [],
                },
            )
        if doctype == "Purchase Order" and name == "PO-001":
            return ToolResult(
                ok=True,
                data={
                    "doctype": "Purchase Order",
                    "name": "PO-001",
                    "supplier": "SUP-001",
                    "company": "Acme",
                    "currency": "USD",
                    "docstatus": 1,
                    "status": "To Receive and Bill",
                    "items": [
                        {
                            "name": "POI-001",
                            "item_code": "ITEM-001",
                            "item_name": "Test Item",
                            "qty": 10,
                            "received_qty": 3,
                            "uom": "Nos",
                            "warehouse": "Stores - A",
                            "rate": 12,
                            "price_list_rate": 12,
                            "conversion_factor": 1,
                            "project": "PROJ-001",
                            "cost_center": "Bridge - A",
                            "description": "Approved project purchase",
                        }
                    ],
                },
            )
        if doctype == "Purchase Order" and name == "PO-DRAFT":
            return ToolResult(
                ok=True,
                data={
                    "doctype": "Purchase Order",
                    "name": "PO-DRAFT",
                    "docstatus": 0,
                    "status": "Draft",
                    "items": [],
                },
            )
        if doctype == "Purchase Receipt" and name == "PR-001":
            return ToolResult(
                ok=True,
                data={
                    "doctype": "Purchase Receipt",
                    "name": name,
                    "supplier": "SUP-001",
                    "supplier_name": "Supplier One",
                    "company": "Acme",
                    "currency": "USD",
                    "posting_date": "2026-06-08",
                    "project": "PROJ-001",
                    "cost_center": "Main - A",
                    "docstatus": 1,
                    "is_return": 0,
                    "items": [
                        {
                            "name": "PRI-001",
                            "item_code": "ITEM-001",
                            "item_name": "Test Item",
                            "received_qty": 10,
                            "qty": 10,
                            "returned_qty": 2,
                            "warehouse": "Stores - A",
                            "uom": "Nos",
                            "stock_uom": "Nos",
                            "conversion_factor": 1,
                            "rate": 12,
                            "price_list_rate": 12,
                            "purchase_order": "PO-001",
                            "purchase_order_item": "POI-001",
                            "project": "PROJ-001",
                            "cost_center": "Main - A",
                            "expense_account": "Cost of Goods Sold - A",
                            "description": "Wrong-spec material",
                        },
                        {
                            "name": "PRI-002",
                            "item_code": "ITEM-002",
                            "item_name": "Second Item",
                            "received_qty": 5,
                            "qty": 5,
                            "warehouse": "Stores - A",
                            "uom": "Nos",
                            "stock_uom": "Nos",
                            "conversion_factor": 1,
                            "rate": 6,
                        },
                    ],
                },
            )
        if doctype == "Purchase Receipt" and name == "PR-DRAFT":
            return ToolResult(ok=True, data={"doctype": "Purchase Receipt", "name": name, "docstatus": 0, "items": []})
        if doctype == "Purchase Receipt" and name == "PR-RETURN":
            return ToolResult(ok=True, data={"doctype": "Purchase Receipt", "name": name, "docstatus": 1, "is_return": 1, "items": []})
        if doctype == "Supplier Quotation" and name == "SQ-LOW":
            return ToolResult(
                ok=True,
                data={
                    "doctype": "Supplier Quotation",
                    "name": name,
                    "supplier": "SUP-LOW",
                    "supplier_name": "Supplier Low",
                    "currency": "USD",
                    "docstatus": 1,
                    "grand_total": 90,
                    "items": [{"item_code": "ITEM-001", "item_name": "Test Item", "qty": 10, "rate": 9, "amount": 90, "uom": "Nos"}],
                },
            )
        if doctype == "Supplier Quotation" and name == "SQ-HIGH":
            return ToolResult(
                ok=True,
                data={
                    "doctype": "Supplier Quotation",
                    "name": name,
                    "supplier": "SUP-HIGH",
                    "supplier_name": "Supplier High",
                    "currency": "USD",
                    "docstatus": 1,
                    "grand_total": 120,
                    "items": [{"item_code": "ITEM-001", "item_name": "Test Item", "qty": 10, "rate": 12, "amount": 120, "uom": "Nos"}],
                },
            )
        if doctype == "Supplier Quotation" and name == "SQ-DRAFT":
            return ToolResult(
                ok=True,
                data={
                    "doctype": "Supplier Quotation",
                    "name": name,
                    "supplier": "SUP-DRAFT",
                    "currency": "USD",
                    "docstatus": 0,
                    "grand_total": 80,
                    "items": [{"item_code": "ITEM-001", "qty": 10, "rate": 8, "amount": 80}],
                },
            )
        if doctype == "Supplier Quotation":
            return ToolResult(ok=False, error_type="not_found", error="not found")
        return ToolResult(ok=True, data={"doctype": doctype, "name": name})

    def search_documents(self, doctype, **kwargs) -> ToolResult:
        self.calls.append(("search_documents", doctype, kwargs))
        if doctype == "Supplier Scorecard":
            return ToolResult(
                ok=True,
                data=[
                    {
                        "name": "SSC-1",
                        "supplier": kwargs.get("filters", {}).get("supplier", "SUP-BLOCKED"),
                        "status": "Active",
                        "supplier_score": 62,
                        "warn_rfqs": 1,
                        "prevent_pos": 1,
                    }
                ],
            )
        if doctype == "Item Supplier":
            return ToolResult(ok=True, data=[{"name": "ISUP-1", "parent": "ITEM-001", "supplier": "SUP-BLOCKED"}])
        if doctype == "Item Price":
            supplier = kwargs.get("filters", {}).get("supplier")
            if supplier == "SUP-001":
                return ToolResult(
                    ok=True,
                    data=[
                        {
                            "name": "IP-BUY-1",
                            "item_code": "ITEM-001",
                            "supplier": supplier,
                            "price_list": "Standard Buying",
                            "price_list_rate": 8.5,
                            "currency": "USD",
                            "uom": "Nos",
                            "valid_from": "2026-01-01",
                            "valid_upto": "2027-12-31",
                        }
                    ],
                )
            return ToolResult(ok=True, data=[{"name": "IP-1", "item_code": "ITEM-001", "supplier": "SUP-BLOCKED", "price_list_rate": 9.5, "currency": "USD"}])
        return ToolResult(ok=True, data=[])

    def create_document(self, doctype, data) -> ToolResult:
        self.calls.append(("create_document", doctype, data))
        return ToolResult(ok=True, data={"doctype": doctype, "name": f"{doctype}-0001", "docstatus": data.get("docstatus", 0)})

    def add_comment(self, reference_doctype, reference_name, content, **kwargs) -> ToolResult:
        self.calls.append(("add_comment", reference_doctype, reference_name, content, kwargs))
        return ToolResult(ok=True, data={"reference_doctype": reference_doctype, "reference_name": reference_name, "content": content})

    def create_todo(self, description, **kwargs) -> ToolResult:
        self.calls.append(("create_todo", description, kwargs))
        return ToolResult(ok=True, data={"description": description, **kwargs})

    def call_method(self, method, args=None, http_method="POST") -> ToolResult:
        self.calls.append(("call_method", method, args, http_method))
        return ToolResult(ok=True, data={"count": 2, "groups": {"Purchase": [{"item_code": "ITEM-001"}]}})

    def run_report(self, report_name, **kwargs) -> ToolResult:
        self.calls.append(("run_report", report_name, kwargs))
        return ToolResult(ok=True, data={"columns": [], "rows": [{"supplier": "SUP-001"}], "raw": {}})

    def submit_document(self, doctype, name) -> ToolResult:
        self.calls.append(("submit_document", doctype, name))
        return ToolResult(ok=True, data={"doctype": doctype, "name": name, "docstatus": 1})


def test_purchase_order_draft_returns_v02_result_shape_and_resolves_items() -> None:
    client = BuyingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.buying.create_purchase_order_draft",
            "arguments": {
                "supplier": "SUP-001",
                "schedule_date": "2026-06-10",
                "items": [{"item_code": "ITEM-001", "qty": 3, "rate": 12}],
            },
        }
    )

    assert result.ok
    assert result.data["doctype"] == "Purchase Order"
    assert result.data["docstatus"] == 0
    assert result.data["status"] == "Draft"
    assert result.data["next_actions"] == ["review_draft", "confirm_submit"]
    assert result.data["risk"] == {
        "level": "L3",
        "requires_confirmation_for_submit": True,
        "submit_tool": "erpnext.buying.submit_document",
    }
    assert client.calls[-1] == (
        "create_document",
        "Purchase Order",
        {
            "doctype": "Purchase Order",
            "supplier": "SUP-001",
            "schedule_date": "2026-06-10",
            "items": [{"item_name": "Test Item", "item_code": "ITEM-001", "qty": 3, "uom": "Nos", "rate": 12}],
            "docstatus": 0,
        },
    )


def test_material_request_draft_preserves_project_context_on_items() -> None:
    client = BuyingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.buying.create_material_request_draft",
            "arguments": {
                "schedule_date": "2026-06-12",
                "items": [
                    {
                        "item_code": "ITEM-001",
                        "qty": 3,
                        "warehouse": "Stores - A",
                        "project": "PROJ-001",
                        "cost_center": "Bridge - A",
                    }
                ],
            },
        }
    )

    assert result.ok
    assert client.calls[-1] == (
        "create_document",
        "Material Request",
        {
            "doctype": "Material Request",
            "material_request_type": "Purchase",
            "schedule_date": "2026-06-12",
            "items": [
                {
                    "item_name": "Test Item",
                    "item_code": "ITEM-001",
                    "qty": 3,
                    "uom": "Nos",
                    "schedule_date": "2026-06-12",
                    "warehouse": "Stores - A",
                    "project": "PROJ-001",
                    "cost_center": "Bridge - A",
                }
            ],
            "docstatus": 0,
        },
    )


def test_purchase_order_from_material_request_preserves_source_references() -> None:
    client = BuyingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.buying.create_purchase_order_from_material_request_draft",
            "arguments": {
                "material_request": "MR-001",
                "supplier": "SUP-001",
                "transaction_date": "2026-06-11",
                "selected_items": [{"material_request_item": "MRI-001", "qty": 5, "rate": 12}],
            },
        }
    )

    assert result.ok
    assert result.data["source_material_request"] == "MR-001"
    assert result.data["source_item_count"] == 1
    assert result.data["risk"] == {
        "level": "L3",
        "requires_confirmation_for_submit": True,
        "submit_tool": "erpnext.buying.submit_document",
    }
    assert client.calls == [
        ("get_document", "Material Request", "MR-001"),
        ("get_document", "Item", "ITEM-001"),
        (
            "create_document",
            "Purchase Order",
            {
                "doctype": "Purchase Order",
                "supplier": "SUP-001",
                "transaction_date": "2026-06-11",
                "schedule_date": "2026-06-12",
                "company": "Acme",
                "items": [
                    {
                        "item_name": "Test Item",
                        "item_code": "ITEM-001",
                        "qty": 5.0,
                        "uom": "Nos",
                        "schedule_date": "2026-06-12",
                        "warehouse": "Stores - A",
                        "rate": 12,
                        "description": "Project material demand",
                        "project": "PROJ-001",
                        "cost_center": "Bridge - A",
                        "material_request": "MR-001",
                        "material_request_item": "MRI-001",
                    }
                ],
                "docstatus": 0,
            },
        ),
    ]


def test_purchase_order_from_material_request_resolves_missing_supplier_price() -> None:
    client = BuyingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.buying.create_purchase_order_from_material_request_draft",
            "arguments": {
                "material_request": "MR-001",
                "supplier": "SUP-001",
                "transaction_date": "2026-06-11",
            },
        }
    )

    assert result.ok
    create_call = next(call for call in client.calls if call[0:2] == ("create_document", "Purchase Order"))
    assert create_call[2]["buying_price_list"] == "Standard Buying"
    assert create_call[2]["items"][0]["rate"] == 8.5
    assert create_call[2]["items"][0]["price_list_rate"] == 8.5


def test_purchase_order_from_material_request_requires_submitted_purchase_request() -> None:
    client = BuyingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.buying.create_purchase_order_from_material_request_draft",
            "arguments": {"material_request": "MR-DRAFT", "supplier": "SUP-001"},
        }
    )

    assert not result.ok
    assert result.error_type == "validation_error"
    assert result.data["status"] == "Not Submitted"
    assert result.data["next_actions"] == ["submit_material_request", "retry_purchase_order_creation"]
    assert client.calls == [("get_document", "Material Request", "MR-DRAFT")]


def test_purchase_receipt_from_purchase_order_preserves_source_references() -> None:
    client = BuyingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.buying.create_purchase_receipt_from_purchase_order_draft",
            "arguments": {
                "purchase_order": "PO-001",
                "posting_date": "2026-06-12",
                "selected_items": [{"purchase_order_item": "POI-001", "qty": 4, "warehouse": "Stores - B"}],
            },
        }
    )

    assert result.ok
    assert result.data["source_purchase_order"] == "PO-001"
    assert result.data["source_item_count"] == 1
    assert result.data["risk"] == {
        "level": "L3",
        "requires_confirmation_for_submit": True,
        "submit_tool": "erpnext.buying.submit_document",
    }
    assert client.calls == [
        ("get_document", "Purchase Order", "PO-001"),
        ("get_document", "Item", "ITEM-001"),
        (
            "create_document",
            "Purchase Receipt",
            {
                "doctype": "Purchase Receipt",
                "supplier": "SUP-001",
                "posting_date": "2026-06-12",
                "company": "Acme",
                "items": [
                    {
                        "item_name": "Test Item",
                        "item_code": "ITEM-001",
                        "qty": 4.0,
                        "uom": "Nos",
                        "warehouse": "Stores - B",
                        "rate": 12,
                        "price_list_rate": 12,
                        "conversion_factor": 1,
                        "description": "Approved project purchase",
                        "project": "PROJ-001",
                        "cost_center": "Bridge - A",
                        "purchase_order": "PO-001",
                        "purchase_order_item": "POI-001",
                    }
                ],
                "docstatus": 0,
            },
        ),
    ]


def test_purchase_receipt_from_purchase_order_requires_submitted_order() -> None:
    client = BuyingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.buying.create_purchase_receipt_from_purchase_order_draft",
            "arguments": {"purchase_order": "PO-DRAFT"},
        }
    )

    assert not result.ok
    assert result.error_type == "validation_error"
    assert result.data["status"] == "Not Submitted"
    assert result.data["next_actions"] == ["submit_purchase_order", "retry_purchase_receipt_creation"]
    assert client.calls == [("get_document", "Purchase Order", "PO-DRAFT")]


def test_record_purchase_receipt_discrepancy_adds_comment_todo_and_return_preview() -> None:
    client = BuyingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.buying.record_purchase_receipt_discrepancy",
            "arguments": {
                "purchase_receipt": "PR-001",
                "description": "送货规格与采购订单不一致，要求供应商确认退换货。",
                "discrepancy_type": "spec_mismatch",
                "severity": "High",
                "reported_by": "warehouse@example.com",
                "assigned_to": "buyer@example.com",
                "items": [
                    {
                        "purchase_receipt_item": "PRI-001",
                        "item_code": "ITEM-001",
                        "qty": 3,
                        "expected": "M12*80",
                        "actual": "M10*80",
                        "reason": "规格不符",
                    }
                ],
            },
        }
    )

    assert result.ok
    assert result.data["status"] == "Discrepancy Recorded"
    assert result.data["risk"] == {"level": "L2", "writes_comment": True, "creates_todo": True, "does_not_submit": True}
    assert result.data["discrepancy"] == {
        "type": "spec_mismatch",
        "severity": "High",
        "description": "送货规格与采购订单不一致，要求供应商确认退换货。",
        "reported_by": "warehouse@example.com",
        "item_count": 1,
    }
    assert result.data["return_preview"]["status"] == "Return Context Ready"
    assert result.data["return_preview"]["return_items"][0]["return_qty"] == -3.0
    assert result.data["next_actions"] == ["review_discrepancy_record", "follow_up_supplier", "create_purchase_receipt_return_draft"]
    assert client.calls == [
        ("get_document", "Purchase Receipt", "PR-001"),
        (
            "add_comment",
            "Purchase Receipt",
            "PR-001",
            result.data["comment"]["content"],
            {"comment_email": "agent@example.com", "comment_by": "Nexterp Agent"},
        ),
        (
            "create_todo",
            "跟进采购收货 PR-001 到货差异：送货规格与采购订单不一致，要求供应商确认退换货。",
            {
                "allocated_to": "buyer@example.com",
                "priority": "High",
                "reference_type": "Purchase Receipt",
                "reference_name": "PR-001",
                "date": None,
            },
        ),
    ]


def test_purchase_receipt_return_context_previews_returnable_rows() -> None:
    client = BuyingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.buying.get_purchase_receipt_return_context",
            "arguments": {
                "purchase_receipt": "PR-001",
                "items": [{"purchase_receipt_item": "PRI-001", "qty": 3, "reason": "送货规格不一致"}],
            },
        }
    )

    assert result.ok
    assert result.data["status"] == "Return Context Ready"
    assert result.data["risk"] == {"level": "L1", "writes_document": False}
    assert result.data["return_items"] == [
        {
            "purchase_receipt_item": "PRI-001",
            "item_code": "ITEM-001",
            "item_name": "Test Item",
            "requested_qty": 3.0,
            "return_qty": -3.0,
            "returnable_qty_before_request": 8.0,
            "warehouse": "Stores - A",
            "uom": "Nos",
            "stock_uom": "Nos",
            "conversion_factor": 1,
            "rate": 12.0,
            "price_list_rate": 12.0,
            "purchase_order": "PO-001",
            "purchase_order_item": "POI-001",
            "project": "PROJ-001",
            "cost_center": "Main - A",
            "expense_account": "Cost of Goods Sold - A",
            "description": "Wrong-spec material",
            "reason": "送货规格不一致",
        }
    ]
    assert result.data["errors"] == []
    assert client.calls == [("get_document", "Purchase Receipt", "PR-001")]


def test_purchase_receipt_return_draft_creates_negative_qty_return_document() -> None:
    client = BuyingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.buying.create_purchase_receipt_return_draft",
            "arguments": {
                "purchase_receipt": "PR-001",
                "posting_date": "2026-06-09",
                "items": [{"item_code": "ITEM-001", "qty": 4}],
                "reason": "全部退回供应商重送",
            },
        }
    )

    assert result.ok
    assert result.data["doctype"] == "Purchase Receipt"
    assert result.data["status"] == "Draft"
    assert result.data["return_against"] == "PR-001"
    assert result.data["return_item_count"] == 1
    assert result.data["risk"] == {
        "level": "L3",
        "requires_confirmation_for_submit": True,
        "submit_tool": "erpnext.buying.submit_document",
    }
    assert client.calls[-1] == (
        "create_document",
        "Purchase Receipt",
        {
            "doctype": "Purchase Receipt",
            "naming_series": "MAT-PR-RET-.YYYY.-",
            "supplier": "SUP-001",
            "company": "Acme",
            "posting_date": "2026-06-09",
            "currency": "USD",
            "is_return": 1,
            "return_against": "PR-001",
            "project": "PROJ-001",
            "cost_center": "Main - A",
            "remarks": "全部退回供应商重送",
            "items": [
                {
                    "item_code": "ITEM-001",
                    "item_name": "Test Item",
                    "qty": -4.0,
                    "received_qty": -4.0,
                    "uom": "Nos",
                    "stock_uom": "Nos",
                    "conversion_factor": 1,
                    "warehouse": "Stores - A",
                    "rate": 12.0,
                    "price_list_rate": 12.0,
                    "purchase_receipt_item": "PRI-001",
                    "purchase_order": "PO-001",
                    "purchase_order_item": "POI-001",
                    "project": "PROJ-001",
                    "cost_center": "Main - A",
                    "expense_account": "Cost of Goods Sold - A",
                    "description": "Wrong-spec material | Return reason: 全部退回供应商重送",
                }
            ],
            "docstatus": 0,
        },
    )


def test_purchase_receipt_return_blocks_invalid_original_or_quantity() -> None:
    client = BuyingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    draft_original = adapter.execute(
        {"tool": "erpnext.buying.get_purchase_receipt_return_context", "arguments": {"purchase_receipt": "PR-DRAFT"}}
    )
    return_original = adapter.execute(
        {"tool": "erpnext.buying.get_purchase_receipt_return_context", "arguments": {"purchase_receipt": "PR-RETURN"}}
    )
    too_much = adapter.execute(
        {
            "tool": "erpnext.buying.create_purchase_receipt_return_draft",
            "arguments": {"purchase_receipt": "PR-001", "items": [{"purchase_receipt_item": "PRI-001", "qty": 99}]},
        }
    )

    assert not draft_original.ok
    assert draft_original.error_type == "validation_error"
    assert not return_original.ok
    assert return_original.error_type == "validation_error"
    assert not too_much.ok
    assert too_much.error_type == "validation_error"
    assert too_much.data["errors"][0]["type"] == "qty_exceeds_returnable"


def test_buying_draft_rejects_unconfirmed_selected_item_code() -> None:
    client = BuyingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.buying.create_material_request_draft",
            "arguments": {"items": [{"selected_item_code": "ITEM-001", "qty": 1}]},
        }
    )

    assert not result.ok
    assert result.error_type == "item_resolution_required"
    assert result.data["status"] == "needs_item_resolution"
    assert result.data["next_actions"] == ["search_items", "confirm_item_selection", "retry_draft_creation"]
    assert client.calls == []


def test_buying_submit_requires_confirmation_metadata_and_returns_stable_shape() -> None:
    client = BuyingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    blocked = adapter.execute({"tool": "erpnext.buying.submit_document", "arguments": {"doctype": "Purchase Order", "name": "PO-0001"}})

    assert not blocked.ok
    assert blocked.error_type == "buying_confirmation_required"
    assert client.calls == []

    allowed = adapter.execute(
        {
            "tool": "erpnext.buying.submit_document",
            "arguments": {
                "doctype": "Purchase Order",
                "name": "PO-0001",
                "confirmation": {
                    "confirmed_by": "buyer@example.com",
                    "confirmed_at": "2026-06-09T10:00:00Z",
                    "confirmation_text": "确认提交采购订单 PO-0001",
                    "reason": "主管已确认供应商和价格",
                },
            },
        }
    )

    assert allowed.ok
    assert allowed.data["doctype"] == "Purchase Order"
    assert allowed.data["docstatus"] == 1
    assert allowed.data["status"] == "Submitted"
    assert allowed.data["risk"]["level"] == "L4"
    assert client.calls == [("submit_document", "Purchase Order", "PO-0001")]


def test_purchase_suggestions_and_analysis_have_next_actions_and_l0_risk() -> None:
    client = BuyingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    suggestions = adapter.execute({"tool": "erpnext.buying.generate_purchase_suggestions", "arguments": {"limit": 5}})
    analysis = adapter.execute({"tool": "erpnext.buying.run_purchase_analysis", "arguments": {"company": "Acme"}})

    assert suggestions.ok
    assert suggestions.data["status"] == "Suggestions Generated"
    assert suggestions.data["next_actions"] == ["review_suggestions", "create_material_request_draft"]
    assert suggestions.data["risk"]["level"] == "L0"
    assert analysis.ok
    assert analysis.data["report_name"] == "Purchase Analytics"
    assert analysis.data["risk"]["level"] == "L0"


def test_supplier_scorecard_search_and_procurement_profile_are_read_only() -> None:
    client = BuyingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    scorecards = adapter.execute(
        {"tool": "erpnext.buying.search_supplier_scorecards", "arguments": {"supplier": "SUP-BLOCKED"}}
    )
    profile = adapter.execute(
        {
            "tool": "erpnext.buying.get_supplier_procurement_profile",
            "arguments": {"supplier": "SUP-BLOCKED", "item_code": "ITEM-001", "currency": "USD"},
        }
    )

    assert scorecards.ok
    assert scorecards.data["doctype"] == "Supplier Scorecard"
    assert scorecards.data["risk"]["level"] == "L0"
    assert profile.ok
    assert profile.data["status"] == "Profile Ready"
    assert profile.data["risk"] == {"level": "L1", "creates_procurement_document": False}
    assert profile.data["eligibility"]["eligible_for_rfq"] == "warning"
    assert profile.data["eligibility"]["eligible_for_po"] == "blocked"
    assert profile.data["eligibility"]["rfq_warnings"] == ["warn_rfqs", "scorecard_warn_rfqs"]
    assert profile.data["eligibility"]["po_blockers"] == ["prevent_pos", "scorecard_prevent_pos"]
    assert profile.data["item_suppliers"][0]["name"] == "ISUP-1"
    assert profile.data["item_prices"][0]["name"] == "IP-1"
    assert client.calls == [
        (
            "search_documents",
            "Supplier Scorecard",
            {
                "filters": {"supplier": "SUP-BLOCKED"},
                "fields": [
                    "name",
                    "supplier",
                    "status",
                    "supplier_score",
                    "warn_rfqs",
                    "prevent_rfqs",
                    "warn_pos",
                    "prevent_pos",
                    "modified",
                ],
                "limit": 50,
                "offset": 0,
                "order_by": "modified desc",
            },
        ),
        ("get_document", "Supplier", "SUP-BLOCKED"),
        (
            "search_documents",
            "Supplier Scorecard",
            {
                "filters": {"supplier": "SUP-BLOCKED"},
                "fields": [
                    "name",
                    "supplier",
                    "status",
                    "supplier_score",
                    "warn_rfqs",
                    "prevent_rfqs",
                    "warn_pos",
                    "prevent_pos",
                    "modified",
                ],
                "limit": 5,
                "order_by": "modified desc",
            },
        ),
        (
            "search_documents",
            "Item Supplier",
            {
                "filters": {"parent": "ITEM-001", "supplier": "SUP-BLOCKED"},
                "fields": ["name", "parent", "supplier", "supplier_part_no"],
                "limit": 20,
                "order_by": "modified desc",
            },
        ),
        (
            "search_documents",
            "Item Price",
            {
                "filters": {"item_code": "ITEM-001", "buying": 1, "currency": "USD", "supplier": "SUP-BLOCKED"},
                "fields": ["name", "item_code", "price_list", "price_list_rate", "currency", "supplier", "valid_from", "valid_upto"],
                "limit": 20,
                "order_by": "valid_from desc",
            },
        ),
    ]


def test_compare_supplier_quotations_ranks_without_awarding_business() -> None:
    client = BuyingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.buying.compare_supplier_quotations",
            "arguments": {"supplier_quotations": ["SQ-HIGH", "SQ-LOW", "SQ-DRAFT"]},
        }
    )

    assert result.ok
    assert result.data["status"] == "Comparison Ready"
    assert result.data["risk"] == {"level": "L1", "requires_confirmation_for_submit": False, "does_not_award": True}
    assert result.data["excluded_quotations"][0]["name"] == "SQ-DRAFT"
    assert result.data["excluded_quotations"][0]["reason"] == "draft_not_included"
    assert result.data["total_ranking"][0]["name"] == "SQ-LOW"
    assert result.data["total_ranking"][0]["total_amount"] == 90.0
    assert result.data["item_comparisons"][0]["best_supplier_quotation"] == "SQ-LOW"
    assert result.data["recommendation"] == {
        "status": "lowest_total",
        "supplier_quotation": "SQ-LOW",
        "supplier": "SUP-LOW",
        "total_amount": 90.0,
        "currency": "USD",
        "requires_human_review": True,
        "award_tool": None,
        "draft_po_tool": "erpnext.buying.create_purchase_order_draft",
    }
    assert client.calls == [
        ("get_document", "Supplier Quotation", "SQ-HIGH"),
        ("get_document", "Supplier Quotation", "SQ-LOW"),
        ("get_document", "Supplier Quotation", "SQ-DRAFT"),
    ]


def test_compare_supplier_quotations_requires_submitted_quotes_by_default() -> None:
    client = BuyingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.buying.compare_supplier_quotations",
            "arguments": {"supplier_quotations": ["SQ-DRAFT", "SQ-DRAFT"]},
        }
    )

    assert not result.ok
    assert result.error_type == "no_comparable_quotations"
    assert result.data["risk"]["level"] == "L1"
    assert result.data["excluded_quotations"][0]["reason"] == "draft_not_included"


def test_compare_supplier_quotations_requires_two_names() -> None:
    client = BuyingFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute({"tool": "erpnext.buying.compare_supplier_quotations", "arguments": {"supplier_quotations": ["SQ-LOW"]}})

    assert not result.ok
    assert result.error_type == "validation_error"
    assert result.data["risk"]["level"] == "L1"
    assert client.calls == []


def test_buying_tools_infer_expected_risk_levels() -> None:
    assert ToolCall.from_dict({"tool": "erpnext.buying.search_suppliers"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.buying.search_supplier_scorecards"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.buying.get_supplier_procurement_profile"}).risk_level == "L1"
    assert ToolCall.from_dict({"tool": "erpnext.buying.get_purchase_receipt_return_context"}).risk_level == "L1"
    assert ToolCall.from_dict({"tool": "erpnext.buying.compare_supplier_quotations"}).risk_level == "L1"
    assert ToolCall.from_dict({"tool": "erpnext.buying.record_purchase_receipt_discrepancy"}).risk_level == "L2"
    assert ToolCall.from_dict({"tool": "erpnext.buying.create_purchase_order_draft"}).risk_level == "L3"
    assert ToolCall.from_dict({"tool": "erpnext.buying.create_purchase_order_from_material_request_draft"}).risk_level == "L3"
    assert ToolCall.from_dict({"tool": "erpnext.buying.create_purchase_receipt_from_purchase_order_draft"}).risk_level == "L3"
    assert ToolCall.from_dict({"tool": "erpnext.buying.create_purchase_receipt_return_draft"}).risk_level == "L3"
    assert ToolCall.from_dict({"tool": "erpnext.buying.submit_document"}).risk_level == "L4"
