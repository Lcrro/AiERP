#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


ALLOWED_TOOLS = {
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
        questions = payload.get("questions") if isinstance(payload.get("questions"), list) else []
        return {
            "status": payload.get("status"),
            "pending_id": payload.get("pending_id"),
            "summary": payload.get("summary"),
            "questions": questions,
            "choice_groups": len(choices),
        }
    if tool_name == "nexterp_execute_prepared_operation":
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        document = result.get("document") if isinstance(result.get("document"), dict) else {}
        return {
            "status": payload.get("status"),
            "document": {"doctype": document.get("doctype"), "name": document.get("name"), "status": document.get("status")},
        }
    return {}


def extract(path: Path) -> dict[str, Any]:
    calls: dict[str, dict[str, Any]] = {}
    ordered_ids: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        message = record.get("message") if isinstance(record.get("message"), dict) else {}
        role = message.get("role")
        content = message.get("content") if isinstance(message.get("content"), list) else []
        if role == "assistant":
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
    questions: list[str] = []
    confirmation: dict[str, Any] | None = None
    pending_id: str | None = None
    for step in steps:
        result = step["result"]
        if step["tool"] in {"nexterp_search_capabilities", "nexterp_load_guide"}:
            for node in result.get("nodes") or []:
                if node not in loaded_nodes:
                    loaded_nodes.append(node)
        questions.extend(str(question) for question in result.get("questions") or [])
        if result.get("summary"):
            confirmation = result["summary"]
        if result.get("pending_id"):
            pending_id = str(result["pending_id"])
    return {
        "steps": steps,
        "loaded_nodes": loaded_nodes,
        "questions": questions,
        "confirmation": confirmation,
        "pending_id": pending_id,
    }


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: extract_nexterp_trace.py SESSION_JSONL")
    path = Path(sys.argv[1]).expanduser().resolve()
    expected = (Path.home() / ".openclaw-nexterp" / "agents").resolve()
    if expected not in path.parents or path.suffix != ".jsonl":
        raise PermissionError("session path is outside the isolated Nexterp profile")
    print(json.dumps(extract(path), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
