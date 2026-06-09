from __future__ import annotations

from nexterp_agent.erpnext import ERPNextAdapter
from nexterp_agent.erpnext.schemas import ToolCall, ToolResult


class AssetsFakeClient:
    def __init__(self) -> None:
        self.calls = []

    def search_documents(self, doctype, **kwargs) -> ToolResult:
        self.calls.append(("search_documents", doctype, kwargs))
        if doctype == "Asset Depreciation Schedule":
            return ToolResult(ok=True, data=[{"name": "ADS-1", "asset": "AST-1", "finance_book": "Main"}])
        return ToolResult(ok=True, data=[{"name": f"{doctype}-1"}])

    def create_document(self, doctype, data) -> ToolResult:
        self.calls.append(("create_document", doctype, data))
        return ToolResult(ok=True, data={"doctype": doctype, "name": f"{doctype}-1", **data})

    def get_document(self, doctype, name) -> ToolResult:
        self.calls.append(("get_document", doctype, name))
        if doctype == "Asset":
            return ToolResult(
                ok=True,
                data={
                    "doctype": "Asset",
                    "name": name,
                    "asset_name": "Forklift",
                    "company": "Acme",
                    "item_code": "FORKLIFT-001",
                    "asset_category": "Equipment",
                    "status": "Submitted",
                    "docstatus": 1,
                    "gross_purchase_amount": 10000,
                    "value_after_depreciation": 7000,
                    "finance_books": [
                        {"finance_book": "Main", "depreciation_method": "Straight Line", "value_after_depreciation": 7000},
                        {"finance_book": "Tax", "depreciation_method": "Straight Line", "value_after_depreciation": 6500},
                    ],
                },
            )
        if doctype == "Asset Depreciation Schedule":
            return ToolResult(
                ok=True,
                data={
                    "doctype": "Asset Depreciation Schedule",
                    "name": name,
                    "asset": "AST-1",
                    "finance_book": "Main",
                    "status": "Active",
                    "docstatus": 1,
                    "value_after_depreciation": 7000,
                    "depreciation_schedule": [
                        {
                            "schedule_date": "2026-12-31",
                            "depreciation_amount": 1000,
                            "accumulated_depreciation_amount": 3000,
                            "journal_entry": None,
                            "depreciation_status": "Pending",
                        },
                        {
                            "schedule_date": "2027-12-31",
                            "depreciation_amount": 1000,
                            "accumulated_depreciation_amount": 4000,
                            "journal_entry": None,
                            "depreciation_status": "Pending",
                        }
                    ],
                },
            )
        return ToolResult(ok=True, data={"doctype": doctype, "name": name, "status": "Submitted"})

    def submit_document(self, doctype, name) -> ToolResult:
        self.calls.append(("submit_document", doctype, name))
        return ToolResult(ok=True, data={"doctype": doctype, "name": name, "docstatus": 1})

    def cancel_document(self, doctype, name) -> ToolResult:
        self.calls.append(("cancel_document", doctype, name))
        return ToolResult(ok=True, data={"doctype": doctype, "name": name, "docstatus": 2})


def test_assets_read_tools_are_read_only_and_normalized() -> None:
    client = AssetsFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.assets.search_assets",
            "arguments": {"company": "Acme", "asset_category": "Vehicles", "query": "truck"},
        }
    )

    assert result.ok
    assert result.data["doctype"] == "Asset"
    assert result.data["risk"] == {"level": "L0"}
    assert client.calls == [
        (
            "search_documents",
            "Asset",
            {
                "filters": {"company": "Acme", "asset_category": "Vehicles", "asset_name": ["like", "%truck%"]},
                "fields": [
                    "name",
                    "asset_name",
                    "item_code",
                    "asset_category",
                    "company",
                    "location",
                    "custodian",
                    "status",
                    "docstatus",
                    "gross_purchase_amount",
                    "available_for_use_date",
                ],
                "limit": 50,
                "offset": 0,
                "order_by": "modified desc",
            },
        )
    ]


def test_assets_draft_tools_force_docstatus_zero_and_return_shape() -> None:
    client = AssetsFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.assets.create_value_adjustment_draft",
            "arguments": {"data": {"asset": "AST-1", "docstatus": 1, "current_asset_value": 1000}},
        }
    )

    assert result.ok
    assert result.data["doctype"] == "Asset Value Adjustment"
    assert result.data["docstatus"] == 0
    assert result.data["risk"] == {"level": "L3", "requires_confirmation_for_submit": True}
    assert client.calls == [
        (
            "create_document",
            "Asset Value Adjustment",
            {
                "asset": "AST-1",
                "docstatus": 0,
                "current_asset_value": 1000,
                "doctype": "Asset Value Adjustment",
            },
        )
    ]


def test_assets_prepare_disposal_or_sale_is_read_only() -> None:
    client = AssetsFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {"tool": "erpnext.assets.prepare_disposal_or_sale", "arguments": {"asset": "AST-1", "action": "sell"}}
    )

    assert result.ok
    assert result.data["action"] == "sell"
    assert result.data["risk"]["level"] == "L5_FINANCIAL"
    assert client.calls == [("get_document", "Asset", "AST-1")]


