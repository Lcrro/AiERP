from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.erpnext import ERPNextAdapter, ERPNextClient
from nexterp_agent.erpnext.config import load_erpnext_settings


def build_adapter(profile: str) -> ERPNextAdapter:
    settings = load_erpnext_settings(profile)
    client = ERPNextClient(
        settings.base_url,
        settings.api_key,
        settings.api_secret,
        host_header=settings.host_header,
    )
    return ERPNextAdapter(client)


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize material master fields in ERPNext.")
    parser.add_argument("--profile", default="local")
    args = parser.parse_args()

    adapter = build_adapter(args.profile)
    result = adapter.execute({"tool": "erpnext.setup_item_master"})
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
