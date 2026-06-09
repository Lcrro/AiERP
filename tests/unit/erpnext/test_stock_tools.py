from __future__ import annotations

from nexterp_agent.erpnext import ERPNextAdapter
from nexterp_agent.erpnext.schemas import ToolCall, ToolResult


class StockFakeClient:
    def __init__(self) -> None:
        self.calls = []

    def get_document(self, doctype, name) -> ToolResult:
        self.calls.append(("get_document", doctype, name))
        if doctype == "Item" and name == "ITEM-001":
            return ToolResult(ok=True, data={"name": "ITEM-001", "item_code": "ITEM-001", "item_name": "Test Item", "disabled": 0})
        if doctype == "Delivery Note" and name == "DN-001":
            return ToolResult(ok=True, data={"doctype": doctype, "name": name, "docstatus": 1, "status": "Completed", "customer": "Customer A"})
        if doctype == "Purchase Receipt" and name == "PR-001":
            return ToolResult(ok=True, data={"doctype": doctype, "name": name, "docstatus": 1, "status": "Completed", "supplier": "Supplier A"})
        return ToolResult(ok=False, error_type="not_found")

    def search_documents(self, doctype, **kwargs) -> ToolResult:
        self.calls.append(("search_documents", doctype, kwargs))
        if doctype == "Item":
            return ToolResult(
                ok=True,
                data=[{"name": "ITEM-001", "item_code": "ITEM-001", "item_name": "Test Item", "disabled": 0}],
            )
        if doctype == "Stock Ledger Entry":
            return ToolResult(
                ok=True,
                data=[
                    {
                        "name": "SLE-2",
                        "item_code": "ITEM-001",
                        "warehouse": "Stores - A",
                        "posting_date": "2026-06-02",
                        "posting_time": "10:00:00",
                        "actual_qty": -2,
                        "qty_after_transaction": 3,
                        "valuation_rate": 11,
                        "stock_value": 33,
                        "batch_no": "BATCH-001",
                        "is_cancelled": 0,
                    },
                    {
                        "name": "SLE-1",
                        "item_code": "ITEM-001",
                        "warehouse": "Stores - A",
                        "posting_date": "2026-06-01",
                        "posting_time": "09:00:00",
                        "actual_qty": 5,
                        "qty_after_transaction": 5,
                        "valuation_rate": 10,
                        "stock_value": 50,
                        "batch_no": "BATCH-001",
                        "is_cancelled": 0,
                    },
                ],
            )
        return ToolResult(ok=True, data=[])

    def get_stock_balance(self, item_code=None, **kwargs) -> ToolResult:
        self.calls.append(("get_stock_balance", item_code, kwargs))
        return ToolResult(ok=True, data=[{"item_code": item_code, "warehouse": kwargs.get("warehouse"), "actual_qty": 5}])

    def get_item_stock_locations(self, item_code, **kwargs) -> ToolResult:
        self.calls.append(("get_item_stock_locations", item_code, kwargs))
        return ToolResult(ok=True, data=[{"item_code": item_code, "warehouse": "Stores - A", "actual_qty": 5}])

    def get_stock_ledger_entries(self, **kwargs) -> ToolResult:
        self.calls.append(("get_stock_ledger_entries", kwargs))
        return ToolResult(ok=True, data=[{"item_code": "ITEM-001", "actual_qty": -2, "stock_value_difference": -20}])

    def get_stock_settings(self) -> ToolResult:
        self.calls.append(("get_stock_settings",))
        return ToolResult(ok=True, data={"name": "Stock Settings", "allow_negative_stock": 0})

    def create_stock_entry_draft(self, data) -> ToolResult:
        self.calls.append(("create_stock_entry_draft", data))
        return ToolResult(ok=True, data={"doctype": "Stock Entry", "name": "MAT-STE-0001", "docstatus": 0})

    def create_stock_reconciliation_draft(self, data) -> ToolResult:
        self.calls.append(("create_stock_reconciliation_draft", data))
        return ToolResult(ok=True, data={"doctype": "Stock Reconciliation", "name": "MAT-RECO-0001", "docstatus": 0})

    def search_batches(self, **kwargs) -> ToolResult:
        self.calls.append(("search_batches", kwargs))
        return ToolResult(
            ok=True,
            data=[
                {
                    "name": "BATCH-001",
                    "batch_id": "BATCH-001",
                    "item": kwargs.get("item_code"),
                    "manufacturing_date": "2026-01-01",
                    "expiry_date": "2026-12-31",
                    "disabled": 0,
                }
            ],
        )

    def search_serial_numbers(self, **kwargs) -> ToolResult:
        self.calls.append(("search_serial_numbers", kwargs))
        return ToolResult(ok=True, data=[])

    def list_warehouses(self, **kwargs) -> ToolResult:
        self.calls.append(("list_warehouses", kwargs))
        return ToolResult(ok=True, data=[])

    def create_warehouse(self, data) -> ToolResult:
        self.calls.append(("create_warehouse", data))
        return ToolResult(ok=True, data={"doctype": "Warehouse", "name": data["warehouse_name"], "disabled": 0})

    def update_warehouse(self, name, data) -> ToolResult:
        self.calls.append(("update_warehouse", name, data))
        return ToolResult(ok=True, data={"doctype": "Warehouse", "name": name, **data})

    def create_batch(self, data) -> ToolResult:
        self.calls.append(("create_batch", data))
        return ToolResult(ok=True, data={"doctype": "Batch", "name": data.get("batch_id") or "BATCH-001", **data})

    def update_batch(self, name, data) -> ToolResult:
        self.calls.append(("update_batch", name, data))
        return ToolResult(ok=True, data={"doctype": "Batch", "name": name, **data})

    def create_serial_no(self, data) -> ToolResult:
        self.calls.append(("create_serial_no", data))
        return ToolResult(ok=True, data={"doctype": "Serial No", "name": data.get("serial_no") or "SN-001", **data})

    def update_serial_no(self, name, data) -> ToolResult:
        self.calls.append(("update_serial_no", name, data))
        return ToolResult(ok=True, data={"doctype": "Serial No", "name": name, **data})

    def list_pick_lists(self, **kwargs) -> ToolResult:
        self.calls.append(("list_pick_lists", kwargs))
        return ToolResult(ok=True, data=[])

    def create_pick_list_draft(self, data) -> ToolResult:
        self.calls.append(("create_pick_list_draft", data))
        return ToolResult(ok=True, data={"doctype": "Pick List", "name": "PICK-001", "docstatus": 0})

    def list_stock_reservations(self, **kwargs) -> ToolResult:
        self.calls.append(("list_stock_reservations", kwargs))
        return ToolResult(ok=True, data=[])

    def create_stock_reservation_draft(self, data) -> ToolResult:
        self.calls.append(("create_stock_reservation_draft", data))
        return ToolResult(ok=True, data={"doctype": "Stock Reservation Entry", "name": "SRE-001", "docstatus": 0})

    def preview_stock_valuation(self, items) -> ToolResult:
        self.calls.append(("preview_stock_valuation", items))
        return ToolResult(ok=True, data={"status": "preview", "rows": items, "totals": {"stock_value_difference": 20}})

    def allocate_stock_shortages(self, items) -> ToolResult:
        self.calls.append(("allocate_stock_shortages", items))
        return ToolResult(ok=True, data={"status": "has_shortages", "rows": items, "shortage_count": 1})

    def list_delivery_notes(self, **kwargs) -> ToolResult:
        self.calls.append(("list_delivery_notes", kwargs))
        return ToolResult(ok=True, data=[])

    def list_purchase_receipts(self, **kwargs) -> ToolResult:
        self.calls.append(("list_purchase_receipts", kwargs))
        return ToolResult(ok=True, data=[])

    def list_item_reorders(self, **kwargs) -> ToolResult:
        self.calls.append(("list_item_reorders", kwargs))
        return ToolResult(ok=True, data=[{"parent": kwargs.get("item_code"), "warehouse": kwargs.get("warehouse")}])

    def list_quality_inspections(self, **kwargs) -> ToolResult:
        self.calls.append(("list_quality_inspections", kwargs))
        return ToolResult(ok=True, data=[{"item_code": kwargs.get("item_code"), "status": kwargs.get("status")}])

    def create_document(self, doctype, data) -> ToolResult:
        self.calls.append(("create_document", doctype, data))
        return ToolResult(ok=True, data={"doctype": doctype, "name": data.get("name") or data.get("item_group_name") or data.get("uom_name"), **data})

    def update_document(self, doctype, name, data) -> ToolResult:
        self.calls.append(("update_document", doctype, name, data))
        return ToolResult(ok=True, data={"doctype": doctype, "name": name, **data})

    def submit_stock_document(self, doctype, name) -> ToolResult:
        self.calls.append(("submit_stock_document", doctype, name))
        return ToolResult(ok=True, data={"doctype": doctype, "name": name, "docstatus": 1})

    def submit_document(self, doctype, name) -> ToolResult:
        self.calls.append(("submit_document", doctype, name))
        return ToolResult(ok=True, data={"doctype": doctype, "name": name, "docstatus": 1})

    def cancel_document(self, doctype, name) -> ToolResult:
        self.calls.append(("cancel_document", doctype, name))
        return ToolResult(ok=True, data={"doctype": doctype, "name": name, "docstatus": 2})


