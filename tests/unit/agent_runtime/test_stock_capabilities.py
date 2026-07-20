from __future__ import annotations

from datetime import date

import pytest

from nexterp_agent.agent_runtime.business_capabilities import (
    CapabilityCompilationError,
    StockBusinessIntentDraft,
    StockCapabilityCompiler,
    StockCapabilityGraph,
    verify_stock_result,
)


TODAY = date(2026, 7, 20)


def _loader(documents=None):
    documents = documents or {}

    def load(doctype, name):
        return documents[(doctype, name)]

    return load


def _compile(payload, runtime=None):
    intent = StockBusinessIntentDraft.from_dict(payload)
    return StockCapabilityCompiler(_loader()).compile(
        intent,
        runtime_context=runtime or {"company": "STEC (Demo)", "project": "PROJ-001", "warehouse": "Project WH - SD"},
        today=TODAY,
    )


def test_graph_exposes_four_stock_business_goals() -> None:
    cards = StockCapabilityGraph().cards()
    assert {card["goal"] for card in cards} == {
        "query_stock_balance",
        "create_stock_transfer",
        "create_project_material_issue",
        "create_stock_reconciliation",
    }
    assert next(card for card in cards if card["goal"] == "query_stock_balance")["write"] is False


def test_query_stock_balance_compiles_to_item_locations_read_only() -> None:
    prepared = _compile({"goal": "query_stock_balance", "items": [{"item_code": "SAFE-000005"}]})
    assert prepared.write is False
    assert prepared.tool_call == {
        "tool": "erpnext.stock.get_item_locations",
        "arguments": {"item_code": "SAFE-000005", "include_zero": False, "limit": 200},
    }


def test_query_requires_one_resolved_item() -> None:
    with pytest.raises(CapabilityCompilationError, match="唯一物料"):
        _compile({"goal": "query_stock_balance", "items": []})
    with pytest.raises(CapabilityCompilationError, match="已解析物料"):
        _compile({"goal": "query_stock_balance", "items": [{"qty": 1}]})


def test_transfer_compiles_resolved_warehouses_and_positive_items() -> None:
    prepared = _compile({
        "goal": "create_stock_transfer",
        "source_warehouse": "Base WH - SD",
        "target_warehouse": "Project WH - SD",
        "items": [{"item_code": "SAFE-000005", "qty": 100, "uom": "双"}],
        "remarks": "开工前调拨",
    })
    assert prepared.tool_call["tool"] == "erpnext.stock.create_transfer_draft"
    assert prepared.tool_call["arguments"]["source_warehouse"] == "Base WH - SD"
    assert prepared.tool_call["arguments"]["target_warehouse"] == "Project WH - SD"
    assert prepared.tool_call["arguments"]["items"] == [{"item_code": "SAFE-000005", "qty": 100.0, "uom": "双"}]
    assert prepared.confirmation_hash


def test_transfer_rejects_same_or_missing_warehouse() -> None:
    with pytest.raises(CapabilityCompilationError, match="源仓或目标仓"):
        _compile({"goal": "create_stock_transfer", "items": [{"item_code": "A", "qty": 1}]})
    with pytest.raises(CapabilityCompilationError, match="不能相同"):
        _compile({
            "goal": "create_stock_transfer",
            "source_warehouse": "WH-A",
            "target_warehouse": "WH-A",
            "items": [{"item_code": "A", "qty": 1}],
        })


def test_project_issue_uses_runtime_project_and_warehouse() -> None:
    prepared = _compile({
        "goal": "create_project_material_issue",
        "items": [{"item_code": "SAFE-000005", "qty": 20, "uom": "双"}],
    })
    assert prepared.tool_call["tool"] == "erpnext.projects.create_material_issue_draft"
    assert prepared.tool_call["arguments"]["project"] == "PROJ-001"
    assert prepared.tool_call["arguments"]["source_warehouse"] == "Project WH - SD"
    assert prepared.tool_call["arguments"]["posting_date"] == "2026-07-20"


def test_project_issue_requires_runtime_scope() -> None:
    with pytest.raises(CapabilityCompilationError, match="缺少项目"):
        _compile(
            {"goal": "create_project_material_issue", "source_warehouse": "WH", "items": [{"item_code": "A", "qty": 1}]},
            runtime={"company": "STEC"},
        )


def test_reconciliation_allows_zero_physical_count_and_rate() -> None:
    prepared = _compile({
        "goal": "create_stock_reconciliation",
        "warehouse": "Project WH - SD",
        "items": [{"item_code": "SAFE-000005", "qty": 0, "valuation_rate": 12.5}],
    })
    assert prepared.tool_call["tool"] == "erpnext.stock.create_reconciliation_draft"
    assert prepared.tool_call["arguments"]["items"] == [{
        "item_code": "SAFE-000005",
        "warehouse": "Project WH - SD",
        "qty": 0.0,
        "valuation_rate": 12.5,
    }]


def test_reconciliation_rejects_negative_physical_count() -> None:
    with pytest.raises(ValueError, match="at least 0"):
        StockBusinessIntentDraft.from_dict({
            "goal": "create_stock_reconciliation",
            "items": [{"item_code": "A", "qty": -1}],
        })


def test_verify_transfer_reads_back_warehouse_lineage() -> None:
    prepared = _compile({
        "goal": "create_stock_transfer",
        "source_warehouse": "WH-A",
        "target_warehouse": "WH-B",
        "items": [{"item_code": "A", "qty": 1}],
    })
    document = {
        "doctype": "Stock Entry",
        "name": "STE-001",
        "items": [{"item_code": "A", "s_warehouse": "WH-A", "t_warehouse": "WH-B", "qty": 1}],
    }
    result = verify_stock_result(
        prepared,
        {"ok": True, "data": {"doctype": "Stock Entry", "name": "STE-001"}},
        _loader({("Stock Entry", "STE-001"): document}),
    )
    assert result["ok"] is True
    assert "transfer_warehouses_match" in result["checks"]


def test_verify_project_issue_detects_missing_project_lineage() -> None:
    prepared = _compile({
        "goal": "create_project_material_issue",
        "project": "PROJ-001",
        "source_warehouse": "WH-A",
        "items": [{"item_code": "A", "qty": 1}],
    })
    result = verify_stock_result(
        prepared,
        {"ok": True, "data": {"doctype": "Stock Entry", "name": "STE-002"}},
        _loader({("Stock Entry", "STE-002"): {"name": "STE-002", "items": [{"project": "OTHER"}]}}),
    )
    assert result == {
        "ok": False,
        "reason": "project_lineage_missing",
        "checks": ["tool_result_ok", "document_read_back", "document_identity_matches"],
        "document": {"name": "STE-002", "items": [{"project": "OTHER"}]},
    }


def test_invalid_stock_goal_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported stock goal"):
        StockBusinessIntentDraft.from_dict({"goal": "invent_stock"})
