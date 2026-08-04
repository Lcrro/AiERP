from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
GOVERNANCE_SCRIPT = REPO_ROOT / "scripts" / "material_master" / "deepseek_family_governance.py"
DEFAULT_COHORT = (
    REPO_ROOT
    / "data"
    / "material_master"
    / "governance_v0_4"
    / "cohort_001.tsv"
)
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "material_master" / "governance_v0_4"


def read_cohort(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle, delimiter="\t")
        ]
    if not rows or any(not row.get("top_group") or not row.get("material_family") for row in rows):
        raise ValueError("cohort requires top_group and material_family on every row")
    return rows


def build_command(
    row: dict[str, str],
    *,
    chunk_size: int,
    row_concurrency: int,
    reuse: bool,
    reuse_review: bool = False,
) -> list[str]:
    command = [
        sys.executable,
        str(GOVERNANCE_SCRIPT),
        "--top-group",
        row["top_group"],
        "--material-family",
        row["material_family"],
        "--auto-guide",
        "--chunk-size",
        str(chunk_size),
        "--concurrency",
        str(row_concurrency),
    ]
    if reuse:
        command.extend(["--reuse-guide", "--reuse-responses"])
    if reuse_review:
        command.append("--reuse-review")
    return command


def run_family(
    row: dict[str, str],
    *,
    chunk_size: int,
    row_concurrency: int,
    reuse: bool,
    reuse_review: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    command = build_command(
        row,
        chunk_size=chunk_size,
        row_concurrency=row_concurrency,
        reuse=reuse,
        reuse_review=reuse_review,
    )
    process = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output_dir = DEFAULT_OUTPUT_ROOT / f"{row['top_group']}_{row['material_family']}"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cohort_run.log").write_text(
        process.stdout + ("\nSTDERR:\n" + process.stderr if process.stderr else ""),
        encoding="utf-8",
    )
    summary_path = output_dir / "summary.json"
    summary = (
        json.loads(summary_path.read_text(encoding="utf-8"))
        if process.returncode == 0 and summary_path.exists()
        else {}
    )
    return {
        "top_group": row["top_group"],
        "material_family": row["material_family"],
        "success": process.returncode == 0,
        "return_code": process.returncode,
        "duration_seconds": round(time.perf_counter() - started, 2),
        "source_rows": summary.get("source_rows", 0),
        "proposed_rows": summary.get("proposed_rows", 0),
        "review_verdict": summary.get("independent_review", {}).get("verdict", "failed"),
        "review_issue_count": summary.get("independent_review", {}).get("issue_count", 0),
        "output_dir": str(output_dir.relative_to(REPO_ROOT)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run several material families in isolation.")
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--family-concurrency", type=int, default=3)
    parser.add_argument("--row-concurrency", type=int, default=2)
    parser.add_argument("--chunk-size", type=int, default=20)
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--reuse-review", action="store_true")
    args = parser.parse_args()
    cohort_path = args.cohort if args.cohort.is_absolute() else REPO_ROOT / args.cohort
    rows = read_cohort(cohort_path)
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.family_concurrency)) as executor:
        futures = {
            executor.submit(
                run_family,
                row,
                chunk_size=args.chunk_size,
                row_concurrency=args.row_concurrency,
                reuse=args.reuse,
                reuse_review=args.reuse_review,
            ): row
            for row in rows
        }
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda row: (row["top_group"], row["material_family"]))
    batch_summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "cohort": str(cohort_path.relative_to(REPO_ROOT)),
        "family_count": len(results),
        "success_count": sum(1 for row in results if row["success"]),
        "pass_count": sum(1 for row in results if row["review_verdict"] == "pass"),
        "results": results,
    }
    summary_path = DEFAULT_OUTPUT_ROOT / f"{cohort_path.stem}_summary.json"
    summary_path.write_text(
        json.dumps(batch_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(batch_summary, ensure_ascii=False, indent=2))
    return 0 if batch_summary["success_count"] == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
