from __future__ import annotations

import json

import pytest
import requests

from nexterp_agent.agent_runtime.deepseek_material_request import (
    MATERIAL_REQUEST_TOOL,
    DeepSeekSettings,
    build_material_request_messages,
    call_deepseek_json,
    normalize_material_request_plan,
    parse_json_object,
    validate_material_request_plan,
)


def test_material_request_prompt_restricts_tool_and_includes_context() -> None:
    messages = build_material_request_messages(
        "合流1.3标明天要帆布手套100双",
        context={"company": "STEC (Demo)", "item_candidates": [{"item_code": "SAFE-000005"}]},
    )

    combined = "\n".join(message["content"] for message in messages)

    assert MATERIAL_REQUEST_TOOL in combined
    assert "不能编造 ERPNext 主键" in combined
    assert "SAFE-000005" in combined


def test_validate_material_request_plan_accepts_candidate_tool_call() -> None:
    plan = {
        "status": "needs_confirmation",
        "questions": [],
        "tool_call": {
            "tool": MATERIAL_REQUEST_TOOL,
            "arguments": {
                "material_request_type": "Purchase",
                "company": "STEC (Demo)",
                "schedule_date": "2026-06-18",
                "items": [
                    {
                        "item_code": "SAFE-000005",
                        "qty": 100,
                        "uom": "双",
                        "warehouse": "合流1.3标仓库 - SD",
                        "schedule_date": "2026-06-18",
                    }
                ],
            },
        },
    }

    assert validate_material_request_plan(plan) is plan


def test_validate_material_request_plan_rejects_wrong_tool() -> None:
    plan = {
        "status": "needs_confirmation",
        "tool_call": {"tool": "erpnext.create_document", "arguments": {"items": [{"item_code": "X", "qty": 1}]}},
    }

    with pytest.raises(ValueError, match="may only propose"):
        validate_material_request_plan(plan)


def test_normalize_material_request_plan_overrides_model_guesses_from_runtime_context() -> None:
    plan = {
        "status": "needs_confirmation",
        "questions": [],
        "tool_call": {
            "tool": MATERIAL_REQUEST_TOOL,
            "arguments": {
                "material_request_type": "Purchase",
                "company": "Wrong Company",
                "schedule_date": "2026-06-19",
                "items": [
                    {
                        "item_code": "WRONG-ITEM",
                        "qty": 100,
                        "uom": "个",
                        "warehouse": "错误仓库",
                        "schedule_date": "2026-06-19",
                        "project": "WRONG-PROJECT",
                    }
                ],
            },
        },
        "assumptions": [],
    }
    context = {
        "company": "STEC (Demo)",
        "default_schedule_date": "2026-06-18",
        "item_candidates": [{"item_code": "SAFE-000005", "stock_uom": "双"}],
        "warehouse_candidates": [{"name": "合流1.3标仓库 - SD"}],
        "project_candidates": [{"name": "PROJ-0010"}],
    }

    normalized = normalize_material_request_plan(plan, context=context)
    arguments = normalized["tool_call"]["arguments"]
    item = arguments["items"][0]

    assert arguments["company"] == "STEC (Demo)"
    assert arguments["schedule_date"] == "2026-06-18"
    assert item["item_code"] == "SAFE-000005"
    assert item["uom"] == "双"
    assert item["warehouse"] == "合流1.3标仓库 - SD"
    assert item["project"] == "PROJ-0010"
    assert item["schedule_date"] == "2026-06-18"
    assert normalized["runtime_corrections"]
    assert "Runtime 已用解析上下文覆盖模型输出中的主数据和日期字段。" in normalized["assumptions"]
    assert validate_material_request_plan(normalized) is normalized


def test_validate_material_request_plan_requires_questions_when_unclear() -> None:
    with pytest.raises(ValueError, match="non-empty questions"):
        validate_material_request_plan({"status": "needs_clarification", "questions": []})


def test_parse_json_object_strips_markdown_fence() -> None:
    assert parse_json_object('```json\n{"status":"needs_clarification","questions":["缺少物料"]}\n```') == {
        "status": "needs_clarification",
        "questions": ["缺少物料"],
    }


def test_call_deepseek_json_uses_openai_compatible_endpoint(monkeypatch) -> None:
    captured = {}
    response_payload = {"status": "needs_clarification", "questions": ["请确认物料编码"]}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(response_payload, ensure_ascii=False)}}]}

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("nexterp_agent.agent_runtime.deepseek_material_request.requests.post", fake_post)

    result = call_deepseek_json(
        [{"role": "user", "content": "hello"}],
        settings=DeepSeekSettings(api_key="test-key", base_url="https://api.deepseek.com", model="deepseek-v4-flash"),
    )

    assert result == response_payload
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"]["model"] == "deepseek-v4-flash"
    assert captured["json"]["response_format"] == {"type": "json_object"}


def test_call_deepseek_json_retries_transient_timeout(monkeypatch) -> None:
    calls = 0

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    def fake_post(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise requests.Timeout("read timed out")
        return FakeResponse()

    monkeypatch.setattr("nexterp_agent.agent_runtime.deepseek_material_request.requests.post", fake_post)

    result = call_deepseek_json(
        [{"role": "user", "content": "hello"}],
        settings=DeepSeekSettings(
            api_key="test-key",
            max_retries=1,
            retry_backoff_seconds=0,
        ),
    )

    assert result == {"ok": True}
    assert calls == 2
