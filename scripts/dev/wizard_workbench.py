from __future__ import annotations

import argparse
import json
import subprocess
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.erpnext import ERPNextAdapter, ERPNextClient, ToolCall, ToolResult
from nexterp_agent.erpnext.config import load_erpnext_settings
from nexterp_agent.scenarios.wizard_workbench import grouped_wizard_catalog

HTML_PATH = ROOT / "tools" / "wizard_of_oz_workbench.html"
SEED_SCRIPT = ROOT / "scripts" / "seed_civil_company_scenario.py"
DEFAULT_SETUP_REPORT = ROOT / "data" / "scenario" / "wizard_setup_report.json"
READ_ONLY_RISK_LEVELS = {"L0", "L1"}


def _json_response(handler: BaseHTTPRequestHandler, payload: dict[str, Any], status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _text_response(handler: BaseHTTPRequestHandler, body: str, status: int = 200, content_type: str = "text/html") -> None:
    data = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", f"{content_type}; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _read_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    if not length:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    if not raw.strip():
        return {}
    return json.loads(raw)


def execute_toolcall(payload: dict[str, Any], default_profile: str) -> dict[str, Any]:
    started = perf_counter()
    profile = payload.get("profile") or default_profile
    allow_write = bool(payload.get("allow_write"))
    tool_call = ToolCall.from_dict(
        {
            "tool": payload["tool"],
            "arguments": payload.get("arguments") or {},
            "reason": payload.get("reason"),
            "user_context": payload.get("user_context") or {},
        }
    )

    if tool_call.risk_level not in READ_ONLY_RISK_LEVELS and not allow_write:
        blocked = ToolResult(
            ok=False,
            error="Write or high-risk ToolCall blocked by Wizard workbench safe mode.",
            error_type="permission_error",
            user_message="当前处于安全预览模式：这个 ToolCall 会写入或改变 ERPNext。勾选“允许写入 ToolCall”后才会真正执行。",
            data={"blocked": True, "risk_level": tool_call.risk_level},
        ).with_call(tool_call, duration_ms=int((perf_counter() - started) * 1000))
        return {"ok": False, "blocked": True, "profile": profile, "tool_call": tool_call.to_dict(), "result": blocked.to_dict()}

    try:
        settings = load_erpnext_settings(profile)
        client = ERPNextClient(
            settings.base_url,
            settings.api_key,
            settings.api_secret,
            host_header=settings.host_header,
            timeout=60,
        )
        result = ERPNextAdapter(client).execute(tool_call)
        return {"ok": result.ok, "profile": profile, "tool_call": tool_call.to_dict(), "result": result.to_dict()}
    except Exception as exc:  # pragma: no cover - exercised by local misconfiguration.
        failed = ToolResult(
            ok=False,
            error=str(exc),
            error_type="workbench_error",
            user_message="Wizard 工作台执行失败，请检查本地 ERPNext 连接配置和服务状态。",
        ).with_call(tool_call, duration_ms=int((perf_counter() - started) * 1000))
        return {"ok": False, "profile": profile, "tool_call": tool_call.to_dict(), "result": failed.to_dict()}


def run_setup(payload: dict[str, Any], default_profile: str) -> dict[str, Any]:
    profile = payload.get("profile") or default_profile
    report_path = Path(payload.get("report") or DEFAULT_SETUP_REPORT)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    command = [
        sys.executable,
        str(SEED_SCRIPT),
        "--profile",
        profile,
        "--report",
        str(report_path),
    ]
    if payload.get("apply"):
        command.append("--apply")
    if payload.get("skip_stock"):
        command.append("--skip-stock")

    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=300)
    report: dict[str, Any] | None = None
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report = None
    return {
        "ok": completed.returncode == 0,
        "mode": "apply" if payload.get("apply") else "dry_run",
        "profile": profile,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "report_path": str(report_path),
        "report": report,
    }


class WizardWorkbenchHandler(BaseHTTPRequestHandler):
    server_version = "NexterpWizardWorkbench/0.1"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API.
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/tools/wizard_of_oz_workbench.html")
            self.end_headers()
            return
        if parsed.path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        if parsed.path == "/tools/wizard_of_oz_workbench.html":
            _text_response(self, HTML_PATH.read_text(encoding="utf-8"))
            return
        if parsed.path == "/api/catalog":
            query = parse_qs(parsed.query)
            profile = query.get("profile", [self.server.default_profile])[0]  # type: ignore[attr-defined]
            catalog = grouped_wizard_catalog()
            catalog["default_profile"] = profile
            _json_response(self, {"ok": True, "catalog": catalog})
            return
        _json_response(self, {"ok": False, "error": "not_found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API.
        try:
            payload = _read_body(self)
            if self.path == "/api/execute":
                _json_response(self, execute_toolcall(payload, self.server.default_profile))  # type: ignore[attr-defined]
                return
            if self.path == "/api/setup":
                _json_response(self, run_setup(payload, self.server.default_profile))  # type: ignore[attr-defined]
                return
            _json_response(self, {"ok": False, "error": "not_found"}, status=404)
        except json.JSONDecodeError as exc:
            _json_response(self, {"ok": False, "error": f"invalid_json: {exc}"}, status=400)
        except Exception as exc:  # pragma: no cover - defensive server boundary.
            _json_response(self, {"ok": False, "error": str(exc)}, status=500)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("[wizard] " + format % args + "\n")


def build_server(host: str, port: int, profile: str) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), WizardWorkbenchHandler)
    server.default_profile = profile  # type: ignore[attr-defined]
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Wizard of Oz ToolCall workbench.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--profile", default="local")
    args = parser.parse_args()

    if not HTML_PATH.exists():
        raise FileNotFoundError(f"Missing workbench HTML: {HTML_PATH}")

    server = build_server(args.host, args.port, args.profile)
    url = f"http://{args.host}:{args.port}/"
    print(f"Wizard of Oz ToolCall workbench: {url}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Wizard of Oz ToolCall workbench.", flush=True)
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
