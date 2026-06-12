from __future__ import annotations

import argparse
import csv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "material_purchase_2024"
DEFAULT_SOURCE_PATH = DEFAULT_DATA_DIR / "standard_item_catalog_from_review.csv"
DEFAULT_OUTPUT_PATH = DEFAULT_DATA_DIR / "standard_material_input_from_review.tsv"

OUTPUT_FIELDS = [
    "编号",
    "名称",
    "规格",
    "分组",
    "单位",
    "别名/土名",
    "整理提示/依据",
]


def build_hint(row: dict[str, str]) -> str:
    parts: list[str] = []
    status = (row.get("source_statuses") or "").strip()
    notes = (row.get("notes") or "").strip()

    if status and status != "可建档":
        parts.append(f"状态：{status}")
    if notes:
        parts.append(notes)

    return "；".join(parts)


def convert_row(row: dict[str, str]) -> dict[str, str]:
    return {
        "编号": row.get("proposed_item_code", ""),
        "名称": row.get("standard_name", ""),
        "规格": row.get("specs", ""),
        "分组": row.get("item_group", ""),
        "单位": row.get("unit", ""),
        "别名/土名": row.get("alias_names", ""),
        "整理提示/依据": build_hint(row),
    }


def build_input(source_path: Path, output_path: Path) -> int:
    with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(convert_row(row) for row in rows)

    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build standard material cleanup input from review catalog.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    count = build_input(args.source, args.output)
    print(f"input rows: {count}")
    print(f"output: {args.output}")


if __name__ == "__main__":
    main()
