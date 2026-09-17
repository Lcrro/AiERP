"""Run fifth-pass procurement-family discovery and write read-only review data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.item_master.procurement_frequency_discovery import DEFAULT_SOURCE_PATH  # noqa: E402
from nexterp_agent.item_master.procurement_frequency_discovery_v0_5 import (  # noqa: E402
    DEFAULT_OUTPUT_ROOT,
    discover_v5,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="第五轮物料族发现：分离属性、单位、源数据和发布门禁")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    result = discover_v5(args.source, args.output_root)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"result: {result['output_root']}")
    print("template_review_priority:")
    for row in result["review_queues"]["template_review_priority"]:
        print(json.dumps({
            "rank": row["integration_rank"],
            "type": row["standard_type_candidate"],
            "lines": row["line_count"],
            "variants": row["variant_count"],
            "family_template_status": row["family_template_status"],
            "unit_policy_status": row["unit_policy_status"],
            "source_evidence_quality": row["source_evidence_quality"],
            "publication_readiness": row["publication_readiness"],
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