def test_stock_read_tools_dispatch_with_v02_names() -> None:
    client = StockFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    assert adapter.execute({"tool": "erpnext.stock.get_balance", "arguments": {"item_code": "ITEM-001"}}).ok
    assert adapter.execute({"tool": "erpnext.stock.get_item_locations", "arguments": {"item_code": "ITEM-001"}}).ok
    assert adapter.execute({"tool": "erpnext.stock.get_ledger_entries", "arguments": {"item_code": "ITEM-001"}}).ok
    assert adapter.execute({"tool": "erpnext.stock.get_stock_settings"}).ok
    assert adapter.execute({"tool": "erpnext.stock.search_batches", "arguments": {"item_code": "ITEM-001"}}).ok
    assert adapter.execute({"tool": "erpnext.stock.search_serial_numbers", "arguments": {"item_code": "ITEM-001"}}).ok
    assert adapter.execute({"tool": "erpnext.stock.list_warehouses", "arguments": {"company": "Acme"}}).ok
    assert adapter.execute({"tool": "erpnext.stock.list_item_groups", "arguments": {"query": "Raw"}}).ok
    assert adapter.execute({"tool": "erpnext.stock.list_uoms", "arguments": {"query": "Kg", "enabled": True}}).ok
    assert adapter.execute({"tool": "erpnext.stock.list_pick_lists", "arguments": {"purpose": "Delivery"}}).ok
    assert adapter.execute({"tool": "erpnext.stock.list_reservations", "arguments": {"item_code": "ITEM-001"}}).ok
    assert adapter.execute({"tool": "erpnext.stock.list_delivery_notes", "arguments": {"customer": "Customer A"}}).ok
    assert adapter.execute({"tool": "erpnext.stock.list_purchase_receipts", "arguments": {"supplier": "Supplier A"}}).ok
    assert adapter.execute({"tool": "erpnext.stock.list_item_reorders", "arguments": {"item_code": "ITEM-001"}}).ok
    assert adapter.execute({"tool": "erpnext.stock.list_quality_inspections", "arguments": {"item_code": "ITEM-001"}}).ok

    assert [call[0] for call in client.calls] == [
        "get_stock_balance",
        "get_item_stock_locations",
        "get_stock_ledger_entries",
        "get_stock_settings",
        "search_batches",
        "search_serial_numbers",
        "list_warehouses",
        "search_documents",
        "search_documents",
        "list_pick_lists",
        "list_stock_reservations",
        "list_delivery_notes",
        "list_purchase_receipts",
        "list_item_reorders",
        "list_quality_inspections",
    ]


