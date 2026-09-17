"""Thin lifecycle wrapper for the compact 4-container stack.

Does not replace material_sites.py dual-stack path. Secrets stay under
``.secrets/erpnext-compact/`` and are never printed.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPACT_SCRIPTS = ROOT / "deploy" / "compact-dev" / "scripts"


def run_script(name: str) -> int:
    script = COMPACT_SCRIPTS / name
    if not script.is_file():
        print(f"error: missing {script}", file=sys.stderr)
        return 1
    return subprocess.call(["bash", str(script)], cwd=str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Compact dev stack lifecycle (Plan A)")
    parser.add_argument(
        "--action",
        choices=("status", "up", "down", "restore", "smoke", "restart-test", "backup-verify"),
        required=True,
    )
    args = parser.parse_args()
    mapping = {
        "backup-verify": "backup-verify.sh",
        "up": "up.sh",
        "down": "down.sh",
        "restore": "restore-sites.sh",
        "smoke": "smoke.sh",
        "restart-test": "restart-test.sh",
    }
    if args.action == "status":
        script = COMPACT_SCRIPTS / "_common.sh"
        # inline status via compose ps
        return subprocess.call(
            [
                "bash",
                "-lc",
                f'source "{script}" && compose ps',
            ],
            cwd=str(ROOT),
        )
    return run_script(mapping[args.action])


if __name__ == "__main__":
    raise SystemExit(main())
