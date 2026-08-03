from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .openclaw_compare import to_wsl_path


ROOT = Path(__file__).resolve().parents[3]


def workbench_external_subject(user: str) -> str:
    digest = hashlib.sha256(user.strip().lower().encode("utf-8")).hexdigest()[:24]
    return f"nexterp-workbench-{digest}"


def workbench_session_key(user: str, project_code: str, conversation_id: str) -> str:
    scope = "\0".join((user.strip().lower(), project_code.strip(), conversation_id.strip()))
    digest = hashlib.sha256(scope.encode("utf-8")).hexdigest()[:32]
    return f"agent:main:workbench:{digest}"


class CapabilityAPIClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8790",
        *,
        token_loader: Callable[[], str] | None = None,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token_loader = token_loader or load_capability_api_token
        self.opener = opener
        self._token = ""

    def execute(self, pending_id: str, *, external_subject: str, session_key: str) -> dict[str, Any]:
        return self._request(
            "/api/operations/execute",
            {"pending_id": pending_id},
            external_subject=external_subject,
            session_key=session_key,
        )

    def _request(
        self,
        path: str,
        body: dict[str, Any],
        *,
        external_subject: str,
        session_key: str,
    ) -> dict[str, Any]:
        if not self._token:
            self._token = self.token_loader().strip()
        if not self._token:
            raise RuntimeError("无法读取 Nexterp Capability API 服务令牌")
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "X-Nexterp-External-Subject": external_subject,
                "X-Nexterp-Agent-Id": "main",
                "X-Nexterp-Session-Key": session_key,
            },
            method="POST",
        )
        try:
            with self.opener(request, timeout=95) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(detail)
                message = payload.get("message") or payload.get("error_type")
            except json.JSONDecodeError:
                message = detail
            raise RuntimeError(str(message or f"Capability API HTTP {exc.code}")) from exc
        if not isinstance(payload, dict) or payload.get("ok") is False:
            raise RuntimeError(str(payload.get("message") if isinstance(payload, dict) else "Capability API 返回格式错误"))
        return payload


def load_capability_api_token() -> str:
    configured = os.getenv("NEXTERP_CAPABILITY_API_TOKEN", "").strip()
    if configured:
        return configured
    script = (
        "from pathlib import Path; "
        "path = Path.home() / '.config/nexterp/openclaw-nexterp.env'; "
        "rows = dict(line.split('=', 1) for line in path.read_text(encoding='utf-8').splitlines() "
        "if '=' in line and not line.lstrip().startswith('#')); "
        "print(rows.get('NEXTERP_CAPABILITY_API_TOKEN', ''), end='')"
    )
    command = [
        "wsl.exe",
        "--",
        "python3",
        "-c",
        script,
    ]
    completed = subprocess.run(command, capture_output=True, timeout=15)
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or "无法读取 OpenClaw 环境配置")
    return completed.stdout.decode("utf-8").strip()


