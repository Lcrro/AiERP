"""Reconcile sandbox user roles on the isolated material-test Site."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.erpnext.bootstrap_material_test_business import (  # noqa: E402
    DEFAULT_SECRET_PATH,
    SANDBOX_USERS,
)
from scripts.erpnext.sync_gpc_materials_to_test_site import (  # noqa: E402
    FrappeSessionClient,
    SyncError,
    _load_client,
)


def reconcile(client: FrappeSessionClient) -> dict[str, Any]:
    """Add missing declared roles and verify them by reading the User back."""
    changed: list[str] = []
    unchanged: list[str] = []
    for expected in SANDBOX_USERS:
        email = str(expected["email"])
        user = client.get_doc("User", email)
        if user is None:
            raise SyncError(f"sandbox user does not exist: {email}")
        expected_roles = {str(role) for role in expected.get("roles", [])}
        current_roles = {
            str(row.get("role"))
            for row in (user.get("roles") or [])
            if isinstance(row, dict) and row.get("role")
        }
        if expected_roles.issubset(current_roles):
            unchanged.append(email)
            continue
        merged_roles = sorted(current_roles | expected_roles)
        client.update_doc(
            "User",
            email,
            {"roles": [{"doctype": "Has Role", "role": role} for role in merged_roles]},
        )
        readback = client.get_doc("User", email) or {}
        readback_roles = {
            str(row.get("role"))
            for row in (readback.get("roles") or [])
            if isinstance(row, dict) and row.get("role")
        }
        if not expected_roles.issubset(readback_roles):
            raise SyncError(f"role readback failed: {email}")
        changed.append(email)
    return {"site": "material-test.localhost", "changed": changed, "unchanged": unchanged}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secret-file", type=Path, default=DEFAULT_SECRET_PATH)
    args = parser.parse_args()
    try:
        client = _load_client(Path(args.secret_file))
        print(json.dumps(reconcile(client), ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
