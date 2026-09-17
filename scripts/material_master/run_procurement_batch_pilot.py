"""Run the local, read-only Longhua procurement batch pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.item_master.procurement_batch_pilot import (  # noqa: E402
    DEFAULT_LONGHUA_WORKBOOK_PATH,
    DEFAULT_RUNTIME_ROOT,
    MAX_PILOT_ROWS,
    ProcurementBatchPilot,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="整理龙华实际采购清单的本地 GPC 候选，不写入 ERPNext")
    parser.add_argument("--source", type=Path, default=DEFAULT_LONGHUA_WORKBOOK_PATH)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--limit", type=int, default=MAX_PILOT_ROWS)
    parser.add_argument("--local-only", action="store_true", help="仅验证本地读取/检索，不调用 DeepSeek")
    parser.add_argument("--job-id", default="")
    args = parser.parse_args()

    pilot = ProcurementBatchPilot(source_path=args.source, runtime_root=args.runtime_root)

    def progress(stage: str, percent: int, message: str, metrics: dict[str, object]) -> None:
        suffix = f" {json.dumps(metrics, ensure_ascii=False)}" if metrics else ""
        print(f"[{percent:3d}%] {stage}: {message}{suffix}", flush=True)

    result = pilot.run(
        limit=args.limit,
        use_deepseek=not args.local_only,
        job_id=args.job_id or None,
        progress=progress,
    )
    print(json.dumps(result["audit"], ensure_ascii=False, indent=2))
    print(f"result: {result['job_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
