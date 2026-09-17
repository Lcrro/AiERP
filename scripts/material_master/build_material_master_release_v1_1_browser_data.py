"""Build read-only browser data for the material master v1.1 candidate release."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data/material_master/release_v1_1/material_master_release_v1_1.tsv"
DEFAULT_OUTPUT = ROOT / "data/material_master/release_v1_1/material_master_release_v1_1_browser_data.json"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def counts(rows: list[dict[str, str]], key: str) -> dict[str, int]:
    return dict(Counter(row.get(key, "") for row in rows if row.get(key, "")))


def build_categories(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row.get("top_group", "待治理")].append(row)
    categories: list[dict[str, object]] = []
    for name, items in sorted(grouped.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        sub_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in items:
            sub_groups[row.get("sub_group", "待治理")].append(row)
        categories.append(
            {
                "name": name,
                "sku_count": len(items),
                "name_count": len({row.get("item_name", "") for row in items if row.get("item_name")}),
                "status_counts": counts(items, "status"),
                "quality_counts": counts(items, "quality_level"),
                "sub_groups": [
                    {"name": sub_name, "sku_count": len(sub_items)}
                    for sub_name, sub_items in sorted(sub_groups.items(), key=lambda pair: (-len(pair[1]), pair[0]))
                ],
            }
        )
    return categories


def build(input_path: Path = DEFAULT_INPUT, output_path: Path = DEFAULT_OUTPUT) -> dict[str, object]:
    rows = read_rows(input_path)
    for row in rows:
        row["search_text"] = " ".join(value for value in row.values() if value).lower()
    summary = {
        "sku_count": len(rows),
        "item_name_count": len({row.get("item_name", "") for row in rows}),
        "material_family_count": len({row.get("material_family", "") for row in rows}),
        "top_group_count": len({row.get("top_group", "") for row in rows}),
        "item_group_count": len({row.get("item_group", "") for row in rows}),
        "type_count": len({row.get("classification_key", "") for row in rows}),
        "status_counts": counts(rows, "status"),
        "quality_counts": counts(rows, "quality_level"),
        "agent_use_policy_counts": counts(rows, "agent_use_policy"),
        "classification_status_counts": counts(rows, "classification_status"),
        "issue_counts": {
            "missing_required_specs": sum(bool(row.get("missing_required_specs")) for row in rows),
            "candidate_family": sum("source_family_was_candidate" in row.get("governance_note", "") for row in rows),
            "human_confirmation": sum(row.get("agent_use_policy") == "confirm_before_use" for row in rows),
        },
    }
    payload = {
        "generated_at": datetime.now().replace(microsecond=0).isoformat(),
        "source": str(input_path),
        "family_rules_source": "docs/reference/material-entry-rules-v1.1.md",
        "family_rules_count": 0,
        "summary": summary,
        "categories": build_categories(rows),
        "family_rule_impacts": [],
        "rows": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build(args.input, args.output)
    print(json.dumps({"output": str(args.output), **payload["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
