from __future__ import annotations

from scripts.openclaw.benchmark_material_request_runtime import evaluate


def test_confirmation_requires_frozen_pending_without_execute_call() -> None:
    passed, _ = evaluate({
        "pending_id": "pending-1",
        "confirmation": {"title": "创建材料申请"},
        "tool_summary": {"tools": ["nexterp_prepare_operation"]},
    }, "confirmation")

    assert passed


def test_clarification_requires_no_pending_and_an_actionable_question() -> None:
    passed, _ = evaluate({
        "message": "请选择具体的标准物料。",
        "questions": [],
        "tool_summary": {"tools": ["nexterp_prepare_operation"]},
    }, "clarification")

    assert passed


def test_preview_benchmark_rejects_any_execute_attempt() -> None:
    passed, _ = evaluate({
        "pending_id": "pending-1",
        "confirmation": {"title": "创建材料申请"},
        "tool_summary": {"tools": ["nexterp_execute_prepared_operation"]},
    }, "confirmation")

    assert not passed
