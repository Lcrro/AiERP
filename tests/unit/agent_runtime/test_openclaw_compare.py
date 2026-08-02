from __future__ import annotations

import json
from pathlib import Path
import subprocess

from nexterp_agent.workbench.openclaw_compare import OpenClawPreviewRunner, summarize_existing_result, to_wsl_path


def test_to_wsl_path_preserves_spaces_without_shell_quoting() -> None:
    path = Path(r"C:\Users\Administrator\Documents\nexterp agent 2\scripts\openclaw\runner.sh")
    assert to_wsl_path(path) == "/mnt/c/Users/Administrator/Documents/nexterp agent 2/scripts/openclaw/runner.sh"


def test_existing_result_is_reduced_to_auditable_summary() -> None:
    summary = summarize_existing_result({
        "status": "needs_confirmation",
        "message": "请确认",
        "questions": ["需要哪一种？"],
        "steps": [{"label": "解析实体", "action": "resolve_entities", "result": {"summary": "已解析"}}],
        "pending_tool_call": {"tool": "create", "arguments": {"qty": 2}},
    }, duration_ms=123)

    assert summary["duration_ms"] == 123
    assert summary["question_count"] == 1
    assert summary["steps"] == [{"label": "解析实体", "action": "resolve_entities", "summary": "已解析"}]


def test_openclaw_runner_returns_only_safe_trace_and_uses_preview_session(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    raw = {
        "status": "ok",
        "result": {
            "payloads": [{"text": "请选择水泥"}],
            "meta": {
                "durationMs": 456,
                "agentMeta": {
                    "sessionId": "session-1",
                    "sessionFile": "/home/administrator/.openclaw-nexterp/agents/main/sessions/session-1.jsonl",
                    "provider": "deepseek",
                    "model": "deepseek-v4-flash",
                },
                "toolSummary": {"calls": 2, "tools": ["nexterp_search_capabilities", "nexterp_prepare_operation"], "failures": 0},
                "systemPromptReport": {"must_not_leak": True},
            },
        },
    }
    trace = {
        "steps": [{"tool": "nexterp_search_capabilities", "arguments": {"query": "水泥"}, "result": {"status": "found"}}],
        "loaded_nodes": [{"node_id": "op.material_request.create", "label": "创建材料申请草稿"}],
        "questions": ["请选择水泥"],
        "confirmation": None,
        "pending_id": None,
    }

    def fake_run(command, **_kwargs):
        calls.append(command)
        payload = raw if len(calls) == 1 else trace
        return subprocess.CompletedProcess(command, 0, json.dumps(payload, ensure_ascii=False).encode(), b"")

    runner = OpenClawPreviewRunner(tmp_path, runner=fake_run)
    result = runner.run(text="申请水泥", project_label="合流1.3标", employee_name="毛晓泉")

    assert ":compare-preview:" in calls[0][calls[0].index("--session-key") + 1]
    assert result["message"] == "请选择水泥"
    assert result["loaded_nodes"][0]["node_id"] == "op.material_request.create"
    assert "systemPromptReport" not in result