def test_stock_list_batch_balances_summarizes_ledger_without_moving_stock() -> None:
    client = StockFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.stock.list_batch_balances",
            "arguments": {"item_code": "ITEM-001", "warehouse": "Stores - A", "as_of_date": "2026-06-30"},
        }
    )

    assert result.ok
    assert result.data["doctype"] == "Batch"
    assert result.data["risk"] == {"level": "L0", "moves_stock": False}
    assert result.data["records"] == [
        {
            "item_code": "ITEM-001",
            "batch_no": "BATCH-001",
            "warehouse": "Stores - A",
            "actual_qty": 3.0,
            "latest_posting_date": "2026-06-02",
            "latest_posting_time": "10:00:00",
            "latest_qty_after_transaction": 3,
            "valuation_rate": 11,
            "stock_value": 33,
            "expiry_date": "2026-12-31",
            "disabled": False,
        }
    ]
    assert client.calls == [
        ("search_batches", {"item_code": "ITEM-001", "query": None, "limit": 50}),
        (
            "search_documents",
            "Stock Ledger Entry",
            {
                "filters": {
                    "item_code": "ITEM-001",
                    "is_cancelled": 0,
                    "warehouse": "Stores - A",
                    "batch_no": ["in", ["BATCH-001"]],
                    "posting_date": ["<=", "2026-06-30"],
                },
                "fields": [
                    "name",
                    "item_code",
                    "warehouse",
                    "posting_date",
                    "posting_time",
                    "actual_qty",
                    "qty_after_transaction",
                    "valuation_rate",
                    "stock_value",
                    "batch_no",
                    "is_cancelled",
                ],
                "limit": 500,
                "order_by": "posting_date desc, posting_time desc, creation desc",
            },
        ),
    ]


