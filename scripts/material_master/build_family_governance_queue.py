from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = (
    REPO_ROOT
    / "data"
    / "material_master"
    / "release_v1_0"
    / "material_master_release_v1_0.tsv"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "data"
    / "material_master"
    / "governance_v0_4"
    / "family_governance_queue.tsv"
)

FIELDS = [
    "priority_rank",
    "top_group",
    "material_family",
    "row_count",
    "item_name_count",
    "generic_name_rows",
    "dimension_in_item_name_rows",
    "uom_count",
    "uoms",
    "duplicate_signature_groups",
    "priority_score",
    "recommended_action",
]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle, delimiter="\t")
        ]


def normalize_signature(row: dict[str, str]) -> tuple[str, str, str]:
    specs = re.sub(r"\s+", "", row.get("required_specs", "")).replace("*", "×")
    return (
        row.get("item_name", "").strip().lower(),
        specs.lower(),
        row.get("stock_uom", "").strip().lower(),
    )


def build_queue(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    grouped: defaultdict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row.get("top_group", ""), row.get("material_family", ""))].append(row)

    queue: list[dict[str, Any]] = []
    for (top_group, material_family), family_rows in grouped.items():
        names = {row.get("item_name", "") for row in family_rows if row.get("item_name", "")}
        uoms = sorted({row.get("stock_uom", "") for row in family_rows if row.get("stock_uom", "")})
        generic_name_rows = sum(
            1
            for row in family_rows
            if row.get("item_name", "").strip() == material_family.strip()
        )
        dimension_rows = sum(
            1
            for row in family_rows
            if re.search(r"\d+(?:\.\d+)?\s*(?:mm|cm|m|寸|分|×|\*)", row.get("item_name", ""), re.I)
        )
        signature_counts = Counter(normalize_signature(row) for row in family_rows)
        duplicate_groups = sum(1 for count in signature_counts.values() if count > 1)
        score = (
            len(family_rows)
            + generic_name_rows * 2
            + dimension_rows * 3
            + max(0, len(uoms) - 1) * 5
            + duplicate_groups * 8
        )
        reasons: list[str] = []
        if generic_name_rows:
            reasons.append(f"{generic_name_rows}条名称等于物料族")
        if dimension_rows:
            reasons.append(f"{dimension_rows}条三级名称含规格")
        if len(uoms) > 1:
            reasons.append(f"{len(uoms)}种库存单位")
        if duplicate_groups:
            reasons.append(f"{duplicate_groups}组同名同规格疑似重复")
        if not reasons:
            reasons.append("按规模和采购频率复核")
        queue.append(
            {
                "top_group": top_group,
                "material_family": material_family,
                "row_count": len(family_rows),
                "item_name_count": len(names),
                "generic_name_rows": generic_name_rows,
                "dimension_in_item_name_rows": dimension_rows,
                "uom_count": len(uoms),
                "uoms": "；".join(uoms),
                "duplicate_signature_groups": duplicate_groups,
                "priority_score": score,
                "recommended_action": "；".join(reasons),
            }
        )
    queue.sort(
        key=lambda row: (
            -int(row["priority_score"]),
            -int(row["row_count"]),
            str(row["top_group"]),
            str(row["material_family"]),
        )
    )
    for index, row in enumerate(queue, start=1):
        row["priority_rank"] = index
    return queue


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank material families for governance.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    queue = build_queue(read_tsv(args.input))
    write_tsv(args.output, queue)
    print(f"families={len(queue)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
