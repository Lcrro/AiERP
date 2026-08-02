from __future__ import annotations

import json
from pathlib import Path
import subprocess
import time
from typing import Any, Callable
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[3]


def to_wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    suffix = resolved.as_posix().split(":", 1)[-1]
    return f"/mnt/{drive}{suffix}"


def summarize_existing_result(result: dict[str, Any], *, duration_ms: int) -> dict[str, Any]:
    steps = result.get("steps") if isinstance(result.get("steps"), list) else []
    questions = result.get("questions") if isinstance(result.get("questions"), list) else []
    pending = result.get("pending_tool_call") if isinstance(result.get("pending_tool_call"), dict) else None
    return {
        "runtime": "existing",
        "status": result.get("status") or "unknown",
        "message": result.get("message") or "",
        "duration_ms": duration_ms,
        "questions": questions,
        "question_count": len(questions),
        "candidate_count": len(result.get("candidates") or []),
        "steps": [
            {
                "label": step.get("label"),
                "action": step.get("action"),
                "summary": (step.get("result") or {}).get("summary") if isinstance(step, dict) else None,
            }
            for step in steps if isinstance(step, dict)
        ],
        "tool_summary": {
            "calls": len(steps),
            "tools": [step.get("action") for step in steps if isinstance(step, dict) and step.get("action")],
        },
        "confirmation": pending,
        "document_links": result.get("document_links") or [],
    }


class OpenClawPreviewRunner:
    def __init__(self, root: Path = ROOT, *, runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run) -> None:
        self.root = root
        self.runner = runner

    def run(self, *, text: str, project_label: str, employee_name: str) -> dict[str, Any]:
        token = uuid4().hex
        session_key = f"agent:main:compare-preview:{token}"
        instruction = (
            f"当前工作台项目是“{project_label}”，员工是“{employee_name}”。员工请求：{text}\n"
            "请按照 Nexterp 工作规约按需搜索能力、加载说明并准备操作。"
            "这是 A/B 对比预览：不得调用执行工具，不得写入 ERPNext；信息不足时自然追问。"
        )
        command = [
            "wsl.exe", "--", "bash", to_wsl_path(self.root / "scripts/openclaw/run_nexterp_agent.sh"),
            "--agent", "main", "--session-key", session_key, "--message", instruction,
            "--thinking", "low", "--timeout", "180", "--json",
        ]
        started = time.perf_counter()
        completed = self.runner(command, capture_output=True, timeout=210)
        duration_ms = round((time.perf_counter() - started) * 1000)
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(detail or "OpenClaw preview failed")
        payload = json.loads(completed.stdout.decode("utf-8"))
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
        agent_meta = meta.get("agentMeta") if isinstance(meta.get("agentMeta"), dict) else {}
        session_file = str(agent_meta.get("sessionFile") or "")
        trace = self._extract_trace(session_file) if session_file else {
            "steps": [], "loaded_nodes": [], "questions": [], "confirmation": None, "pending_id": None,
        }
        payloads = result.get("payloads") if isinstance(result.get("payloads"), list) else []
        message = next((str(row.get("text") or "") for row in reversed(payloads) if isinstance(row, dict) and row.get("text")), "")
        tool_summary = meta.get("toolSummary") if isinstance(meta.get("toolSummary"), dict) else {}
        return {
            "runtime": "openclaw_manual",
            "status": payload.get("status") or "unknown",
            "message": message,
            "duration_ms": int(meta.get("durationMs") or duration_ms),
            "model": f"{agent_meta.get('provider', '')}/{agent_meta.get('model', '')}".strip("/"),
            "session_id": agent_meta.get("sessionId"),
            "session_key": session_key,
            "tool_summary": {
                "calls": int(tool_summary.get("calls") or 0),
                "tools": tool_summary.get("tools") or [],
                "failures": int(tool_summary.get("failures") or 0),
            },
            "question_count": len(trace["questions"]),
            **trace,
        }

    def _extract_trace(self, session_file: str) -> dict[str, Any]:
        command = [
            "wsl.exe", "--", "python3",
            to_wsl_path(self.root / "scripts/openclaw/extract_nexterp_trace.py"), session_file,
        ]
        completed = self.runner(command, capture_output=True, timeout=30)
        if completed.returncode != 0:
            return {"steps": [], "loaded_nodes": [], "questions": [], "confirmation": None, "pending_id": None}
        return json.loads(completed.stdout.decode("utf-8"))
