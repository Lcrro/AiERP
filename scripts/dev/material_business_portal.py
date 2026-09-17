"""Run the no-AI business portal with server-side test-account switching."""

from __future__ import annotations

import sys

from agent_workbench import main


if __name__ == "__main__":
    sys.argv.extend(["--profile", "material_test", "--port", "8788"])
    raise SystemExit(main())
