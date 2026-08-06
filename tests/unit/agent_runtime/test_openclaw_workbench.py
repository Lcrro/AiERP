from __future__ import annotations

import json
from pathlib import Path
import subprocess
import time

import pytest

from nexterp_agent.agent_runtime.session import RuntimeSessionStore
from nexterp_agent.workbench import openclaw_runtime
from nexterp_agent.workbench.openclaw_runtime import (
    CapabilityAPIClient,
    OpenClawWorkbenchRunner,
    load_capability_api_token,
    workbench_external_subject,
    workbench_session_key,
)
from nexterp_agent.workbench.server import AgentWorkbenchService, infer_intent_mode


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("查询采购订单的状态", "read"),
        ("采购订单有哪些延期", "analyze"),
        ("帮我采购一批帆布手套", "write"),
        ("新增标准物料：内六角螺丝 M8×45", "write"),
        ("把刚才的申请提交", "write"),
    ],
)
def test_intent_mode_classifies_effect_instead_of_business_nouns(text: str, expected: str) -> None:
    assert infer_intent_mode(text) == expected


def test_workbench_identity_and_session_are_stable_and_scope_isolated() -> None:
    first = workbench_external_subject("mao.xiaoquan@stec-up.local")
    assert first == workbench_external_subject("MAO.XIAOQUAN@stec-up.local")
    assert "mao.xiaoquan" not in first
    assert workbench_session_key("user@example.com", "PRJ-1", "conversation-a").startswith("agent:main:workbench:")
    assert workbench_session_key("user@example.com", "PRJ-1", "conversation-a") != workbench_session_key(
        "user@example.com", "PRJ-2", "conversation-a"
    )


def test_capability_token_loader_reads_protected_wsl_file_without_shell_expansion(monkeypatch) -> None:
    captured = {}

    def fake_run(command, **_kwargs):
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, stdout=b"service-token", stderr=b"")

    monkeypatch.delenv("NEXTERP_CAPABILITY_API_TOKEN", raising=False)
    monkeypatch.setattr(openclaw_runtime.subprocess, "run", fake_run)

    assert load_capability_api_token() == "service-token"
    assert captured["command"][:3] == ["wsl.exe", "--", "python3"]
    assert "bash" not in captured["command"]


