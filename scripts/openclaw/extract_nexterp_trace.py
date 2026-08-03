#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


ALLOWED_TOOLS = {
    "nexterp_load_work_context",
    "nexterp_search_capabilities",
    "nexterp_load_guide",
    "nexterp_prepare_operation",
    "nexterp_execute_prepared_operation",
}


def parse_json_text(value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def compact_result(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if tool_name == "nexterp_load_work_context":
        context = payload.get("agent_context") if isinstance(payload.get("agent_context"), dict) else {}
        identity = context.get("identity") if isinstance(context.get("identity"), dict) else {}
        workplace = context.get("workplace") if isinstance(context.get("workplace"), dict) else {}
        role_context = payload.get("role_context") if isinstance(payload.get("role_context"), dict) else {}
        role_profile = role_context.get("profile") if isinstance(role_context.get("profile"), dict) else {}
        responsibilities = role_context.get("responsibilities") if isinstance(role_context.get("responsibilities"), list) else []
        return {
            "status": payload.get("status"),
            "loaded_topics": payload.get("loaded_topics") or [],
            "identity": {"employee_name": identity.get("employee_name"), "role_code": identity.get("role_code"),
                         "position": identity.get("project_position") or identity.get("position")},
            "workplace": {"project_code": workplace.get("project_code"),
                          "project_short_name": workplace.get("project_short_name"),
                          "warehouse_name": workplace.get("warehouse_name")},
            "role_profile": {
                "role_name": role_profile.get("role_name"),
                "mission": role_profile.get("mission"),
                "boundaries": role_profile.get("boundaries"),
            },
            "responsibilities": [
                {"label": row.get("label"), "summary": row.get("summary"), "type": row.get("type")}
                for row in responsibilities[:5] if isinstance(row, dict)
            ],
        }
    if tool_name == "nexterp_search_capabilities":
        cards = payload.get("cards") if isinstance(payload.get("cards"), list) else []
        return {
            "status": payload.get("status"),
            "nodes": [
                {"node_id": row.get("node_id"), "label": row.get("label"), "node_type": row.get("node_type")}
                for row in cards if isinstance(row, dict)
            ],
        }
    if tool_name == "nexterp_load_guide":
        guides = payload.get("guides") if isinstance(payload.get("guides"), list) else []
        return {
            "status": payload.get("status"),
            "nodes": [
                {"node_id": row.get("node_id"), "label": row.get("label"), "node_type": row.get("node_type")}
                for row in guides if isinstance(row, dict)
            ],
        }
    if tool_name == "nexterp_prepare_operation":
        choices = payload.get("choices") if isinstance(payload.get("choices"), list) else []
        candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
        questions = payload.get("questions") if isinstance(payload.get("questions"), list) else []
        return {
            "status": payload.get("status"),
            "pending_id": payload.get("pending_id"),
            "summary": payload.get("summary"),
            "questions": questions,
            "choices": choices,
            "candidates": candidates,
        }
    if tool_name == "nexterp_execute_prepared_operation":
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        document = result.get("document") if isinstance(result.get("document"), dict) else {}
        return {
            "status": payload.get("status"),
            "document": {"doctype": document.get("doctype"), "name": document.get("name"), "status": document.get("status")},
        }
    return {}


def extract(path: Path, *, last_turn_only: bool = False) -> dict[str, Any]:
    calls: dict[str, dict[str, Any]] = {}
    ordered_ids: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        message = record.get("message") if isinstance(record.get("message"), dict) else {}
        role = message.get("role")
        content = message.get("content") if isinstance(message.get("content"), list) else []
        if role == "user" and last_turn_only:
            calls.clear()
            ordered_ids.clear()
        elif role == "assistant":
            for item in content:
                if not isinstance(item, dict) or item.get("type") != "toolCall":
                    continue
                name = str(item.get("name") or "")
                call_id = str(item.get("id") or "")
                if name not in ALLOWED_TOOLS or not call_id:
                    continue
                calls[call_id] = {"tool": name, "arguments": item.get("arguments") or {}, "result": {}}
                ordered_ids.append(call_id)
        elif role == "toolResult":
            call_id = str(message.get("toolCallId") or message.get("tool_call_id") or "")
            if call_id not in calls:
                continue
            text = next((item.get("text") for item in content if isinstance(item, dict) and item.get("type") == "text"), "")
            calls[call_id]["result"] = compact_result(calls[call_id]["tool"], parse_json_text(text))

    steps = [calls[call_id] for call_id in ordered_ids]
    loaded_nodes: list[dict[str, Any]] = []
    loaded_context: list[str] = []
    agent_context: dict[str, Any] = {}
    questions: list[str] = []
    confirmation: dict[str, Any] | None = None
    pending_id: str | None = None
    business_status: str | None = None
    choices: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    execution: dict[str, Any] | None = None
    for step in steps:
        result = step["result"]
        if step["tool"] == "nexterp_load_work_context":
            loaded_context.extend(str(topic) for topic in result.get("loaded_topics") or [])
            agent_context = {
                "identity": result.get("identity") or {},
                "workplace": result.get("workplace") or {},
                "role_profile": result.get("role_profile") or {},
                "responsibilities": result.get("responsibilities") or [],
            }
        if step["tool"] in {"nexterp_search_capabilities", "nexterp_load_guide"}:
            for node in result.get("nodes") or []:
                if node not in loaded_nodes:
                    loaded_nodes.append(node)
        questions.extend(str(question) for question in result.get("questions") or [])
        if step["tool"] == "nexterp_prepare_operation":
            business_status = str(result.get("status") or "") or business_status
            choices = [row for row in result.get("choices") or [] if isinstance(row, dict)]
            candidates = [row for row in result.get("candidates") or [] if isinstance(row, dict)]
        elif step["tool"] == "nexterp_execute_prepared_operation":
            business_status = str(result.get("status") or "") or business_status
            execution = result
        if result.get("summary"):
            confirmation = result["summary"]
        if result.get("pending_id"):
            pending_id = str(result["pending_id"])
    return {
        "steps": steps,
        "loaded_nodes": loaded_nodes,
        "loaded_context": list(dict.fromkeys(loaded_context)),
        "agent_context": agent_context,
        "questions": questions,
        "confirmation": confirmation,
        "pending_id": pending_id,
        "business_status": business_status,
        "choices": choices,
        "candidates": candidates,
        "execution": execution,
    }


def main() -> int:
    args = sys.argv[1:]
    last_turn_only = "--last-turn" in args
    args = [arg for arg in args if arg != "--last-turn"]
    if len(args) != 1:
        raise SystemExit("usage: extract_nexterp_trace.py [--last-turn] SESSION_JSONL")
    path = Path(args[0]).expanduser().resolve()
    expected = (Path.home() / ".openclaw-nexterp" / "agents").resolve()
    if expected not in path.parents or path.suffix != ".jsonl":
        raise PermissionError("session path is outside the isolated Nexterp profile")
    print(json.dumps(extract(path, last_turn_only=last_turn_only), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
