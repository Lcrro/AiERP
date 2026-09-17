"""Run the fourth-pass, three-axis procurement family discovery."""

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
from nexterp_agent.item_master.procurement_frequency_discovery_v0_4 import (  # noqa: E402
    DEFAULT_OUTPUT_ROOT,
    discover_v4,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="第四轮按族模板、源数据质量和发布准备度分轴发现采购物料")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    result = discover_v4(args.source, args.output_root)
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
            "source_data_quality": row["source_data_quality"],
            "publication_readiness": row["publication_readiness"],
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
