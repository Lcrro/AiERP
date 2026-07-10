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
from nexterp_agent.master_data import MasterDataImporter, build_import_operations


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def build_client(profile: str) -> ERPNextClient:
    prefix = f"NEXTERP_{profile.upper()}_"
    required = ["BASE_URL", "API_KEY", "API_SECRET"]
    values = {name: os.getenv(prefix + name) for name in required}
    missing = [prefix + name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(f"Missing ERPNext configuration: {', '.join(missing)}")
    return ERPNextClient(
        values["BASE_URL"] or "",
        values["API_KEY"] or "",
        values["API_SECRET"] or "",
        host_header=os.getenv(prefix + "HOST_HEADER"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan, apply, or verify the v1 master data release in ERPNext.")
    parser.add_argument("mode", choices=["plan", "apply", "verify"])
    parser.add_argument("--profile", default="local")
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env")
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--stage", action="append", default=[], help="Limit execution to one or more plan stages.")
    parser.add_argument("--doctype", action="append", default=[], help="Limit execution to one or more DocTypes.")
    parser.add_argument("--key", action="append", default=[], help="Limit execution to exact operation keys.")
    parser.add_argument("--limit", type=int, default=0, help="Limit operation count for a controlled smoke run.")
    parser.add_argument("--workers", type=int, default=1, help="Parallel workers for an independent DocType batch.")
    args = parser.parse_args()

    load_dotenv(args.env_file)
    operations = build_import_operations()
    if args.stage:
        operations = [operation for operation in operations if operation.stage in set(args.stage)]
    if args.doctype:
        operations = [operation for operation in operations if operation.doctype in set(args.doctype)]
    if args.key:
        operations = [operation for operation in operations if operation.key in set(args.key)]
    if args.limit > 0:
        operations = operations[: args.limit]
    if args.mode == "apply" and args.workers > 1 and len({operation.doctype for operation in operations}) > 1:
        raise RuntimeError("Parallel apply/verify requires --doctype to select one independent DocType.")
    if args.mode == "plan":
        payload = MasterDataImporter(operations=operations).plan()
    else:
        importer = MasterDataImporter(build_client(args.profile), operations)
        payload = (
            importer.apply(stop_on_error=not args.continue_on_error, workers=args.workers)
            if args.mode == "apply"
            else importer.verify(workers=args.workers)
        )

    report_path = args.report or REPO_ROOT / "data" / "runtime" / f"master_data_{args.mode}_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items() if key != "operations" and key != "results"}, ensure_ascii=False, indent=2))
    print(f"report={report_path}")
    return 0 if payload.get("failed_count", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
