from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.item_master.procurement_batch_publication import ProcurementBatchGpcPublisher


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish one frozen local procurement batch into the internal GPC workbench.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--curation-path", type=Path)
    args = parser.parse_args()
    result = ProcurementBatchGpcPublisher().publish(args.job_id, curation_path=args.curation_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