def test_openclaw_workbench_runner_maps_prepare_result_to_confirmation_and_candidates(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    raw = {
        "status": "ok",
        "result": {
            "payloads": [{"text": "我找到了两种水泥，请选择后再确认申请。"}],
            "meta": {
                "durationMs": 321,
                "agentMeta": {
                    "sessionFile": "/home/user/.openclaw-nexterp/agents/main/sessions/session.jsonl",
                    "provider": "deepseek",
                    "model": "deepseek-v4-flash",
                },
            },
        },
    }
    trace = {
        "business_status": "needs_confirmation",
        "pending_id": "pending-1",
        "confirmation": {"title": "创建材料申请"},
        "questions": [],
        "loaded_nodes": [{"node_id": "op.material_request.create"}],
        "choices": [{
            "raw_item_text": "水泥",
            "candidates": [{"value": "MAT-1", "label": "水泥42.5袋装", "meta": "50kg", "stock_uom": "包"}],
        }],
        "candidates": [],
        "steps": [{
            "tool": "nexterp_prepare_operation",
            "arguments": {"operation_id": "op.material_request.create"},
            "result": {"status": "needs_confirmation", "pending_id": "pending-1"},
        }],
    }

    def fake_run(command, **_kwargs):
        calls.append(command)
        payload = raw if len(calls) == 1 else trace
        return subprocess.CompletedProcess(command, 0, json.dumps(payload, ensure_ascii=False).encode(), b"")

    runner = OpenClawWorkbenchRunner(tmp_path, runner=fake_run)
    result = runner.run(
        text="申请10包水泥",
        user="mao.xiaoquan@stec-up.local",
        employee_name="毛晓泉",
        position="材料员",
        project_code="PRJ-HL-13",
        project_label="合流1.3标",
        warehouse="WH-HL-13",
        conversation_id="conversation-a",
    )

    assert calls[0][calls[0].index("--external-subject") + 1] == workbench_external_subject(
        "mao.xiaoquan@stec-up.local"
    )
    assert ":workbench:" in calls[0][calls[0].index("--session-key") + 1]
    assert "--last-turn" in calls[1]
    assert result["status"] == "needs_confirmation"
    assert result["pending_tool_call"]["arguments"]["pending_id"] == "pending-1"
    assert result["candidates"][0]["candidates"][0]["item_code"] == "MAT-1"
    assert result["steps"][0]["label"] == "解析并准备操作"


def test_capability_client_executes_frozen_pending_with_trusted_headers() -> None:
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps({"ok": True, "status": "completed", "result": {}}).encode()

    def opener(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    client = CapabilityAPIClient(token_loader=lambda: "service-token", opener=opener)
    payload = client.execute("pending-1", external_subject="subject-1", session_key="session-1")

    request = captured["request"]
    assert payload["status"] == "completed"
    assert request.headers["Authorization"] == "Bearer service-token"
    assert request.headers["X-nexterp-external-subject"] == "subject-1"
    assert json.loads(request.data)["pending_id"] == "pending-1"


def test_openclaw_confirmation_reports_verified_item_and_returns_item_link(tmp_path: Path) -> None:
    class CapabilityClient:
        def execute(self, pending_id, *, external_subject, session_key):
            assert pending_id == "pending-item"
            assert external_subject.startswith("nexterp-workbench-")
            assert ":workbench:" in session_key
            return {
                "status": "completed",
                "result": {
                    "document": {
                        "doctype": "Item",
                        "name": "FAST-000124",
                        "item_name": "内六角螺丝 M9*47 碳钢 8.8 镀锌",
                        "disabled": 0,
                    }
                },
            }

    runner = OpenClawWorkbenchRunner(tmp_path, capability_client=CapabilityClient())
    result = runner.confirm(
        pending_id="pending-item",
        user="pan.feng@stec-up.local",
        project_code="PRJ-HL-13",
        conversation_id="item-create",
    )

    assert result["status"] == "completed"
    assert "通过 ERPNext 回读验证" in result["message"]
    assert result["document_links"] == [{"doctype": "Item", "name": "FAST-000124"}]


def test_workbench_service_uses_openclaw_and_confirms_same_pending(tmp_path: Path) -> None:
    bindings = []
    run_calls = []
    confirm_calls = []

    class Repository:
        def upsert_identity(self, **kwargs):
            bindings.append(kwargs)

    class Runtime:
        def run(self, **kwargs):
            run_calls.append(kwargs)
            return {
                "status": "needs_confirmation",
                "message": "请确认创建材料申请。",
                "pending_id": "pending-1",
                "pending_tool_call": {"tool": "nexterp_execute_prepared_operation", "arguments": {"pending_id": "pending-1"}},
                "steps": [],
                "questions": [],
                "candidates": [],
                "tool_results": [],
                "document_links": [],
            }

        def confirm(self, **kwargs):
            confirm_calls.append(kwargs)
            return {
                "status": "completed",
                "message": "已创建材料申请 MAT-MR-1。",
                "steps": [],
                "questions": [],
                "candidates": [],
                "tool_results": [],
                "document_links": [{"doctype": "Material Request", "name": "MAT-MR-1"}],
            }

    service = AgentWorkbenchService.__new__(AgentWorkbenchService)
    service.base_url = "http://localhost:8002"
    service.session_store = RuntimeSessionStore(tmp_path)
    service.capability_repository = Repository()
    service.openclaw_runtime = Runtime()

    request = {
        "user": "mao.xiaoquan@stec-up.local",
        "project_code": "PRJ-HL-13",
        "warehouse": "WH-HL-13",
        "conversation_id": "conversation-a",
        "text": "申请10包水泥",
    }
    prepared = service.run(request)
    completed = service.confirm(request)

    assert prepared["status"] == "needs_confirmation"
    assert bindings[0]["employee_user"] == "mao.xiaoquan@stec-up.local"
    assert "PRJ-HL-13" in bindings[0]["allowed_projects"]
    assert run_calls[0]["conversation_id"] == "conversation-a"
    assert confirm_calls == [{
        "pending_id": "pending-1",
        "user": "mao.xiaoquan@stec-up.local",
        "project_code": "PRJ-HL-13",
        "conversation_id": "conversation-a",
    }]
    assert completed["document_links"][0]["url"] == "#document/Material%20Request/MAT-MR-1"
    history = service.session_history("mao.xiaoquan@stec-up.local", "PRJ-HL-13", "conversation-a")
    assert [turn["result"]["status"] for turn in history["turns"]] == ["needs_confirmation", "completed"]


def test_workbench_async_run_exposes_terminal_result_and_scopes_status(tmp_path: Path) -> None:
    class Repository:
        def upsert_identity(self, **_kwargs):
            return None

    class Runtime:
        def run(self, **_kwargs):
            return {
                "status": "needs_clarification",
                "message": "请选择具体物料。",
                "questions": ["请选择规格。"],
                "candidates": [],
                "document_links": [],
            }

    service = AgentWorkbenchService.__new__(AgentWorkbenchService)
    service.base_url = "http://localhost:8002"
    service.session_store = RuntimeSessionStore(tmp_path)
    service.capability_repository = Repository()
    service.openclaw_runtime = Runtime()

    request = {
        "user": "mao.xiaoquan@stec-up.local",
        "project_code": "PRJ-HL-13",
        "conversation_id": "async-test",
        "text": "帮我找钻头",
    }
    started = service.start_run(request)
    assert started["status"] == "running"
    assert started["stage_label"]

    finished = None
    for _ in range(100):
        finished = service.run_status(started["run_id"], request)
        if finished["status"] != "running":
            break
        time.sleep(0.005)
    assert finished is not None
    assert finished["status"] == "needs_clarification"
    assert finished["result"]["message"] == "请选择具体物料。"
    assert finished["stage_label"] == "小助理需要你补充一点信息。"

    with pytest.raises(PermissionError):
        service.run_status(started["run_id"], {**request, "project_code": "PRJ-NJ-01"})
