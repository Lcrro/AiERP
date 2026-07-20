from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SESSION_DIR = REPO_ROOT / "data" / "runtime" / "sessions"


@dataclass
class RuntimeSessionState:
    user: str
    profile: str
    company: str | None = None
    selected_project_code: str | None = None
    selected_warehouse_name: str | None = None
    documents: dict[str, list[str]] = field(default_factory=dict)
    pending: dict[str, Any] | None = None
    turns: list[dict[str, Any]] = field(default_factory=list)
    idempotency_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    selected_entities: dict[str, dict[str, Any]] = field(default_factory=dict)
    agent_steps: list[dict[str, Any]] = field(default_factory=list)
    pending_action: dict[str, Any] | None = None
    business_state: dict[str, Any] = field(default_factory=dict)
    updated_at: str | None = None

    def remember_document(self, doctype: str, name: str) -> None:
        values = self.documents.setdefault(doctype, [])
        if name not in values:
            values.append(name)

    def add_turn(self, payload: dict[str, Any]) -> None:
        self.turns.append(payload)
        self.turns = self.turns[-50:]
        self.updated_at = datetime.now().astimezone().isoformat()

    def remember_request(self, request_id: str, result: dict[str, Any]) -> None:
        self.idempotency_results[request_id] = result
        if len(self.idempotency_results) > 100:
            oldest = next(iter(self.idempotency_results))
            self.idempotency_results.pop(oldest, None)


class RuntimeSessionStore:
    def __init__(self, directory: Path = DEFAULT_SESSION_DIR) -> None:
        self.directory = directory

    def path_for(self, user: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", user)
        return self.directory / f"{safe}.json"

    def load(self, user: str, *, profile: str) -> RuntimeSessionState:
        path = self.path_for(user)
        if not path.exists():
            return RuntimeSessionState(user=user, profile=profile)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return RuntimeSessionState(**payload)

    def save(self, state: RuntimeSessionState) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        state.updated_at = datetime.now().astimezone().isoformat()
        path = self.path_for(state.user)
        path.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path
