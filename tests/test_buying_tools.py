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
            return ToolResult(ok=True, data=[{"name": "IP-1", "item_code": "ITEM-001", "supplier": "SUP-BLOCKED", "price_list_rate": 9.5, "currency": "USD"}])
        return ToolResult(ok=True, data=[])

    def create_document(self, doctype, data) -> ToolResult:
        self.calls.append(("create_document", doctype, data))
        return ToolResult(ok=True, data={"doctype": doctype, "name": f"{doctype}-0001", "docstatus": data.get("docstatus", 0)})

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
    assert ToolCall.from_dict({"tool": "erpnext.buying.compare_supplier_quotations"}).risk_level == "L1"
    assert ToolCall.from_dict({"tool": "erpnext.buying.create_purchase_order_draft"}).risk_level == "L3"
    assert ToolCall.from_dict({"tool": "erpnext.buying.submit_document"}).risk_level == "L4"
