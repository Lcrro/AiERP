from __future__ import annotations

import argparse
import csv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "material_purchase_2024"
DEFAULT_OUTPUT_PATH = DEFAULT_DATA_DIR / "manual_governance_progress.csv"

FIELDS = [
    "batch",
    "issue_id",
    "source_name",
    "identify",
    "spec_normalization",
    "standard_name_normalization",
    "group_normalization",
    "release_grade",
    "judgement",
    "next_action",
]


def load_manual_batches(data_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(data_dir.glob("manual_governance_batch_*.tsv")):
      with path.open("r", encoding="utf-8-sig", newline="") as handle:
          reader = csv.DictReader(handle, delimiter="\t")
          for row in reader:
              rows.append({field: row.get(field, "") for field in FIELDS})
    return rows


def write_progress(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the manual material governance progress CSV.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    rows = load_manual_batches(args.data_dir)
    write_progress(rows, args.output)
    print(f"manual governance rows: {len(rows)}")
    print(f"output: {args.output}")


if __name__ == "__main__":
    main()
