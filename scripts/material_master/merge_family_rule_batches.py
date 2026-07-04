from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_DIR = REPO_ROOT / "data" / "material_master" / "reclassification" / "family_governance"
DEFAULT_OUTPUT_PATH = DEFAULT_INPUT_DIR / "material_family_rules.tsv"
DEFAULT_SUMMARY_PATH = DEFAULT_INPUT_DIR / "material_family_rules_summary.json"

FIELDS = [
    "domain",
    "candidate_term",
    "decision",
    "suggested_family",
    "split_rule",
    "family_attributes",
    "include_examples",
    "exclude_examples",
    "priority",
    "confidence",
    "reason",
]

ALLOWED_DECISIONS = {"solidify", "split", "attribute_only", "reject"}
ALLOWED_PRIORITIES = {"P0", "P1", "P2"}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != FIELDS:
            raise ValueError(f"{path}: unexpected fields {reader.fieldnames}")
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def validate_rows(rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for index, row in enumerate(rows, start=2):
        key = (row["domain"], row["candidate_term"], row["suggested_family"])
        if key in seen:
            errors.append(f"row {index}: duplicate rule {key}")
        seen.add(key)
        for field in ["domain", "candidate_term", "decision", "suggested_family", "priority", "confidence", "reason"]:
            if not row[field]:
                errors.append(f"row {index}: missing {field}")
        if row["decision"] not in ALLOWED_DECISIONS:
            errors.append(f"row {index}: invalid decision {row['decision']!r}")
        if row["priority"] not in ALLOWED_PRIORITIES:
            errors.append(f"row {index}: invalid priority {row['priority']!r}")
        if row["confidence"] not in ALLOWED_CONFIDENCE:
            errors.append(f"row {index}: invalid confidence {row['confidence']!r}")
        if row["decision"] == "split" and not row["split_rule"]:
            errors.append(f"row {index}: split decision requires split_rule")
        if row["decision"] in {"solidify", "split"} and not row["family_attributes"]:
            errors.append(f"row {index}: {row['decision']} decision requires family_attributes")
    return errors


def merge_batches(input_dir: Path) -> tuple[list[dict[str, str]], dict[str, object]]:
    batch_paths = sorted(input_dir.glob("family_rules_batch_*.tsv"))
    if not batch_paths:
        raise FileNotFoundError(f"No family_rules_batch_*.tsv files found in {input_dir}")
    rows: list[dict[str, str]] = []
    batch_counts: dict[str, int] = {}
    for path in batch_paths:
        batch_rows = read_tsv(path)
        batch_counts[path.name] = len(batch_rows)
        rows.extend(batch_rows)
    errors = validate_rows(rows)
    if errors:
        message = "\n".join(errors[:80])
        suffix = "\n..." if len(errors) > 80 else ""
        raise ValueError(f"Family rule validation failed with {len(errors)} errors:\n{message}{suffix}")
    rows.sort(key=lambda row: (row["priority"], row["domain"], row["candidate_term"], row["suggested_family"]))
    summary = {
        "batch_counts": batch_counts,
        "rule_count": len(rows),
        "decision_counts": dict(Counter(row["decision"] for row in rows).most_common()),
        "priority_counts": dict(Counter(row["priority"] for row in rows).most_common()),
        "confidence_counts": dict(Counter(row["confidence"] for row in rows).most_common()),
        "domain_counts": dict(Counter(row["domain"] for row in rows).most_common()),
    }
    return rows, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge material family governance rule batches.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows, summary = merge_batches(args.input_dir)
    write_tsv(args.output, rows)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
