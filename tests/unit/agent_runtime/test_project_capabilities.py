from __future__ import annotations

from datetime import date

import pytest

from nexterp_agent.agent_runtime.business_capabilities import (
    CapabilityCompilationError,
    ProjectBusinessIntentDraft,
    ProjectCapabilityCompiler,
    ProjectCapabilityGraph,
    verify_project_result,
)


TODAY = date(2026, 7, 20)
PROJECT = {"doctype": "Project", "name": "PROJ-001", "project_name": "合流1.3标", "status": "Open"}


def _loader(documents=None):
    documents = documents or {("Project", "PROJ-001"): PROJECT}

    def load(doctype, name):
        return documents[(doctype, name)]

    return load


def _compile(payload, documents=None, runtime=None):
    return ProjectCapabilityCompiler(_loader(documents)).compile(
        ProjectBusinessIntentDraft.from_dict(payload),
        runtime_context=runtime or {"company": "STEC (Demo)", "project": "PROJ-001"},
        today=TODAY,
    )


def test_graph_exposes_four_project_goals() -> None:
    cards = ProjectCapabilityGraph().cards()
    assert {card["goal"] for card in cards} == {
        "query_project_cost", "query_project_exceptions", "create_project_task", "update_project_task",
    }
    assert sum(not card["write"] for card in cards) == 2


def test_project_cost_and_exceptions_compile_read_only() -> None:
    cost = _compile({"goal": "query_project_cost", "from_date": "2026-07-01"})
    assert cost.write is False
    assert cost.tool_call["tool"] == "erpnext.projects.get_project_cost_context"
    exceptions = _compile({"goal": "query_project_exceptions"})
    assert exceptions.tool_call == {
        "tool": "erpnext.projects.get_project_exceptions",
        "arguments": {"project": "PROJ-001", "as_of_date": "2026-07-20", "limit": 200},
    }


def test_create_task_requires_subject_and_uses_runtime_project() -> None:
    with pytest.raises(CapabilityCompilationError, match="任务名称"):
        _compile({"goal": "create_project_task"})
    prepared = _compile({
        "goal": "create_project_task", "subject": "完成井壁验收", "priority": "High",
        "exp_start_date": "2026-07-20", "exp_end_date": "2026-07-22",
    })
    assert prepared.tool_call["tool"] == "erpnext.projects.create_task"
    assert prepared.tool_call["arguments"]["project"] == "PROJ-001"
    assert prepared.write is True


def test_project_mismatch_is_rejected() -> None:
    with pytest.raises(CapabilityCompilationError, match="不一致"):
        _compile({"goal": "query_project_cost", "project": "OTHER"})


def test_update_task_requires_resolved_source_and_changes() -> None:
    documents = {
        ("Project", "PROJ-001"): PROJECT,
        ("Task", "TASK-001"): {"doctype": "Task", "name": "TASK-001", "project": "PROJ-001", "status": "Working"},
    }
    with pytest.raises(CapabilityCompilationError, match="唯一任务"):
        _compile({"goal": "update_project_task", "status": "Completed"}, documents)
    prepared = _compile({
        "goal": "update_project_task",
        "source_documents": [{"doctype": "Task", "name": "TASK-001"}],
        "status": "Completed", "progress": 100,
    }, documents)
    assert prepared.tool_call == {
        "tool": "erpnext.projects.update_task",
        "arguments": {"task": "TASK-001", "status": "Completed", "progress": 100.0},
    }


def test_verify_created_task_checks_project_lineage() -> None:
    prepared = _compile({"goal": "create_project_task", "subject": "完成井壁验收"})
    documents = {
        ("Project", "PROJ-001"): PROJECT,
        ("Task", "TASK-NEW"): {"doctype": "Task", "name": "TASK-NEW", "project": "PROJ-001", "subject": "完成井壁验收"},
    }
    result = verify_project_result(
        prepared,
        {"ok": True, "data": {"doctype": "Task", "name": "TASK-NEW"}},
        _loader(documents),
    )
    assert result["ok"] is True
    assert "task_fields_verified" in result["checks"]
