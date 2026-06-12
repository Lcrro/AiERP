from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.erpnext.tool_registry import ERPNext_TOOL_SCHEMAS

DEFAULT_PATHS = [
    ROOT / "docs" / "scenarios" / "civil-company-day-toolcall-coverage.md",
]
TOOL_MARKER_RE = re.compile(r"tool:(erpnext\.[A-Za-z0-9_.]+)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate scenario ToolCall coverage references.")
    parser.add_argument("paths", nargs="*", type=Path, default=DEFAULT_PATHS)
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    registered = {schema["name"] for schema in ERPNext_TOOL_SCHEMAS}
    referenced_by_file: dict[str, list[str]] = {}
    for path in args.paths:
        full_path = path if path.is_absolute() else ROOT / path
        text = full_path.read_text(encoding="utf-8")
        referenced_by_file[str(full_path)] = sorted(set(TOOL_MARKER_RE.findall(text)))

    referenced = sorted({tool for tools in referenced_by_file.values() for tool in tools})
    missing = [tool for tool in referenced if tool not in registered]
    unused_registered = sorted(registered - set(referenced))

    result = {
        "checked_files": list(referenced_by_file.keys()),
        "registered_tool_count": len(registered),
        "referenced_tool_count": len(referenced),
        "missing_tool_count": len(missing),
        "missing_tools": missing,
        "referenced_tools": referenced,
        "unused_registered_count": len(unused_registered),
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"checked files: {len(result['checked_files'])}")
        print(f"registered tools: {result['registered_tool_count']}")
        print(f"referenced tools: {result['referenced_tool_count']}")
        print(f"missing tools: {result['missing_tool_count']}")
        for tool in missing:
            print(f"missing: {tool}")

    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
