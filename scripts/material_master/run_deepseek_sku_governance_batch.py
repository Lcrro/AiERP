from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from deepseek_sku_governance_trial import (  # noqa: E402
    DEFAULT_INPUT_JSON,
    DEFAULT_OUTPUT_DIR,
    build_messages,
    call_deepseek_json,
    load_deepseek_settings,
    load_target_skus,
    validate_result,
    write_tsv,
)
from merge_sku_governance_duplicates import (  # noqa: E402
    DUPLICATE_COLUMNS,
    UNIQUE_COLUMNS,
    merge_rows,
    read_rows as read_governed_rows,
    write_tsv as write_merge_tsv,
)


DEFAULT_TARGETS = [
    ("管材管件阀门", "弯头", "弯头"),
    ("管材管件阀门", "阀门", "球阀"),
    ("管材管件阀门", "三通", "三通"),
    ("管材管件阀门", "管材", "直管"),
]

STRICT_VALIDATION_KEYS = ("missing", "extra", "duplicates")


@dataclass(frozen=True)
class Target:
    top_group: str
    material_family: str
    material_name: str

    @classmethod
    def parse(cls, text: str) -> "Target":
        parts = [part.strip() for part in text.split("|")]
        if len(parts) != 3 or not all(parts):
            raise ValueError(f"Target must use top_group|material_family|material_name: {text}")
        return cls(parts[0], parts[1], parts[2])

    def slug(self, index: int) -> str:
        raw = f"{index:02d}_{self.top_group}_{self.material_family}_{self.material_name}"
        return re.sub(r'[\\/:*?"<>|\\s]+', "_", raw).strip("_")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle, delimiter="\t")
        ]


def latest_attempt_rows(target_dir: Path) -> Path | None:
    attempts = sorted(
        target_dir.glob("rows_attempt_*.tsv"),
        key=lambda path: (path.stat().st_mtime, path.name),
    )
    return attempts[-1] if attempts else None


def load_all_targets(input_json: Path) -> list[Target]:
    payload = json.loads(input_json.read_text(encoding="utf-8"))
    seen: set[tuple[str, str, str]] = set()
    for row in payload["rows"]:
        key = (
            str(row.get("top_group") or "").strip(),
            str(row.get("material_family") or "").strip(),
            str(row.get("item_name") or "").strip(),
        )
        if all(key):
            seen.add(key)
    return [Target(*key) for key in sorted(seen)]


def validation_is_strictly_ok(validation: dict[str, Any]) -> bool:
    if any(validation.get(key) for key in STRICT_VALIDATION_KEYS):
        return False
    return int(validation.get("input_count") or 0) == int(validation.get("output_count") or -1)


