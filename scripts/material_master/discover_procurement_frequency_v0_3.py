"""Run the third-pass, quality-gated procurement family discovery."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.item_master.procurement_frequency_discovery_v0_3 import (  # noqa: E402
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_SOURCE_PATH,
    discover_v3,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="第三轮只读发现采购物料族、规格、频次和数据质量门禁")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    result = discover_v3(args.source, args.output_root)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"result: {result['output_root']}")
    print("top_review_candidates:")
    for row in result["clusters"][:30]:
        print(json.dumps({
            "rank": row["integration_rank"],
            "type": row["standard_type_candidate"],
            "gate": row["publish_gate"],
            "quadrant": row["frequency_quadrant"],
            "lines": row["line_count"],
            "events": row["distinct_event_count_approx"],
            "dates": row["active_purchase_date_count"],
            "variants": row["variant_count"],
            "uom": row["uom_quality"]["status"],
            "preferred_uom": row["uom_quality"]["preferred_uom"],
            "price_evidence": row["price_evidence"],
            "rows": row["source_rows"][:8],
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