def test_stock_entry_draft_returns_v02_result_shape() -> None:
    client = StockFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.stock.create_entry_draft",
            "arguments": {
                "purpose": "Material Transfer",
                "items": [{"item_code": "ITEM-001", "s_warehouse": "Stores - A", "t_warehouse": "Stores - B", "qty": 2}],
            },
        }
    )

    assert result.ok
    assert result.data["doctype"] == "Stock Entry"
    assert result.data["name"] == "MAT-STE-0001"
    assert result.data["docstatus"] == 0
    assert result.data["status"] == "Draft"
    assert result.data["risk"] == {
        "level": "L3",
        "requires_confirmation_for_submit": True,
        "submit_tool": "erpnext.stock.submit_document",
    }


def test_stock_reconciliation_draft_requires_resolved_item() -> None:
    client = StockFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.stock.create_reconciliation_draft",
            "arguments": {"items": [{"item_query": "ambiguous", "warehouse": "Stores - A", "qty": 1}]},
        }
    )

    assert not result.ok
    assert result.error_type == "item_resolution_required"
    assert client.calls


def test_stock_submit_requires_v02_confirmation_metadata() -> None:
    client = StockFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    blocked = adapter.execute(
        {"tool": "erpnext.stock.submit_document", "arguments": {"doctype": "Stock Entry", "name": "MAT-STE-0001"}}
    )

    assert not blocked.ok
    assert blocked.error_type == "stock_confirmation_required"
    assert client.calls == []

    allowed = adapter.execute(
        {
            "tool": "erpnext.stock.submit_document",
            "arguments": {
                "doctype": "Stock Entry",
                "name": "MAT-STE-0001",
                "confirmation": {
                    "confirmed_by": "warehouse@example.com",
                    "confirmed_at": "2026-06-09T10:00:00Z",
                    "confirmation_text": "确认提交库存移动 MAT-STE-0001",
                    "reason": "仓库主管已复核数量和仓库。",
                },
            },
        }
    )

    assert allowed.ok
    assert client.calls == [("submit_stock_document", "Stock Entry", "MAT-STE-0001")]


