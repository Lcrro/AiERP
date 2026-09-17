"""Run the second-pass read-only procurement family discovery."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.item_master.procurement_frequency_discovery_v0_2 import (  # noqa: E402
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_SOURCE_PATH,
    discover_v2,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="第二轮只读发现实际采购清单中的物料族、别名、规格和频次")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    result = discover_v2(args.source, args.output_root)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"result: {result['output_root']}")
    print("top_integration_candidates:")
    for row in result["clusters"][:30]:
        print(json.dumps({
            "rank": row["integration_rank"],
            "type": row["standard_type_candidate"],
            "confidence": row["family_confidence"],
            "queue": row["queue"],
            "review_status": row["review_status"],
            "lines": row["line_count"],
            "events": row["distinct_event_count_approx"],
            "dates": row["active_purchase_date_count"],
            "sessions": row["purchase_session_count"],
            "raw_names": row["raw_name_count"],
            "variants": row["variant_count"],
            "alias_groups": row["alias_candidate_group_count"],
            "uom": row["uom_quality"]["status"],
            "rows": row["source_rows"][:8],
        }, ensure_ascii=False))
    print("top_frequency_clusters:")
    for row in sorted(result["clusters"], key=lambda item: (item["frequency_rank"], item["cluster_id"]))[:30]:
        print(json.dumps({
            "rank": row["frequency_rank"],
            "type": row["standard_type_candidate"],
            "confidence": row["family_confidence"],
            "queue": row["queue"],
            "events": row["distinct_event_count_approx"],
            "lines": row["line_count"],
            "dates": row["active_purchase_date_count"],
            "sessions": row["purchase_session_count"],
            "raw_names": row["raw_name_count"],
            "variants": row["variant_count"],
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
