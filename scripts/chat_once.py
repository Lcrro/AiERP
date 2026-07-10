from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.agent_runtime.civil_runtime import CivilAgentRuntime
from nexterp_agent.agent_runtime.credentials import load_user_credentials
from nexterp_agent.erpnext.client import ERPNextClient


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one natural-language civil ERP Agent turn.")
    parser.add_argument("text")
    parser.add_argument("--user", required=True, help="ERPNext employee user email")
    parser.add_argument("--profile", default="civil")
    parser.add_argument("--execute", action="store_true", help="Explicitly confirm and execute the compiled ToolCall")
    parser.add_argument("--json", action="store_true", help="Print the complete structured result")
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env")
    args = parser.parse_args()
    load_dotenv(args.env_file)
    prefix = f"NEXTERP_{args.profile.upper()}_"

    def client_factory(user: str) -> ERPNextClient:
        credentials = load_user_credentials(user)
        return ERPNextClient(
            os.environ[prefix + "BASE_URL"],
            credentials["api_key"],
            credentials["api_secret"],
            host_header=os.getenv(prefix + "HOST_HEADER"),
        )

    runtime = CivilAgentRuntime(client_factory=client_factory)
    result = runtime.run_once(args.text, user=args.user, execute=args.execute)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2) if args.json else result.message)
    if result.questions and not args.json:
        for question in result.questions:
            print(f"- {question}")
    if result.candidates and not args.json:
        print(json.dumps(result.candidates, ensure_ascii=False, indent=2))
    if result.tool_call and not args.execute and not args.json:
        print(json.dumps(result.tool_call, ensure_ascii=False, indent=2))
    return 0 if result.status not in {"failed", "unsupported_intent"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
