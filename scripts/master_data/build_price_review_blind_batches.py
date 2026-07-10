from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path


DEFAULT_SAMPLE = Path("data/material_master/price_review_samples/price_review_sample_10pct_by_family.tsv")
DEFAULT_OUTPUT_DIR = Path("data/material_master/price_review_samples/blind_batches")
DEFAULT_AGENT_COUNT = 5

BLIND_FIELDS = [
    "item_code",
    "item_name",
    "sku_name",
    "required_specs",
    "top_group",
    "sub_group",
    "material_family",
    "unit",
    "aliases",
    "brand",
    "model",
]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def split_batches(rows: list[dict[str, str]], agent_count: int) -> list[list[dict[str, str]]]:
    batches: list[list[dict[str, str]]] = [[] for _ in range(agent_count)]
    for index, row in enumerate(rows):
        batches[index % agent_count].append(row)
    return batches


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build blind price review batches without old price anchors.")
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--agent-count", type=int, default=DEFAULT_AGENT_COUNT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.agent_count <= 0:
        raise ValueError("--agent-count must be positive")

    rows = read_tsv(args.sample)
    batches = split_batches(rows, args.agent_count)
    summary = {
        "source": str(args.sample),
        "output_dir": str(args.output_dir),
        "generated_at": date.today().isoformat(),
        "agent_count": args.agent_count,
        "source_count": len(rows),
        "fields": BLIND_FIELDS,
        "batches": [],
    }
    for index, batch in enumerate(batches, start=1):
        batch_path = args.output_dir / f"price_review_blind_batch_{index:02d}.tsv"
        write_tsv(batch_path, batch, BLIND_FIELDS)
        summary["batches"].append(
            {
                "batch": index,
                "path": str(batch_path),
                "count": len(batch),
                "family_count": len({row.get("material_family", "") for row in batch}),
            }
        )
    write_json(args.output_dir / "price_review_blind_batches_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
