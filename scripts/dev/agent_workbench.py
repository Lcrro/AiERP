from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.parse import parse_qs, quote, urlparse


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.agent_runtime.civil_runtime import CivilAgentRuntime
from nexterp_agent.agent_runtime.credentials import load_user_credentials
from nexterp_agent.erpnext.client import ERPNextClient
from nexterp_agent.master_data import MasterDataRelease


HTML_PATH = ROOT / "tools" / "agent_workbench.html"
DOCTYPE_ROUTES = {
    "Material Request": "material-request",
    "Request for Quotation": "request-for-quotation",
    "Purchase Order": "purchase-order",
    "Purchase Receipt": "purchase-receipt",
    "Purchase Invoice": "purchase-invoice",
    "Stock Entry": "stock-entry",
    "Project": "project",
    "ToDo": "todo",
}
DOCUMENT_MODULES = (
    ("buying", "采购", (
        ("Material Request", "材料申请", "Material Request Item"),
        ("Request for Quotation", "询价单", None),
        ("Purchase Order", "采购订单", "Purchase Order Item"),
        ("Purchase Receipt", "采购收货", "Purchase Receipt Item"),
    )),
    ("stock", "库存", (
        ("Stock Entry", "库存移动", "Stock Entry Detail"),
    )),
    ("accounting", "财务", (
        ("Purchase Invoice", "采购发票", "Purchase Invoice Item"),
        ("Payment Entry", "付款单", None),
    )),
    ("projects", "项目协作", (
        ("Task", "任务", "Task"),
        ("ToDo", "待办", None),
    )),
)
DOCTYPE_ROUTES.update({"Payment Entry": "payment-entry", "Task": "task"})


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def json_response(handler: BaseHTTPRequestHandler, payload: dict[str, Any], status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def html_response(handler: BaseHTTPRequestHandler, body: str) -> None:
    data = body.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    return json.loads(handler.rfile.read(length).decode("utf-8")) if length else {}


def employee_catalog() -> list[dict[str, str]]:
    release = MasterDataRelease()
    roles = release.roles
    return [
        {
            "employee_code": row["employee_code"],
            "employee_name": row["employee_name"],
            "position": row["position"],
            "user_email": row["user_email"],
            "profile": roles[row["role_code"]]["default_agent_profile"],
            "default_project_code": row.get("default_project_code", ""),
            "default_warehouse_code": row.get("default_warehouse_code", ""),
        }
        for row in release.table("employees.tsv", include_candidates=False)
        if row.get("user_email")
    ]


def project_catalog() -> list[dict[str, Any]]:
    release = MasterDataRelease()
    employees = {row["employee_code"]: row for row in employee_catalog()}
    assignments = release.table("employee_assignments.tsv", include_candidates=False)
    organization_people = {
        row["employee_code"] for row in assignments
        if row.get("scope_type") == "organization" and row.get("scope_code") == "DEPT-UP" and row.get("is_active") == "1"
    }
    project_roles: dict[str, list[dict[str, str]]] = {}
    for project_code, project in release.projects.items():
        people: dict[str, dict[str, str]] = {}
        for row in assignments:
            employee_code = row.get("employee_code", "")
            if employee_code not in employees or row.get("is_active") != "1":
                continue
            if employee_code in organization_people or row.get("scope_code") == project_code:
                person = dict(employees[employee_code])
                person["project_position"] = row.get("position", person["position"]) if row.get("scope_code") == project_code else person["position"]
                people[employee_code] = person
        project_roles[project_code] = sorted(people.values(), key=lambda row: (row["position"] != "项目经理", row["employee_name"]))
    return [
        {
            "project_code": code,
            "project_name": row["project_name"],
            "project_short_name": row["project_short_name"],
            "operating_status": row.get("project_operating_status", ""),
            "warehouse_code": row.get("default_warehouse_code", ""),
            "employees": project_roles[code],
        }
        for code, row in release.projects.items()
    ]


def result_document_links(result: dict[str, Any], erpnext_base_url: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    payloads = result.get("tool_results") or ([result.get("tool_result")] if result.get("tool_result") else [])
    seen: set[tuple[str, str]] = set()
    for payload in payloads:
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            continue
        doctype = str(data.get("doctype") or "")
        name = str(data.get("name") or "")
        route = DOCTYPE_ROUTES.get(doctype)
        if not route or not name or (doctype, name) in seen:
            continue
        seen.add((doctype, name))
        links.append(
            {
                "doctype": doctype,
                "name": name,
                "url": f"{erpnext_base_url.rstrip('/')}/app/{route}/{quote(name, safe='')}",
            }
        )
    return links


class AgentWorkbenchService:
    def __init__(self, profile: str = "civil") -> None:
        self.profile = profile
        prefix = f"NEXTERP_{profile.upper()}_"
        self.base_url = os.environ[prefix + "BASE_URL"]
        self.host_header = os.getenv(prefix + "HOST_HEADER")

    def runtime(self) -> CivilAgentRuntime:
        def client_factory(user: str) -> ERPNextClient:
            credentials = load_user_credentials(user)
            return ERPNextClient(
                self.base_url,
                credentials["api_key"],
                credentials["api_secret"],
                host_header=self.host_header,
                timeout=90,
            )

        return CivilAgentRuntime(client_factory=client_factory)

    def client(self, user: str) -> ERPNextClient:
        credentials = load_user_credentials(user)
        return ERPNextClient(self.base_url, credentials["api_key"], credentials["api_secret"], host_header=self.host_header, timeout=90)

    def documents(self, user: str, project: str = "") -> dict[str, Any]:
        if not user:
            raise ValueError("user 必填")
        client = self.client(user)
        modules: list[dict[str, Any]] = []
        for module_code, module_label, doctypes in DOCUMENT_MODULES:
            groups: list[dict[str, Any]] = []
            for doctype, label, project_child in doctypes:
                filters: dict[str, Any] = {}
                if project and project_child:
                    child_result = client.search_documents(
                        project_child,
                        filters={"project": project},
                        fields=["name", "parent"] if project_child != "Task" else ["name"],
                        limit=100,
                    )
                    child_rows = child_result.data if child_result.ok and isinstance(child_result.data, list) else []
                    names = [row.get("name") if project_child == "Task" else row.get("parent") for row in child_rows]
                    names = list(dict.fromkeys(name for name in names if name))
                    if not names:
                        groups.append({"doctype": doctype, "label": label, "documents": []})
                        continue
                    filters = {"name": ["in", names]}
                result = client.search_documents(
                    doctype,
                    filters=filters,
                    fields=["name", "owner", "modified", "docstatus"],
                    limit=30,
                    order_by="modified desc",
                )
                rows = result.data if result.ok and isinstance(result.data, list) else []
                groups.append({
                    "doctype": doctype,
                    "label": label,
                    "error": None if result.ok else result.user_message or result.error,
                    "documents": [
                        {
                            **row,
                            "url": f"{self.base_url.rstrip('/')}/app/{DOCTYPE_ROUTES[doctype]}/{quote(str(row.get('name', '')), safe='')}",
                        }
                        for row in rows
                    ],
                })
            modules.append({"code": module_code, "label": module_label, "groups": groups})
        return {"project": project, "modules": modules}

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        user = str(payload.get("user") or "").strip()
        text = str(payload.get("text") or "").strip()
        if not user or not text:
            raise ValueError("user 和 text 必填")
        execute = bool(payload.get("execute"))
        request_id = str(payload.get("request_id") or "").strip() or None
        result = self.runtime().run_once(text, user=user, execute=execute, request_id=request_id)
        response = result.to_dict()
        response["execute"] = execute
        response["document_links"] = result_document_links(response, self.base_url)
        return response


class AgentWorkbenchHandler(BaseHTTPRequestHandler):
    server_version = "NexterpAgentWorkbench/0.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            html_response(self, HTML_PATH.read_text(encoding="utf-8"))
            return
        if parsed.path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        if parsed.path == "/api/employees":
            json_response(self, {"ok": True, "employees": employee_catalog()})
            return
        if parsed.path == "/api/catalog":
            json_response(self, {"ok": True, "projects": project_catalog(), "employees": employee_catalog()})
            return
        if parsed.path == "/api/documents":
            query = parse_qs(parsed.query)
            payload = self.server.service.documents(  # type: ignore[attr-defined]
                (query.get("user") or [""])[0],
                (query.get("project") or [""])[0],
            )
            json_response(self, {"ok": True, **payload})
            return
        if parsed.path == "/api/health":
            json_response(self, {"ok": True, "service": "agent-workbench", "profile": self.server.service.profile})  # type: ignore[attr-defined]
            return
        json_response(self, {"ok": False, "error": "not_found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.path != "/api/agent":
                json_response(self, {"ok": False, "error": "not_found"}, 404)
                return
            response = self.server.service.run(read_json(self))  # type: ignore[attr-defined]
            json_response(self, {"ok": response.get("status") != "failed", "result": response})
        except (ValueError, json.JSONDecodeError) as exc:
            json_response(self, {"ok": False, "error": str(exc)}, 400)
        except Exception as exc:  # pragma: no cover - local service boundary
            json_response(self, {"ok": False, "error": str(exc)}, 500)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("[agent-workbench] " + format % args + "\n")


def build_server(host: str, port: int, profile: str) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), AgentWorkbenchHandler)
    server.service = AgentWorkbenchService(profile)  # type: ignore[attr-defined]
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the employee natural-language Agent workbench.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--profile", default="civil")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()
    load_dotenv(args.env_file)
    if not HTML_PATH.exists():
        raise FileNotFoundError(HTML_PATH)
    server = build_server(args.host, args.port, args.profile)
    print(f"Employee Agent workbench: http://{args.host}:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