def run_target(
    *,
    target: Target,
    index: int,
    input_json: Path,
    batch_dir: Path,
    dry_run: bool,
    reuse_existing: bool,
    max_retries: int,
    strict: bool,
) -> dict[str, Any]:
    target_dir = batch_dir / target.slug(index)
    target_dir.mkdir(parents=True, exist_ok=True)

    skus = load_target_skus(
        input_json,
        top_group=target.top_group,
        material_family=target.material_family,
        material_name=target.material_name,
    )
    if not skus:
        raise ValueError(f"No SKU rows found for {target}")

    messages = build_messages(
        top_group=target.top_group,
        material_family=target.material_family,
        material_name=target.material_name,
        skus=skus,
    )
    request_payload = {
        "target": {
            "top_group": target.top_group,
            "material_family": target.material_family,
            "material_name": target.material_name,
            "sku_count": len(skus),
        },
        "messages": messages,
    }
    request_path = target_dir / "request.json"
    response_path = target_dir / "response.json"
    rows_path = target_dir / "rows.tsv"
    unique_path = target_dir / "unique.tsv"
    duplicates_path = target_dir / "duplicates.tsv"
    write_json(request_path, request_payload)

    if dry_run:
        return {
            "target": request_payload["target"],
            "dry_run": True,
            "request": str(request_path),
        }

    reusable_rows_path = rows_path if rows_path.exists() else latest_attempt_rows(target_dir)
    if reuse_existing and reusable_rows_path and reusable_rows_path.exists():
        rows = read_governed_rows(reusable_rows_path)
        if reusable_rows_path != rows_path:
            write_tsv(rows_path, rows)
        unique_rows, duplicate_rows = merge_rows(rows)
        write_merge_tsv(unique_path, unique_rows, UNIQUE_COLUMNS)
        write_merge_tsv(duplicates_path, duplicate_rows, DUPLICATE_COLUMNS)
        validation = {}
        if response_path.exists():
            response_payload = json.loads(response_path.read_text(encoding="utf-8"))
            validation = response_payload.get("validation", {})
        return {
            "target": request_payload["target"],
            "request": str(request_path),
            "response": str(response_path),
            "rows_tsv": str(rows_path),
            "unique_tsv": str(unique_path),
            "duplicates_tsv": str(duplicates_path),
            "input_rows": len(skus),
            "output_rows": len(rows),
            "unique_rows": len(unique_rows),
            "duplicate_groups": len(duplicate_rows),
            "validation": validation,
            "summary": {"reused_existing_rows": True},
        }

    settings = load_deepseek_settings()
    last_error: Exception | None = None
    response_payload: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = []
    validation: dict[str, Any] = {}
    for attempt in range(1, max(1, max_retries) + 1):
        try:
            result = call_deepseek_json(messages, settings=settings)
            validation = validate_result(result, [row["item_code"] for row in skus])
            response_payload = {
                "model": settings.model,
                "target": request_payload["target"],
                "attempt": attempt,
                "validation": validation,
                "result": result,
            }
            write_json(target_dir / f"response_attempt_{attempt}.json", response_payload)
            rows = result.get("rows", [])
            write_tsv(target_dir / f"rows_attempt_{attempt}.tsv", rows)
            if strict and not validation_is_strictly_ok(validation):
                raise ValueError(f"strict validation failed: {validation}")
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            write_json(
                target_dir / f"error_attempt_{attempt}.json",
                {
                    "target": request_payload["target"],
                    "attempt": attempt,
                    "error": str(exc),
                },
            )
    else:
        raise RuntimeError(f"DeepSeek governance failed after {max_retries} attempt(s): {last_error}")

    if response_payload is None:
        raise RuntimeError("DeepSeek governance did not produce a response payload")

    write_json(response_path, response_payload)
    write_tsv(rows_path, rows)

    unique_rows, duplicate_rows = merge_rows(rows)
    write_merge_tsv(unique_path, unique_rows, UNIQUE_COLUMNS)
    write_merge_tsv(duplicates_path, duplicate_rows, DUPLICATE_COLUMNS)

    return {
        "target": request_payload["target"],
        "request": str(request_path),
        "response": str(response_path),
        "rows_tsv": str(rows_path),
        "unique_tsv": str(unique_path),
        "duplicates_tsv": str(duplicates_path),
        "input_rows": len(skus),
        "output_rows": len(rows),
        "unique_rows": len(unique_rows),
        "duplicate_groups": len(duplicate_rows),
        "validation": validation,
        "summary": result.get("summary", {}),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DeepSeek SKU governance for multiple material-name targets concurrently.")
    parser.add_argument("--input-json", type=Path, default=DEFAULT_INPUT_JSON)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--batch-name", default=None)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--target", action="append", default=[], help="Format: top_group|material_family|material_name")
    parser.add_argument("--top-group", default=None, help="Single target top group. Use with --material-family and --material-name.")
    parser.add_argument("--material-family", default=None, help="Single target material family.")
    parser.add_argument("--material-name", default=None, help="Single target material name.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reuse-existing", action="store_true", help="Reuse existing rows.tsv files and only rerun merge/post-processing.")
    parser.add_argument("--all-targets", action="store_true", help="Process every top_group/material_family/material_name target in the input JSON.")
    parser.add_argument("--limit", type=int, default=None, help="Limit target count for smoke runs.")
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--no-strict", action="store_true", help="Do not retry/mark failure when output count or item_code coverage is wrong.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.top_group or args.material_family or args.material_name:
        if not (args.top_group and args.material_family and args.material_name):
            raise SystemExit("--top-group, --material-family, and --material-name must be provided together.")
        targets = [Target(args.top_group, args.material_family, args.material_name)]
    elif args.target:
        targets = [Target.parse(item) for item in args.target]
    elif args.all_targets:
        targets = load_all_targets(args.input_json)
    else:
        targets = [Target(*item) for item in DEFAULT_TARGETS]
    if args.limit is not None:
        targets = targets[: args.limit]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_name = args.batch_name or f"batch_{timestamp}"
    batch_dir = args.output_dir / batch_name
    batch_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        future_to_target = {
            executor.submit(
                run_target,
                target=target,
                index=index,
                input_json=args.input_json,
                batch_dir=batch_dir,
                dry_run=args.dry_run,
                reuse_existing=args.reuse_existing,
                max_retries=args.max_retries,
                strict=not args.no_strict,
            ): target
            for index, target in enumerate(targets, start=1)
        }
        for future in as_completed(future_to_target):
            target = future_to_target[future]
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    {
                        "target": {
                            "top_group": target.top_group,
                            "material_family": target.material_family,
                            "material_name": target.material_name,
                        },
                        "error": str(exc),
                    }
                )

    summary = {
        "batch_dir": str(batch_dir),
        "target_count": len(targets),
        "success_count": len(results),
        "error_count": len(errors),
        "results": sorted(results, key=lambda item: item["target"]["material_family"] + item["target"]["material_name"]),
        "errors": errors,
    }
    if results and not args.dry_run:
        all_unique: list[dict[str, Any]] = []
        all_duplicates: list[dict[str, Any]] = []
        for result in results:
            target_label = (
                result["target"]["top_group"]
                + "/"
                + result["target"]["material_family"]
                + "/"
                + result["target"]["material_name"]
            )
            unique_path = Path(result["unique_tsv"])
            if unique_path.exists():
                for row in read_tsv(unique_path):
                    row["target"] = target_label
                    all_unique.append(row)
            duplicates_path = Path(result["duplicates_tsv"])
            if duplicates_path.exists():
                for row in read_tsv(duplicates_path):
                    row["target"] = target_label
                    all_duplicates.append(row)
        aggregate_unique_path = batch_dir / "unique_all.tsv"
        aggregate_duplicates_path = batch_dir / "duplicates_all.tsv"
        if all_unique:
            write_merge_tsv(aggregate_unique_path, all_unique, [*UNIQUE_COLUMNS, "target"])
        if all_duplicates:
            write_merge_tsv(aggregate_duplicates_path, all_duplicates, [*DUPLICATE_COLUMNS, "target"])
        summary["aggregate"] = {
            "unique_rows": len(all_unique),
            "duplicate_rows": len(all_duplicates),
            "unique_tsv": str(aggregate_unique_path) if all_unique else "",
            "duplicates_tsv": str(aggregate_duplicates_path) if all_duplicates else "",
        }
    summary_path = batch_dir / "batch_summary.json"
    write_json(summary_path, summary)
    print(
        json.dumps(
            {
                "summary": str(summary_path),
                "batch_dir": summary["batch_dir"],
                "target_count": summary["target_count"],
                "success_count": summary["success_count"],
                "error_count": summary["error_count"],
                "aggregate": summary.get("aggregate", {}),
                "errors_preview": errors[:10],
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
