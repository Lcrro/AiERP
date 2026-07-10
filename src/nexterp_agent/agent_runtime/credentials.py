from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CREDENTIALS_PATH = REPO_ROOT / ".secrets" / "erpnext-civil-users.json"


def load_user_credentials(user: str, path: Path = DEFAULT_CREDENTIALS_PATH) -> dict[str, str]:
    if not path.exists():
        raise RuntimeError(f"Missing employee ERPNext credentials file: {path}")
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    users = payload.get("users") if isinstance(payload, dict) else None
    credentials = users.get(user) if isinstance(users, dict) else None
    if not isinstance(credentials, dict) or not credentials.get("api_key") or not credentials.get("api_secret"):
        raise RuntimeError(f"Missing ERPNext API credentials for employee: {user}")
    return {"api_key": credentials["api_key"], "api_secret": credentials["api_secret"]}