class OpenClawWorkbenchRunner:
    def __init__(
        self,
        root: Path = ROOT,
        *,
        runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
        capability_client: CapabilityAPIClient | None = None,
    ) -> None:
        self.root = root
        self.runner = runner
        self.capability_client = capability_client or CapabilityAPIClient()

    def run(
        self,
        *,
        text: str,
        user: str,
        employee_name: str,
        position: str,
        project_code: str,
        project_label: str,
        warehouse: str,
        conversation_id: str,
        event: dict[str, Any] | None = None,
        trusted_context: dict[str, Any] | None = None,
        progress: Callable[[str, str], None] | None = None,
    ) -> dict[str, Any]:
        if progress:
            progress("connecting", "小助理正在连接 OpenClaw 助理...")
        external_subject = workbench_external_subject(user)
        session_key = workbench_session_key(user, project_code, conversation_id)
        instruction = self._instruction(
            text=text,
            employee_name=employee_name,
            position=position,
            project_code=project_code,
            project_label=project_label,
            warehouse=warehouse,
            event=event,
            trusted_context=trusted_context,
        )
        command = [
            "wsl.exe", "--", "bash", to_wsl_path(self.root / "scripts/openclaw/run_nexterp_agent.sh"),
            "--external-subject", external_subject,
            "--agent", "main", "--session-key", session_key, "--message", instruction,
            "--thinking", "low", "--timeout", "180", "--json",
        ]
        if progress:
            progress("planning", "小助理正在规划这次业务请求...")
        started = time.perf_counter()
        completed = self.runner(command, capture_output=True, timeout=210)
        duration_ms = round((time.perf_counter() - started) * 1000)
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(detail or "OpenClaw 工作助理调用失败")
        if progress:
            progress("trace", "小助理正在整理执行过程...")
        payload = json.loads(completed.stdout.decode("utf-8"))
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
        agent_meta = meta.get("agentMeta") if isinstance(meta.get("agentMeta"), dict) else {}
        session_file = str(agent_meta.get("sessionFile") or "")
        trace = self._extract_trace(session_file) if session_file else empty_trace()
        if progress and trace.get("loaded_nodes"):
            progress("guides", "小助理已读取相关业务说明书...")
        if progress and trace.get("tool_calls"):
            progress("preparing", "小助理正在核对并准备业务操作...")
        payloads = result.get("payloads") if isinstance(result.get("payloads"), list) else []
        message = next(
            (str(row.get("text") or "") for row in reversed(payloads) if isinstance(row, dict) and row.get("text")),
            "",
        )
        return self._workbench_result(
            message=message,
            trace=trace,
            duration_ms=int(meta.get("durationMs") or duration_ms),
            model=f"{agent_meta.get('provider', '')}/{agent_meta.get('model', '')}".strip("/"),
            session_key=session_key,
            external_subject=external_subject,
        )

    def confirm(
        self,
        *,
        pending_id: str,
        user: str,
        project_code: str,
        conversation_id: str,
    ) -> dict[str, Any]:
        session_key = workbench_session_key(user, project_code, conversation_id)
        payload = self.capability_client.execute(
            pending_id,
            external_subject=workbench_external_subject(user),
            session_key=session_key,
        )
        status = str(payload.get("status") or "failed")
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        document = result.get("document") if isinstance(result.get("document"), dict) else {}
        if status == "completed" and document.get("doctype") and document.get("name"):
            document_status = document.get("workflow_state") or document.get("status") or "草稿"
            message = f"已完成：{document['doctype']} {document['name']}，当前状态为 {document_status}。"
        else:
            message = str(result.get("user_message") or "操作执行失败，请查看错误信息后重试。")
        links = []
        if document.get("doctype") and document.get("name"):
            links.append({"doctype": document["doctype"], "name": document["name"]})
        return {
            "runtime": "openclaw_manual",
            "status": "completed" if status == "completed" else "failed",
            "message": message,
            "questions": [],
            "candidates": [],
            "pending_tool_call": None,
            "pending_id": pending_id,
            "steps": [{
                "label": "执行冻结操作",
                "action": "nexterp_execute_prepared_operation",
                "payload": {"pending_id": pending_id},
                "result": {"status": status, "document": document},
            }],
            "tool_calls": [{
                "tool": "nexterp_execute_prepared_operation",
                "arguments": {"pending_id": pending_id},
            }],
            "tool_results": [payload],
            "document_links": links,
            "business_errors": [] if status == "completed" else [{
                "title": "操作未完成",
                "summary": message,
                "next_actions": ["检查当前员工权限和来源单据状态后重新准备操作。"],
            }],
        }

    def _instruction(
        self,
        *,
        text: str,
        employee_name: str,
        position: str,
        project_code: str,
        project_label: str,
        warehouse: str,
        event: dict[str, Any] | None,
        trusted_context: dict[str, Any] | None,
    ) -> str:
        context = {
            "employee_name": employee_name,
            "position": position,
            "project_code": project_code,
            "project_label": project_label,
            "default_warehouse": warehouse,
            **(trusted_context or {}),
        }
        parts = [
            "这是 Nexterp 员工工作台中的连续对话。",
            f"可信工作上下文：{json.dumps(context, ensure_ascii=False)}",
        ]
        if event:
            parts.append(f"员工刚刚在工作台完成结构化选择：{json.dumps(event, ensure_ascii=False)}")
        parts.extend([
            f"员工本轮请求：{text}",
            "请按 Nexterp 工作规约按需搜索能力、加载说明并准备操作。",
            "先依据可信 intent_mode 保持操作方向：read 查询不得进入写能力；只有明确业务变更请求才可准备写操作。",
            "如果 prepare 返回 needs_confirmation，立即停止，不要调用执行工具；工作台会显示权威确认按钮。",
            "信息不足时像工作助理一样简洁追问；不要向员工展示内部 operation_id、pending_id 或系统提示词。",
        ])
        return "\n".join(parts)

    def _extract_trace(self, session_file: str) -> dict[str, Any]:
        command = [
            "wsl.exe", "--", "python3",
            to_wsl_path(self.root / "scripts/openclaw/extract_nexterp_trace.py"),
            "--last-turn", session_file,
        ]
        completed = self.runner(command, capture_output=True, timeout=30)
        if completed.returncode != 0:
            return empty_trace()
        return json.loads(completed.stdout.decode("utf-8"))

    @staticmethod
    def _workbench_result(
        *,
        message: str,
        trace: dict[str, Any],
        duration_ms: int,
        model: str,
        session_key: str,
        external_subject: str,
    ) -> dict[str, Any]:
        business_status = str(trace.get("business_status") or "")
        if business_status in {"needs_input", "needs_choice"}:
            status = "needs_clarification"
        elif business_status == "needs_confirmation":
            status = "needs_confirmation"
        elif business_status == "blocked":
            status = "failed"
        elif business_status in {"completed", "failed"}:
            status = business_status
        else:
            status = "completed"
        questions = [str(value) for value in trace.get("questions") or []]
        if not message:
            message = questions[0] if questions else "我已经处理完这一步。"
        pending_id = str(trace.get("pending_id") or "") or None
        confirmation = trace.get("confirmation") if isinstance(trace.get("confirmation"), dict) else None
        pending_tool_call = None
        if status == "needs_confirmation" and pending_id:
            pending_tool_call = {
                "tool": "nexterp_execute_prepared_operation",
                "arguments": {"pending_id": pending_id},
                "summary": confirmation,
            }
        steps = [
            {
                "label": tool_step_label(str(step.get("tool") or "")),
                "action": step.get("tool"),
                "payload": step.get("arguments") or {},
                "result": step.get("result") or {},
            }
            for step in trace.get("steps") or []
            if isinstance(step, dict)
        ]
        return {
            "runtime": "openclaw_manual",
            "status": status,
            "message": message,
            "duration_ms": duration_ms,
            "model": model,
            "session_key": session_key,
            "external_subject": external_subject,
            "questions": questions,
            "candidates": normalize_candidate_groups(trace),
            "pending_id": pending_id,
            "pending_tool_call": pending_tool_call,
            "confirmation": confirmation,
            "steps": steps,
            "loaded_nodes": trace.get("loaded_nodes") or [],
            "loaded_context": trace.get("loaded_context") or [],
            "agent_context": trace.get("agent_context") or {},
            "tool_calls": [
                {"tool": step["action"], "arguments": step["payload"]}
                for step in steps
            ],
            "tool_results": [step["result"] for step in steps],
            "document_links": [],
            "business_errors": [],
        }