def test_generic_submit_of_stock_doctype_is_guarded() -> None:
    client = StockFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    blocked = adapter.execute(
        {"tool": "erpnext.submit_document", "arguments": {"doctype": "Stock Reconciliation", "name": "MAT-RECO-0001"}}
    )

    assert not blocked.ok
    assert blocked.error_type == "stock_confirmation_required"


def test_stock_item_group_and_uom_master_tools_return_v02_shape() -> None:
    client = StockFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    item_group = adapter.execute(
        {
            "tool": "erpnext.stock.create_item_group",
            "arguments": {"data": {"item_group_name": "Pytest Raw Materials", "parent_item_group": "All Item Groups"}},
        }
    )
    uom = adapter.execute(
        {
            "tool": "erpnext.stock.update_uom",
            "arguments": {"name": "Kg", "data": {"enabled": 1}},
        }
    )

    assert item_group.ok
    assert item_group.data == {
        "doctype": "Item Group",
        "name": "Pytest Raw Materials",
        "docstatus": None,
        "status": "Active",
        "summary": "Created Item Group master record.",
        "next_actions": ["review_master_data"],
        "risk": {"level": "L3", "requires_confirmation_for_submit": False},
    }
    assert uom.ok
    assert uom.data["doctype"] == "UOM"
    assert uom.data["name"] == "Kg"
    assert uom.data["risk"] == {"level": "L3", "requires_confirmation_for_submit": False}
    assert client.calls == [
        (
            "create_document",
            "Item Group",
            {
                "item_group_name": "Pytest Raw Materials",
                "parent_item_group": "All Item Groups",
                "doctype": "Item Group",
            },
        ),
        ("update_document", "UOM", "Kg", {"enabled": 1}),
    ]


def test_stock_batch_and_serial_create_tools_return_v02_shape() -> None:
    client = StockFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    batch = adapter.execute(
        {
            "tool": "erpnext.stock.create_batch",
            "arguments": {"data": {"batch_id": "BATCH-001", "item_code": "ITEM-001"}},
        }
    )
    serial = adapter.execute(
        {
            "tool": "erpnext.stock.create_serial_no",
            "arguments": {"data": {"serial_no": "SN-001", "item_code": "ITEM-001"}},
        }
    )

    assert batch.ok
    assert batch.data["doctype"] == "Batch"
    assert batch.data["name"] == "BATCH-001"
    assert batch.data["risk"] == {"level": "L3", "requires_confirmation_for_submit": False}
    assert serial.ok
    assert serial.data["doctype"] == "Serial No"
    assert serial.data["name"] == "SN-001"
    assert serial.data["risk"] == {"level": "L3", "requires_confirmation_for_submit": False}
    assert client.calls == [
        ("create_batch", {"batch_id": "BATCH-001", "item": "ITEM-001"}),
        ("create_serial_no", {"serial_no": "SN-001", "item_code": "ITEM-001"}),
    ]


def test_stock_batch_and_serial_updates_require_traceability_confirmation() -> None:
    client = StockFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    blocked = adapter.execute(
        {"tool": "erpnext.stock.update_batch", "arguments": {"name": "BATCH-001", "data": {"disabled": 1}}}
    )

    assert not blocked.ok
    assert blocked.error_type == "traceability_confirmation_required"
    assert client.calls == []

    allowed = adapter.execute(
        {
            "tool": "erpnext.stock.update_serial_no",
            "arguments": {
                "name": "SN-001",
                "data": {"status": "Inactive"},
                "confirmation": {
                    "confirmed_by": "warehouse@example.com",
                    "confirmed_at": "2026-06-09T10:00:00Z",
                    "confirmation_text": "确认更新序列号 SN-001",
                    "reason": "仓库主管已复核追溯记录变更。",
                },
            },
        }
    )

    assert allowed.ok
    assert allowed.data["risk"] == {"level": "L4", "requires_confirmation_for_submit": False}
    assert client.calls == [("update_serial_no", "SN-001", {"status": "Inactive"})]