def test_assets_financial_snapshot_is_read_only_and_can_expand_schedule_rows() -> None:
    client = AssetsFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.assets.get_financial_snapshot",
            "arguments": {"asset": "AST-1", "finance_book": "Main", "include_schedule_rows": True},
        }
    )

    assert result.ok
    assert result.data["status"] == "Financial Snapshot"
    assert result.data["risk"] == {
        "level": "L0",
        "creates_financial_posting": False,
        "does_not_process_depreciation": True,
        "does_not_create_disposal_or_sale": True,
    }
    assert result.data["asset"]["gross_purchase_amount"] == 10000
    assert result.data["finance_books"] == [
        {"finance_book": "Main", "depreciation_method": "Straight Line", "value_after_depreciation": 7000}
    ]
    assert result.data["depreciation_schedules"][0]["schedule_rows"][0]["depreciation_status"] == "Pending"
    assert client.calls == [
        ("get_document", "Asset", "AST-1"),
        (
            "search_documents",
            "Asset Depreciation Schedule",
            {
                "filters": {"asset": "AST-1", "finance_book": "Main"},
                "fields": ["name", "asset", "finance_book", "status", "docstatus", "value_after_depreciation"],
                "limit": 10,
                "order_by": "modified desc",
            },
        ),
        ("get_document", "Asset Depreciation Schedule", "ADS-1"),
    ]


def test_assets_get_depreciation_schedule_can_expand_due_rows_without_posting() -> None:
    client = AssetsFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.assets.get_depreciation_schedule",
            "arguments": {
                "asset": "AST-1",
                "finance_book": "Main",
                "status": "Active",
                "include_rows": True,
                "only_due_before": "2026-12-31",
            },
        }
    )

    assert result.ok
    assert result.data["doctype"] == "Asset Depreciation Schedule"
    assert result.data["risk"] == {"level": "L0", "creates_financial_posting": False}
    assert result.data["records"][0]["schedule_row_count"] == 1
    assert result.data["records"][0]["schedule_rows"] == [
        {
            "schedule_date": "2026-12-31",
            "depreciation_amount": 1000,
            "accumulated_depreciation_amount": 3000,
            "depreciation_status": "Pending",
        }
    ]
    assert client.calls == [
        (
            "search_documents",
            "Asset Depreciation Schedule",
            {
                "filters": {"asset": "AST-1", "finance_book": "Main", "status": "Active"},
                "fields": ["name", "asset", "finance_book", "status", "docstatus", "value_after_depreciation"],
                "limit": 20,
                "offset": 0,
                "order_by": "modified desc",
            },
        ),
        ("get_document", "Asset Depreciation Schedule", "ADS-1"),
    ]


def test_assets_submit_requires_confirmation_metadata() -> None:
    client = AssetsFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    blocked = adapter.execute(
        {"tool": "erpnext.assets.submit_document", "arguments": {"doctype": "Asset", "name": "AST-1"}}
    )

    assert not blocked.ok
    assert blocked.error_type == "asset_confirmation_required"
    assert blocked.meta["risk_level"] == "L5_FINANCIAL"
    assert client.calls == []

    allowed = adapter.execute(
        {
            "tool": "erpnext.assets.submit_document",
            "arguments": {
                "doctype": "Asset Movement",
                "name": "MOV-1",
                "confirmation": {
                    "confirmed_by": "asset.manager@example.com",
                    "confirmed_at": "2026-06-09T10:00:00Z",
                    "confirmation_text": "Confirm asset movement MOV-1",
                    "reason": "Manager approved transfer.",
                },
            },
        }
    )

    assert allowed.ok
    assert allowed.data["risk"]["level"] == "L4"
    assert client.calls == [("submit_document", "Asset Movement", "MOV-1")]


def test_asset_value_adjustment_submit_is_financial_high_risk() -> None:
    client = AssetsFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.assets.submit_document",
            "arguments": {
                "doctype": "Asset Value Adjustment",
                "name": "AVA-1",
                "confirmation": {
                    "confirmed_by": "finance.manager@example.com",
                    "confirmed_at": "2026-06-09T10:00:00Z",
                    "confirmation_text": "Confirm asset value adjustment AVA-1",
                    "reason": "Finance approved asset value adjustment.",
                },
            },
        }
    )

    assert result.ok
    assert result.data["risk"]["level"] == "L5_FINANCIAL"
    assert client.calls == [("submit_document", "Asset Value Adjustment", "AVA-1")]


def test_generic_submit_blocks_asset_without_confirmation() -> None:
    client = AssetsFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute({"tool": "erpnext.submit_document", "arguments": {"doctype": "Asset", "name": "AST-1"}})

    assert not result.ok
    assert result.error_type == "asset_confirmation_required"
    assert client.calls == []


def test_assets_tools_infer_expected_risk_levels() -> None:
    assert ToolCall.from_dict({"tool": "erpnext.assets.search_assets"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.assets.get_financial_snapshot"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.assets.get_depreciation_schedule"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.assets.prepare_disposal_or_sale"}).risk_level == "L1"
    assert ToolCall.from_dict({"tool": "erpnext.assets.create_asset_draft"}).risk_level == "L3"
    assert ToolCall.from_dict({"tool": "erpnext.assets.submit_document"}).risk_level == "L4"