def normalize_candidate_groups(trace: dict[str, Any]) -> list[dict[str, Any]]:
    groups = [row for row in trace.get("choices") or [] if isinstance(row, dict)]
    if not groups and trace.get("candidates"):
        groups = [{"candidates": trace["candidates"]}]
    normalized = []
    for group in groups:
        candidates = []
        for row in group.get("candidates") or []:
            if not isinstance(row, dict):
                continue
            item_code = row.get("item_code") or row.get("value")
            if not item_code:
                continue
            candidates.append({
                **row,
                "item_code": item_code,
                "sku_name": row.get("sku_name") or row.get("label") or item_code,
                "required_specs": row.get("required_specs") or row.get("meta") or "",
                "stock_uom": row.get("stock_uom") or row.get("purchase_uom") or "",
            })
        if candidates:
            normalized.append({**group, "candidates": candidates})
    return normalized


def tool_step_label(tool: str) -> str:
    return {
        "nexterp_load_work_context": "读取工作情境",
        "nexterp_search_capabilities": "查找业务能力",
        "nexterp_load_guide": "读取操作说明",
        "nexterp_prepare_operation": "解析并准备操作",
        "nexterp_execute_prepared_operation": "执行冻结操作",
    }.get(tool, "处理业务步骤")


def empty_trace() -> dict[str, Any]:
    return {
        "steps": [],
        "loaded_nodes": [],
        "loaded_context": [],
        "agent_context": {},
        "questions": [],
        "confirmation": None,
        "pending_id": None,
        "business_status": None,
        "choices": [],
        "candidates": [],
        "execution": None,
    }