def test_stock_pick_list_and_reservation_drafts_return_v02_shape() -> None:
    client = StockFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    pick_list = adapter.execute(
        {
            "tool": "erpnext.stock.create_pick_list_draft",
            "arguments": {
                "purpose": "Delivery",
                "sales_order": "SO-001",
                "locations": [{"item_code": "ITEM-001", "warehouse": "Stores - A", "qty": 2}],
            },
        }
    )
    reservation = adapter.execute(
        {
            "tool": "erpnext.stock.create_reservation_draft",
            "arguments": {
                "item_code": "ITEM-001",
                "warehouse": "Stores - A",
                "voucher_type": "Sales Order",
                "voucher_no": "SO-001",
                "reserved_qty": 2,
            },
        }
    )

    assert pick_list.ok
    assert pick_list.data["doctype"] == "Pick List"
    assert pick_list.data["status"] == "Draft"
    assert pick_list.data["risk"] == {
        "level": "L3",
        "requires_confirmation_for_submit": True,
        "submit_tool": "erpnext.stock.submit_document",
    }
    assert reservation.ok
    assert reservation.data["doctype"] == "Stock Reservation Entry"
    assert reservation.data["status"] == "Draft"
    assert reservation.data["risk"]["submit_tool"] == "erpnext.stock.submit_document"
    assert client.calls == [
        (
            "create_pick_list_draft",
            {
                "purpose": "Delivery",
                "sales_order": "SO-001",
                "locations": [{"item_code": "ITEM-001", "warehouse": "Stores - A", "qty": 2}],
            },
        ),
        (
            "create_stock_reservation_draft",
            {
                "item_code": "ITEM-001",
                "warehouse": "Stores - A",
                "voucher_type": "Sales Order",
                "voucher_no": "SO-001",
                "reserved_qty": 2,
            },
        ),
    ]


def test_stock_pick_list_submit_is_guarded() -> None:
    client = StockFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    blocked = adapter.execute(
        {"tool": "erpnext.stock.submit_document", "arguments": {"doctype": "Pick List", "name": "PICK-001"}}
    )

    assert not blocked.ok
    assert blocked.error_type == "stock_confirmation_required"
    assert client.calls == []


def test_stock_valuation_and_shortage_previews_return_l1_shape() -> None:
    client = StockFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    valuation = adapter.execute(
        {
            "tool": "erpnext.stock.preview_valuation",
            "arguments": {"items": [{"item_code": "ITEM-001", "warehouse": "Stores - A", "qty_delta": 2, "incoming_rate": 10}]},
        }
    )
    shortages = adapter.execute(
        {
            "tool": "erpnext.stock.allocate_shortages",
            "arguments": {"items": [{"item_code": "ITEM-001", "warehouse": "Stores - A", "required_qty": 8}]},
        }
    )

    assert valuation.ok
    assert valuation.data["status"] == "preview"
    assert valuation.data["risk"] == {"level": "L1", "requires_confirmation_for_submit": False}
    assert valuation.data["preview"]["totals"] == {"stock_value_difference": 20}
    assert shortages.ok
    assert shortages.data["status"] == "has_shortages"
    assert shortages.data["risk"] == {"level": "L1", "requires_confirmation_for_submit": False}
    assert shortages.data["preview"]["shortage_count"] == 1
    assert client.calls == [
        ("preview_stock_valuation", [{"item_code": "ITEM-001", "warehouse": "Stores - A", "qty_delta": 2, "incoming_rate": 10}]),
        ("allocate_stock_shortages", [{"item_code": "ITEM-001", "warehouse": "Stores - A", "required_qty": 8}]),
    ]


