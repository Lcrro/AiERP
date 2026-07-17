from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.erpnext.client import ERPNextClient
from nexterp_agent.master_data import MasterDataRelease


def load_dotenv(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate per-employee ERPNext API credentials for the civil sandbox.")
    parser.add_argument("--profile", default="civil")
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / ".secrets" / "erpnext-civil-users.json")
    parser.add_argument(
        "--user",
        action="append",
        default=[],
        help="Generate credentials only for this user. Repeat for multiple users.",
    )
    args = parser.parse_args()
    load_dotenv(args.env_file)
    prefix = f"NEXTERP_{args.profile.upper()}_"
    client = ERPNextClient(
        os.environ[prefix + "BASE_URL"],
        os.environ[prefix + "API_KEY"],
        os.environ[prefix + "API_SECRET"],
        host_header=os.getenv(prefix + "HOST_HEADER"),
    )
    users: dict[str, dict[str, str]] = {}
    if args.output.exists():
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        if isinstance(existing, dict) and isinstance(existing.get("users"), dict):
            users.update(existing["users"])
    employees = list(MasterDataRelease().employees.values())
    if args.user:
        requested = set(args.user)
        employees = [employee for employee in employees if employee["user_email"] in requested]
        found = {employee["user_email"] for employee in employees}
        missing = sorted(requested - found)
        if missing:
            raise RuntimeError(f"Unknown employee users: {', '.join(missing)}")
    for employee in employees:
        user = employee["user_email"]
        result = client.call_method("frappe.core.doctype.user.user.generate_keys", {"user": user})
        if not result.ok or not isinstance(result.data, dict):
            raise RuntimeError(f"Failed to generate API keys for {user}: {result.error}")
        users[user] = {"api_key": result.data["api_key"], "api_secret": result.data["api_secret"]}
        print(f"generated={user}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"profile": args.profile, "users": users}, indent=2) + "\n", encoding="utf-8")
    print(f"credentials_file={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
