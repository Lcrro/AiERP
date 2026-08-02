from __future__ import annotations

from contextlib import contextmanager
import json
import threading
from typing import Any, Iterator
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from nexterp_agent.capability_service.server import CapabilityAPIHandler, ThreadingHTTPServer


class RecordingService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any, Any]] = []

    def search(self, request: Any, identity: Any) -> dict[str, Any]:
        self.calls.append(("search", request, identity))
        return {"cards": []}

    def load_guides(self, request: Any, identity: Any) -> dict[str, Any]:
        self.calls.append(("load", request, identity))
        return {"guides": []}

    def prepare(self, request: Any, identity: Any) -> dict[str, Any]:
        self.calls.append(("prepare", request, identity))
        return {"status": "needs_input"}

    def execute(self, request: Any, identity: Any) -> dict[str, Any]:
        self.calls.append(("execute", request, identity))
        return {"status": "completed"}

    def operation(self, pending_id: str, identity: Any) -> dict[str, Any]:
        self.calls.append(("operation", pending_id, identity))
        return {"pending_id": pending_id, "status": "pending"}


@contextmanager
def api_server(monkeypatch: Any) -> Iterator[tuple[str, RecordingService]]:
    monkeypatch.setenv("NEXTERP_CAPABILITY_API_TOKEN", "test-service-token")
    service = RecordingService()
    server = ThreadingHTTPServer(("127.0.0.1", 0), CapabilityAPIHandler)
    server.service = service  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", service
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def post_json(url: str, payload: dict[str, Any], *, headers: dict[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urlopen(request, timeout=3) as response:  # noqa: S310 - loopback test server
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def trusted_headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer test-service-token",
        "X-Nexterp-External-Subject": "nexterp-local-owner",
        "X-Nexterp-Agent-Id": "nexterp",
        "X-Nexterp-Session-Key": "agent:nexterp:test-session",
    }


def test_service_token_is_required(monkeypatch: Any) -> None:
    with api_server(monkeypatch) as (base_url, service):
        status, result = post_json(f"{base_url}/api/capabilities/search", {"query": "创建材料申请"})

    assert status == 403
    assert result["error_type"] == "permission_error"
    assert service.calls == []


def test_identity_is_required_from_trusted_headers(monkeypatch: Any) -> None:
    with api_server(monkeypatch) as (base_url, service):
        status, result = post_json(
            f"{base_url}/api/capabilities/search",
            {"query": "创建材料申请"},
            headers={"Authorization": "Bearer test-service-token"},
        )

    assert status == 400
    assert result["error_type"] == "validation_error"
    assert service.calls == []


def test_request_body_cannot_override_employee_identity(monkeypatch: Any) -> None:
    with api_server(monkeypatch) as (base_url, service):
        status, result = post_json(
            f"{base_url}/api/capabilities/search",
            {"query": "创建材料申请", "employee_user": "administrator@example.com"},
            headers=trusted_headers(),
        )

    assert status == 400
    assert result["error_type"] == "validation_error"
    assert service.calls == []


def test_service_receives_identity_from_headers_only(monkeypatch: Any) -> None:
    with api_server(monkeypatch) as (base_url, service):
        status, result = post_json(
            f"{base_url}/api/capabilities/search",
            {"query": "创建材料申请"},
            headers=trusted_headers(),
        )

    assert status == 200
    assert result == {"ok": True, "cards": []}
    _, request, identity = service.calls[0]
    assert request.query == "创建材料申请"
    assert identity.external_subject == "nexterp-local-owner"
    assert identity.agent_id == "nexterp"
    assert identity.session_key == "agent:nexterp:test-session"


def test_execute_endpoint_accepts_only_server_generated_pending_id(monkeypatch: Any) -> None:
    with api_server(monkeypatch) as (base_url, service):
        status, result = post_json(
            f"{base_url}/api/operations/execute",
            {"pending_id": "pending-123", "tool_call": {"tool": "forged"}},
            headers=trusted_headers(),
        )

    assert status == 400
    assert result["error_type"] == "validation_error"
    assert service.calls == []
