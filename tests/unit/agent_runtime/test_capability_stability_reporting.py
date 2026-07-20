from __future__ import annotations

from scripts.acceptance.capability_runtime_stability import (
    BenchmarkCase,
    _executed_tools,
    _failure_category,
    _selected_capabilities,
    summarize_results,
)


READ_CASE = BenchmarkCase(
    case_id="stock",
    user="employee@example.com",
    text="查库存",
    expected_capability="stock.balance.query",
    expected_tool="erpnext.stock.get_item_locations",
    mode="read",
    accepted_statuses=("completed",),
)


def test_discovered_capability_is_not_execution_evidence() -> None:
    steps = [
        {
            "action": "discover_capabilities",
            "result": {"capabilities": [{"capability_id": "stock.balance.query"}]},
        }
    ]

    assert _selected_capabilities(steps) == []
    assert _failure_category(
        result={"status": "completed"},
        case=READ_CASE,
        selected_capabilities=[],
        executed_tools=[],
        resolver_inventory_evidence=False,
        bypass_attempts=0,
    ) == "capability_not_selected"


def test_read_success_requires_selected_capability_and_expected_tool() -> None:
    steps = [
        {
            "action": "propose_business_action",
            "result": {"capability": "stock.balance.query"},
        },
        {
            "action": "execute_tool",
            "payload": {"tool": "erpnext.stock.get_item_locations"},
        },
    ]

    selected = _selected_capabilities(steps)
    tools = _executed_tools(steps)
    assert selected == ["stock.balance.query"]
    assert tools == ["erpnext.stock.get_item_locations"]
    assert _failure_category(
        result={"status": "completed"},
        case=READ_CASE,
        selected_capabilities=selected,
        executed_tools=tools,
        resolver_inventory_evidence=False,
        bypass_attempts=0,
    ) == "none"


def test_live_resolver_inventory_is_valid_alternate_stock_evidence() -> None:
    resolver_case = BenchmarkCase(
        **{**READ_CASE.__dict__, "allow_resolver_inventory": True}
    )

    assert _failure_category(
        result={"status": "completed"},
        case=resolver_case,
        selected_capabilities=[],
        executed_tools=[],
        resolver_inventory_evidence=True,
        bypass_attempts=0,
    ) == "none"


def test_summary_separates_clean_recovered_and_failed_runs() -> None:
    rows = [
        {
            "case_id": "stock",
            "success": True,
            "status": "completed",
            "outcome": "clean_success",
            "failure_category": "none",
            "step_count": 5,
            "elapsed_ms": 100,
            "repair_count": 0,
            "repair_categories": [],
            "repeat_count": 0,
            "bypass_attempts": 0,
        },
        {
            "case_id": "stock",
            "success": True,
            "status": "completed",
            "outcome": "recovered_success",
            "failure_category": "none",
            "step_count": 9,
            "elapsed_ms": 300,
            "repair_count": 1,
            "repair_categories": ["resolver_required"],
            "repeat_count": 0,
            "bypass_attempts": 0,
        },
        {
            "case_id": "stock",
            "success": False,
            "status": "failed",
            "outcome": "failed",
            "failure_category": "planner_non_convergence",
            "step_count": 10,
            "elapsed_ms": 500,
            "repair_count": 0,
            "repair_categories": [],
            "repeat_count": 1,
            "bypass_attempts": 0,
        },
    ]

    summary = summarize_results(rows)

    assert summary["successes"] == 2
    assert summary["clean_successes"] == 1
    assert summary["recovered_successes"] == 1
    assert summary["failure_categories"] == {"planner_non_convergence": 1}
    assert summary["repair_categories"] == {"resolver_required": 1}
    assert summary["p50_elapsed_ms"] == 300
    assert summary["p95_elapsed_ms"] == 500
    assert summary["per_case"]["stock"]["success_rate"] == 0.6667