def test_stock_delivery_note_purchase_receipt_boundary_impact_is_read_only() -> None:
    client = StockFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {"tool": "erpnext.stock.get_document_impact", "arguments": {"doctype": "Delivery Note", "name": "DN-001"}}
    )

    assert result.ok
    assert result.data["doctype"] == "Delivery Note"
    assert result.data["boundary"] == {
        "owner_module": "Sales",
        "stock_module_role": "read_stock_impact_only",
        "draft_creation_tool": None,
    }
    assert result.data["impact"]["ledger_entry_count"] == 1
    assert result.data["impact"]["total_actual_qty"] == -2
    assert result.data["impact"]["total_stock_value_difference"] == -20
    assert result.data["risk"] == {"level": "L0", "requires_confirmation_for_submit": False}
    assert client.calls == [
        ("get_document", "Delivery Note", "DN-001"),
        ("get_stock_ledger_entries", {"voucher_type": "Delivery Note", "voucher_no": "DN-001", "limit": 100}),
    ]


def test_stock_settings_reorders_and_quality_inspections_are_l0_reads() -> None:
    client = StockFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    settings = adapter.execute({"tool": "erpnext.stock.get_stock_settings"})
    reorders = adapter.execute(
        {
            "tool": "erpnext.stock.list_item_reorders",
            "arguments": {
                "item_code": "ITEM-001",
                "warehouse": "Stores - A",
                "material_request_type": "Purchase",
                "limit": 25,
            },
        }
    )
    inspections = adapter.execute(
        {
            "tool": "erpnext.stock.list_quality_inspections",
            "arguments": {
                "item_code": "ITEM-001",
                "reference_type": "Purchase Receipt",
                "reference_name": "PR-001",
                "inspection_type": "Incoming",
                "status": "Accepted",
                "docstatus": 1,
                "limit": 10,
            },
        }
    )

    assert settings.ok
    assert settings.data["allow_negative_stock"] == 0
    assert reorders.ok
    assert inspections.ok
    assert client.calls == [
        ("get_stock_settings",),
        (
            "list_item_reorders",
            {
                "item_code": "ITEM-001",
                "warehouse": "Stores - A",
                "material_request_type": "Purchase",
                "limit": 25,
            },
        ),
        (
            "list_quality_inspections",
            {
                "item_code": "ITEM-001",
                "reference_type": "Purchase Receipt",
                "reference_name": "PR-001",
                "inspection_type": "Incoming",
                "status": "Accepted",
                "docstatus": 1,
                "limit": 10,
            },
        ),
    ]


def test_stock_tools_infer_expected_risk_levels() -> None:
    assert ToolCall.from_dict({"tool": "erpnext.stock.get_balance"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.stock.list_batch_balances"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.stock.resolve_item"}).risk_level == "L1"
    assert ToolCall.from_dict({"tool": "erpnext.stock.create_entry_draft"}).risk_level == "L3"
    assert ToolCall.from_dict({"tool": "erpnext.stock.create_reconciliation_draft"}).risk_level == "L3"
    assert ToolCall.from_dict({"tool": "erpnext.stock.list_item_groups"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.stock.create_uom"}).risk_level == "L3"
    assert ToolCall.from_dict({"tool": "erpnext.stock.create_batch"}).risk_level == "L3"
    assert ToolCall.from_dict({"tool": "erpnext.stock.update_serial_no"}).risk_level == "L4"
    assert ToolCall.from_dict({"tool": "erpnext.stock.list_pick_lists"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.stock.create_pick_list_draft"}).risk_level == "L3"
    assert ToolCall.from_dict({"tool": "erpnext.stock.create_reservation_draft"}).risk_level == "L3"
    assert ToolCall.from_dict({"tool": "erpnext.stock.preview_valuation"}).risk_level == "L1"
    assert ToolCall.from_dict({"tool": "erpnext.stock.allocate_shortages"}).risk_level == "L1"
    assert ToolCall.from_dict({"tool": "erpnext.stock.list_delivery_notes"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.stock.get_document_impact"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.stock.get_stock_settings"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.stock.list_item_reorders"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.stock.list_quality_inspections"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.stock.submit_document"}).risk_level == "L4"
