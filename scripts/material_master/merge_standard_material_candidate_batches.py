from __future__ import annotations

import argparse
import csv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "material_purchase_2024"
DEFAULT_BATCH_DIR = DEFAULT_DATA_DIR / "standard_material_candidate_batches"
DEFAULT_OUTPUT_PATH = DEFAULT_DATA_DIR / "standard_material_candidates_curated.tsv"

FIELDS = [
    "标准名称",
    "必填规格",
    "辅助规格",
    "标准分组",
    "标准单位",
    "别名/土名",
    "放行等级",
    "整理依据",
]

ALLOWED_GRADES = {"A", "B", "C", "D"}


def read_batch(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != FIELDS:
            raise ValueError(f"{path.name}: unexpected fields {reader.fieldnames}")
        rows = list(reader)
    for index, row in enumerate(rows, start=2):
        grade = row.get("放行等级", "")
        if grade not in ALLOWED_GRADES:
            raise ValueError(f"{path.name}:{index}: invalid grade {grade!r}")
        for field in ["标准名称", "必填规格", "标准分组", "标准单位", "放行等级"]:
            if not (row.get(field) or "").strip():
                raise ValueError(f"{path.name}:{index}: missing required field {field}")
    return rows


def merge_batches(batch_dir: Path, output_path: Path) -> int:
    paths = sorted(batch_dir.glob("standard_material_candidate_batch_*.tsv"))
    rows: list[dict[str, str]] = []
    for path in paths:
        rows.extend(read_batch(path))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and merge standard material candidate batch TSV files.")
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    count = merge_batches(args.batch_dir, args.output)
    print(f"merged rows: {count}")
    print(f"output: {args.output}")


if __name__ == "__main__":
    main()
