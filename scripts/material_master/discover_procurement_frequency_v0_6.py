"""Run sixth-pass procurement discovery and write a read-only review package."""

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
from nexterp_agent.item_master.procurement_frequency_discovery_v0_6 import (  # noqa: E402
    DEFAULT_OUTPUT_ROOT,
    discover_v6,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="第六轮物料族发现：目录对齐、族级决策与安全合并边界")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    result = discover_v6(args.source, args.output_root)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"result: {result['output_root']}")
    print("priority_decisions:")
    for row in result["review_decisions"]:
        if row["decision"] not in {"selector", "configurable", "split_required"}:
            continue
        print(json.dumps({
            "type": row["standard_type_candidate"],
            "decision": row["decision"],
            "lines": row["line_count"],
            "variants": row["variant_count"],
            "catalog_match_status": row["catalog_match_status"],
            "selector_axes": row["selector_axes"],
            "required_attribute_gaps": row["required_attribute_gaps"],
            "unit_reliability": row["unit_evidence"]["reliability"],
            "publication_gate": row["publication_gate"],
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
