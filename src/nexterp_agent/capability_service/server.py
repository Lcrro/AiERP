from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from typing import Any
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv
from pydantic import ValidationError

from .catalog import CapabilityCatalogRepository
from .context_models import WorkContextLoadRequest
from .models import (
    CapabilitySearchRequest,
    ExecuteOperationRequest,
    GuideLoadRequest,
    PrepareOperationRequest,
    RequestIdentity,
)
from .service import CapabilityManualService


def read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if length <= 0:
        return {}
    payload = json.loads(handler.rfile.read(length).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload


def respond(handler: BaseHTTPRequestHandler, payload: dict[str, Any], status: int = 200) -> None:
    data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


class CapabilityAPIHandler(BaseHTTPRequestHandler):
    server_version = "NexterpCapabilityAPI/0.6"

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._authorize()
            parsed = urlparse(self.path)
            if parsed.path == "/api/health":
                respond(self, {"ok": True, "service": "nexterp-capability-api", "version": "0.6"})
                return
            prefix = "/api/operations/"
            if parsed.path.startswith(prefix):
                pending_id = unquote(parsed.path.removeprefix(prefix))
                result = self.server.service.operation(pending_id, self._identity())  # type: ignore[attr-defined]
                respond(self, {"ok": True, **result})
                return
            respond(self, {"ok": False, "error": "not_found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._error(exc)

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._authorize()
            payload = read_json(self)
            identity = self._identity()
            service = self.server.service  # type: ignore[attr-defined]
            if self.path == "/api/capabilities/search":
                result = service.search(CapabilitySearchRequest.model_validate(payload), identity)
            elif self.path == "/api/context/load":
                result = service.load_context(WorkContextLoadRequest.model_validate(payload), identity)
            elif self.path == "/api/guides/load":
                result = service.load_guides(GuideLoadRequest.model_validate(payload), identity)
            elif self.path == "/api/operations/prepare":
                result = service.prepare(PrepareOperationRequest.model_validate(payload), identity)
            elif self.path == "/api/operations/execute":
                result = service.execute(ExecuteOperationRequest.model_validate(payload), identity)
            else:
                respond(self, {"ok": False, "error": "not_found"}, HTTPStatus.NOT_FOUND)
                return
            respond(self, {"ok": True, **result})
        except Exception as exc:
            self._error(exc)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _authorize(self) -> None:
        expected = os.environ.get("NEXTERP_CAPABILITY_API_TOKEN", "")
        if not expected:
            raise RuntimeError("NEXTERP_CAPABILITY_API_TOKEN is not configured")
        if self.headers.get("Authorization", "") != f"Bearer {expected}":
            raise PermissionError("Invalid capability service token")

    def _identity(self) -> RequestIdentity:
        return RequestIdentity(
            external_subject=self.headers.get("X-Nexterp-External-Subject", ""),
            agent_id=self.headers.get("X-Nexterp-Agent-Id", ""),
            session_key=self.headers.get("X-Nexterp-Session-Key", ""),
        )

    def _error(self, exc: Exception) -> None:
        if isinstance(exc, ValidationError):
            status, error_type = HTTPStatus.BAD_REQUEST, "validation_error"
            details = exc.errors(include_url=False)
        elif isinstance(exc, PermissionError):
            status, error_type, details = HTTPStatus.FORBIDDEN, "permission_error", None
        elif isinstance(exc, KeyError):
            status, error_type, details = HTTPStatus.NOT_FOUND, "not_found", None
        elif isinstance(exc, (ValueError, RuntimeError)):
            status, error_type, details = HTTPStatus.BAD_REQUEST, "operation_error", None
        else:
            status, error_type, details = HTTPStatus.INTERNAL_SERVER_ERROR, "unknown_error", None
        payload: dict[str, Any] = {"ok": False, "error_type": error_type, "message": str(exc)}
        if details is not None:
            payload["details"] = details
        respond(self, payload, status)


def run_server(host: str = "127.0.0.1", port: int = 8790) -> None:
    load_dotenv()
    dsn = os.environ.get("MATERIAL_CATALOG_DATABASE_URL", "")
    repository = CapabilityCatalogRepository(dsn)
    repository.migrate()
    service = CapabilityManualService(repository)
    server = ThreadingHTTPServer((host, port), CapabilityAPIHandler)
    server.service = service  # type: ignore[attr-defined]
    print(f"Nexterp Capability API listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server(
        os.environ.get("NEXTERP_CAPABILITY_API_HOST", "127.0.0.1"),
        int(os.environ.get("NEXTERP_CAPABILITY_API_PORT", "8790")),
    )
