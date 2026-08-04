from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from deepseek_family_governance import (  # noqa: E402
    DEFAULT_INPUT,
    DEFAULT_OUTPUT_ROOT,
    MODEL_FIELDS,
    apply_preview,
    build_browser_payload,
    read_tsv,
    write_tsv,
)


DEFAULT_COHORT = DEFAULT_OUTPUT_ROOT / "cohort_001.tsv"
DEFAULT_PREVIEW = DEFAULT_OUTPUT_ROOT / "cohort_001_material_master_preview.tsv"
DEFAULT_BROWSER_DATA = DEFAULT_OUTPUT_ROOT / "cohort_001_browser_data.json"
DEFAULT_REVIEW_QUEUE = DEFAULT_OUTPUT_ROOT / "cohort_001_review_queue.tsv"
DEFAULT_SUMMARY = DEFAULT_OUTPUT_ROOT / "cohort_001_preview_summary.json"

REVIEW_QUEUE_FIELDS = [
    "top_group",
    "material_family",
    "item_code",
    "severity",
    "issue_type",
    "issue",
    "suggestion",
    "review_status",
]


def read_cohort(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if not rows or any(not row.get("top_group") or not row.get("material_family") for row in rows):
        raise ValueError(f"{path}: cohort must contain top_group and material_family")
    return rows


def load_family_result(
    top_group: str,
    material_family: str,
    output_root: Path,
) -> tuple[list[dict[str, str]], dict[str, Any], dict[str, Any]]:
    output_dir = output_root / f"{top_group}_{material_family}"
    proposed_path = output_dir / "family_governed.tsv"
    review_path = output_dir / "independent_review.json"
    summary_path = output_dir / "summary.json"
    if not proposed_path.exists() or not review_path.exists() or not summary_path.exists():
        raise FileNotFoundError(f"Incomplete family result: {output_dir}")
    fields, rows = read_tsv(proposed_path)
    if fields != MODEL_FIELDS:
        raise ValueError(f"{proposed_path}: unexpected fields {fields}")
    return (
        rows,
        json.loads(review_path.read_text(encoding="utf-8")),
        json.loads(summary_path.read_text(encoding="utf-8")),
    )


def build_preview(
    *,
    source_rows: list[dict[str, str]],
    cohort_rows: list[dict[str, str]],
    output_root: Path,
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    proposed_rows: list[dict[str, str]] = []
    review_issues: list[dict[str, str]] = []
    family_results: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for family in cohort_rows:
        top_group = family["top_group"]
        material_family = family["material_family"]
        proposed, review, summary = load_family_result(
            top_group,
            material_family,
            output_root,
        )
        duplicate_codes = seen_codes.intersection(row["item_code"] for row in proposed)
        if duplicate_codes:
            raise ValueError(f"item_code appears in multiple families: {sorted(duplicate_codes)}")
        seen_codes.update(row["item_code"] for row in proposed)
        proposed_rows.extend(proposed)
        for issue in review.get("issues", []):
            review_issues.append(
                {
                    "top_group": top_group,
                    "material_family": material_family,
                    "item_code": str(issue.get("item_code", "")),
                    "severity": str(issue.get("severity", "")),
                    "issue_type": str(issue.get("issue_type", "")),
                    "issue": str(issue.get("issue", "")),
                    "suggestion": str(issue.get("suggestion", "")),
                    "review_status": "待人工确认",
                }
            )
        family_results.append(
            {
                "top_group": top_group,
                "material_family": material_family,
                "source_rows": int(summary.get("source_rows", len(proposed))),
                "proposed_rows": len(proposed),
                "review_verdict": review.get("verdict", "unknown"),
                "review_issue_count": len(review.get("issues", [])),
            }
        )

    combined_review = {"issues": review_issues}
    preview_rows = apply_preview(source_rows, proposed_rows, combined_review)
    severity_counts = Counter(issue["severity"] for issue in review_issues)
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "authoritative": False,
        "source_rows": len(source_rows),
        "governed_rows": len(proposed_rows),
        "family_count": len(family_results),
        "review_pass_family_count": sum(
            1 for row in family_results if row["review_verdict"] == "pass"
        ),
        "review_pending_family_count": sum(
            1 for row in family_results if row["review_verdict"] != "pass"
        ),
        "review_issue_count": len(review_issues),
        "review_severity_counts": dict(severity_counts),
        "families": family_results,
        "note": "Preview only. The authoritative release file was not modified.",
    }
    return preview_rows, review_issues, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge isolated family governance results into one preview.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--preview", type=Path, default=DEFAULT_PREVIEW)
    parser.add_argument("--browser-data", type=Path, default=DEFAULT_BROWSER_DATA)
    parser.add_argument("--review-queue", type=Path, default=DEFAULT_REVIEW_QUEUE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser.parse_args()


def absolute(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def main() -> int:
    args = parse_args()
    input_path = absolute(args.input)
    cohort_path = absolute(args.cohort)
    output_root = absolute(args.output_root)
    preview_path = absolute(args.preview)
    browser_path = absolute(args.browser_data)
    review_queue_path = absolute(args.review_queue)
    summary_path = absolute(args.summary)
    input_fields, source_rows = read_tsv(input_path)
    preview_rows, review_issues, summary = build_preview(
        source_rows=source_rows,
        cohort_rows=read_cohort(cohort_path),
        output_root=output_root,
    )
    write_tsv(preview_path, preview_rows, input_fields)
    write_tsv(review_queue_path, review_issues, REVIEW_QUEUE_FIELDS)
    browser_path.parent.mkdir(parents=True, exist_ok=True)
    browser_path.write_text(
        json.dumps(
            build_browser_payload(preview_rows, source=preview_path),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
