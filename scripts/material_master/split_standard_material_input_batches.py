from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "material_purchase_2024"
DEFAULT_INPUT_PATH = DEFAULT_DATA_DIR / "standard_material_input_from_review.tsv"
DEFAULT_BATCH_DIR = DEFAULT_DATA_DIR / "standard_material_input_batches"


def read_rows(input_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader.fieldnames or []), list(reader)


def write_batch(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def split_batches(input_path: Path, batch_dir: Path, batch_size: int) -> int:
    fieldnames, rows = read_rows(input_path)
    total = len(rows)
    count = math.ceil(total / batch_size)
    for index in range(count):
        start = index * batch_size
        end = min(start + batch_size, total)
        filename = f"standard_material_input_batch_{index + 1:03d}.tsv"
        write_batch(batch_dir / filename, fieldnames, rows[start:end])
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Split standard material input TSV into fixed-size batches.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH_DIR)
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()

    count = split_batches(args.input, args.batch_dir, args.batch_size)
    print(f"batches: {count}")
    print(f"batch_dir: {args.batch_dir}")


if __name__ == "__main__":
    main()
