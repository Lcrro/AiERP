"""Find high-frequency material groups in the Longhua purchase list."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.item_master.procurement_frequency_discovery import (  # noqa: E402
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_SOURCE_PATH,
    discover,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="只读发现实际采购清单中的高频物料族和多规格整合候选")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    result = discover(args.source, args.output_root)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"result: {result['output_root']}")
    print("top_integration_candidates:")
    for row in result["clusters"][:30]:
        print(json.dumps({
            "type": row["standard_type_candidate"],
            "queue": row["queue"],
            "lines": row["line_count"],
            "events": row["distinct_event_count_approx"],
            "aliases": row["alias_count"],
            "variants": row["variant_count"],
            "score": row["integration_priority_score"],
            "rows": row["source_rows"][:8],
        }, ensure_ascii=False))
    print("top_frequency_clusters:")
    for row in sorted(result["clusters"], key=lambda item: (item["frequency_rank"], item["cluster_id"]))[:30]:
        print(json.dumps({
            "rank": row["frequency_rank"],
            "type": row["standard_type_candidate"],
            "queue": row["queue"],
            "events": row["distinct_event_count_approx"],
            "lines": row["line_count"],
            "aliases": row["alias_count"],
            "variants": row["variant_count"],
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
