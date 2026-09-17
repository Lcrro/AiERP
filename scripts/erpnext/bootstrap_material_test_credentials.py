"""Generate sandbox-only API keys after the material-test Users exist.

The command logs in with the local Site Administrator password from the ignored
secret file, writes keys only under ``.secrets/erpnext-material-test`` and
never prints a key or secret.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.erpnext.bootstrap_material_test_business import DEFAULT_SECRET_PATH, SANDBOX_USERS  # noqa: E402
from scripts.erpnext.sync_gpc_materials_to_test_site import _load_client, SyncError  # noqa: E402


DEFAULT_OUTPUT = ROOT / ".secrets" / "erpnext-material-test" / "user-api-credentials.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secret-file", type=Path, default=DEFAULT_SECRET_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        client = _load_client(args.secret_file)
        existing: dict[str, dict[str, str]] = {}
        if args.output.is_file():
            payload = json.loads(args.output.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("users"), dict):
                existing = dict(payload["users"])
        for row in SANDBOX_USERS:
            user = str(row["email"])
            result = client.method(
                "frappe.core.doctype.user.user.generate_keys",
                {"user": user},
                http_method="POST",
            )
            if not isinstance(result, dict) or not result.get("api_key") or not result.get("api_secret"):
                raise SyncError(f"无法为沙盘用户生成 API 凭据：{user}")
            existing[user] = {"api_key": str(result["api_key"]), "api_secret": str(result["api_secret"])}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({"profile": "material_test", "users": existing}, indent=2) + "\n", encoding="utf-8")
        print(f"generated={len(SANDBOX_USERS)} users; credentials_file={args.output}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
