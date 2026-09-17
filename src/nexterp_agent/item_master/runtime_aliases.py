from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .release_resolver import normalize_text
from .source_identity import normalize_source_records


DEFAULT_RUNTIME_ALIAS_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "material_master"
    / "runtime_aliases.jsonl"
)


class RuntimeAliasStore:
    """Small auditable store for aliases explicitly confirmed by a user.

    Analysis never writes this file.  A separate confirmation endpoint calls
    ``confirm`` after validating the selected type or SKU against the release
    catalog.  JSONL keeps the first version portable; it can later be imported
    into the existing PostgreSQL governance catalog without changing callers.
    """

    def __init__(self, path: str | Path = DEFAULT_RUNTIME_ALIAS_PATH) -> None:
        self.path = Path(path)

    def active(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("enabled", True):
                rows.append(row)
        return rows

    def confirm(
        self,
        *,
        alias: str,
        target_kind: str,
        target_id: str,
        user: str,
        source_row: str = "",
        source_identity: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        alias = str(alias or "").strip()
        if len(alias) < 2:
            raise ValueError("alias 至少需要 2 个字符")
        if target_kind not in {"type", "sku"}:
            raise ValueError("target_kind 必须是 type 或 sku")
        if not target_id:
            raise ValueError("target_id 不能为空")
        scoped_identity: dict[str, Any] = {}
        if source_identity:
            scoped_identity = next(iter(normalize_source_records([source_identity])), {})
        # A legacy caller may still provide source_row for display purposes,
        # but it is deliberately not stored as an identity key.  Only the
        # complete composite record can ever be used to join source data.
        legacy_source_row = str(source_row or "").strip() if not scoped_identity else ""
        row = {
            "alias_id": f"ALIAS-{uuid4().hex[:12].upper()}",
            "alias": alias,
            "normalized_alias": normalize_text(alias),
            "target_kind": target_kind,
            "target_id": target_id,
            "source": "user_confirmation",
            "confirmed_by": user,
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
            "source_identity": scoped_identity,
            "source_identity_status": "scoped" if scoped_identity else "unscoped_legacy",
            "enabled": True,
        }
        if legacy_source_row:
            row["legacy_source_row"] = legacy_source_row
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row
