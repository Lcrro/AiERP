from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import deepseek_test_price_trial as trial  # noqa: E402


DEFAULT_OUTPUT_DIR = trial.REPO_ROOT / "outputs" / "master_data" / "test_price_batches"


def load_priceable_rows(path: Path, *, limit: int | None = None) -> list[dict[str, str]]:
    rows = trial.read_tsv(path)
    selected = [
        trial.compact_row(row)
        for row in rows
        if row.get("item_code") and row.get("sku_name") and row.get("stock_uom")
    ]
    if limit is not None:
        return selected[:limit]
    return selected


def chunk_rows(rows: list[dict[str, str]], batch_size: int) -> list[list[dict[str, str]]]:
    return [rows[index : index + batch_size] for index in range(0, len(rows), batch_size)]


def write_batch_request(batch_dir: Path, batch_index: int, rows: list[dict[str, str]], messages: list[dict[str, str]]) -> None:
    trial.write_json(
        batch_dir / "request.json",
        {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "batch_index": batch_index,
            "row_count": len(rows),
            "rows": rows,
            "messages": messages,
        },
    )
    trial.write_tsv(batch_dir / "input.tsv", rows, trial.INPUT_FIELDS)


def process_batch(
    *,
    batch_index: int,
    rows: list[dict[str, str]],
    run_dir: Path,
    retries: int,
    retry_delay_seconds: float,
    force: bool,
) -> dict[str, Any]:
    batch_dir = run_dir / f"batch_{batch_index:03d}"
    price_path = batch_dir / "prices.tsv"
    validation_path = batch_dir / "validation.json"
    if price_path.exists() and validation_path.exists() and not force:
        return {
            "batch_index": batch_index,
            "status": "skipped",
            "row_count": len(rows),
            "price_tsv": str(price_path),
        }

    messages = trial.build_messages(rows)
    batch_dir.mkdir(parents=True, exist_ok=True)
    write_batch_request(batch_dir, batch_index, rows, messages)

    last_error = ""
    for attempt in range(1, retries + 2):
        try:
            response = trial.call_deepseek_json(messages)
            trial.write_json(batch_dir / "response.json", response)
            price_rows, validation = trial.validate_response(rows, response)
            trial.write_tsv(price_path, price_rows, trial.PRICE_TSV_FIELDS)
            trial.write_json(
                validation_path,
                {
                    **validation,
                    "batch_index": batch_index,
                    "attempt": attempt,
                    "price_tsv": str(price_path),
                },
            )
            return {
                "batch_index": batch_index,
                "status": "ok",
                "row_count": len(price_rows),
                "warnings": validation["warnings"],
                "price_tsv": str(price_path),
                "attempt": attempt,
            }
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            trial.write_json(
                batch_dir / "error.json",
                {
                    "batch_index": batch_index,
                    "attempt": attempt,
                    "error": last_error,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
            if attempt <= retries:
                time.sleep(retry_delay_seconds * attempt)

    return {
        "batch_index": batch_index,
        "status": "failed",
        "row_count": len(rows),
        "error": last_error,
    }


def read_price_rows(price_tsv: Path) -> list[dict[str, Any]]:
    return trial.read_tsv(price_tsv)


def merge_successful_batches(run_dir: Path, batch_results: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [
        result
        for result in sorted(batch_results, key=lambda item: item["batch_index"])
        if result["status"] in {"ok", "skipped"}
    ]
    merged_rows: list[dict[str, Any]] = []
    for result in successful:
        merged_rows.extend(read_price_rows(Path(result["price_tsv"])))

    merged_path = run_dir / "deepseek_test_item_prices.tsv"
    trial.write_tsv(merged_path, merged_rows, trial.PRICE_TSV_FIELDS)

    item_codes = [row["item_code"] for row in merged_rows]
    duplicates = sorted({code for code in item_codes if item_codes.count(code) > 1})
    confidence_counts: dict[str, int] = {}
    risk_counts: dict[str, int] = {}
    for row in merged_rows:
        confidence = row.get("confidence", "")
        confidence_counts[confidence] = confidence_counts.get(confidence, 0) + 1
        for flag in str(row.get("risk_flags", "")).split("；"):
            flag = flag.strip()
            if flag:
                risk_counts[flag] = risk_counts.get(flag, 0) + 1

    summary = {
        "merged_tsv": str(merged_path),
        "merged_rows": len(merged_rows),
        "successful_batches": len(successful),
        "duplicate_item_codes": duplicates,
        "confidence_counts": confidence_counts,
        "risk_counts": dict(sorted(risk_counts.items())),
    }
    trial.write_json(run_dir / "merge_summary.json", summary)
    return summary


def revalidate_existing_run(run_dir: Path) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for batch_dir in sorted(run_dir.glob("batch_*")):
        if not batch_dir.is_dir():
            continue
        batch_index = int(batch_dir.name.rsplit("_", 1)[1])
        input_path = batch_dir / "input.tsv"
        response_path = batch_dir / "response.json"
        if not input_path.exists() or not response_path.exists():
            results.append(
                {
                    "batch_index": batch_index,
                    "status": "failed",
                    "row_count": 0,
                    "error": "missing input.tsv or response.json",
                }
            )
            continue
        rows = trial.read_tsv(input_path)
        response = json.loads(response_path.read_text(encoding="utf-8"))
        price_rows, validation = trial.validate_response(rows, response)
        price_path = batch_dir / "prices.tsv"
        validation_path = batch_dir / "validation.json"
        trial.write_tsv(price_path, price_rows, trial.PRICE_TSV_FIELDS)
        trial.write_json(
            validation_path,
            {
                **validation,
                "batch_index": batch_index,
                "revalidated_at": datetime.now().isoformat(timespec="seconds"),
                "price_tsv": str(price_path),
            },
        )
        results.append(
            {
                "batch_index": batch_index,
                "status": "ok",
                "row_count": len(price_rows),
                "warnings": validation["warnings"],
                "price_tsv": str(price_path),
                "revalidated": True,
            }
        )

    results.sort(key=lambda item: item["batch_index"])
    trial.write_json(run_dir / "batch_results.json", results)
    merge_summary = merge_successful_batches(run_dir, results)
    failures = [result for result in results if result["status"] == "failed"]
    summary = {
        "run_dir": str(run_dir),
        "revalidated_batches": len(results) - len(failures),
        "failed_batches": len(failures),
        "merge_summary": merge_summary,
    }
    trial.write_json(run_dir / "run_summary.json", summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DeepSeek estimated test prices in concurrent batches.")
    parser.add_argument("--input", type=Path, default=trial.DEFAULT_INPUT_TSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-delay-seconds", type=float, default=5)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--revalidate-run", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.revalidate_run is not None:
        summary = revalidate_existing_run(args.revalidate_run)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if summary["failed_batches"]:
            raise SystemExit(f"{summary['failed_batches']} batch(es) failed during revalidation")
        return

    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be positive")
    if args.concurrency <= 0:
        raise SystemExit("--concurrency must be positive")

    rows = load_priceable_rows(args.input, limit=args.limit)
    batches = chunk_rows(rows, args.batch_size)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    run_dir = args.output_dir / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    run_meta = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "input": str(args.input),
        "row_count": len(rows),
        "batch_size": args.batch_size,
        "batch_count": len(batches),
        "concurrency": args.concurrency,
        "retries": args.retries,
    }
    trial.write_json(run_dir / "run_meta.json", run_meta)
    trial.write_tsv(run_dir / "selected_input.tsv", rows, trial.INPUT_FIELDS)

    print(json.dumps({**run_meta, "run_dir": str(run_dir)}, ensure_ascii=False, indent=2))

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(
                process_batch,
                batch_index=batch_index,
                rows=batch_rows,
                run_dir=run_dir,
                retries=args.retries,
                retry_delay_seconds=args.retry_delay_seconds,
                force=args.force,
            )
            for batch_index, batch_rows in enumerate(batches, start=1)
        ]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(
                json.dumps(
                    {
                        "batch_index": result["batch_index"],
                        "status": result["status"],
                        "row_count": result["row_count"],
                        "attempt": result.get("attempt"),
                        "error": result.get("error"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    results.sort(key=lambda item: item["batch_index"])
    trial.write_json(run_dir / "batch_results.json", results)
    failures = [result for result in results if result["status"] == "failed"]
    merge_summary = merge_successful_batches(run_dir, results)
    final_summary = {
        **run_meta,
        "run_dir": str(run_dir),
        "ok_batches": sum(1 for result in results if result["status"] == "ok"),
        "skipped_batches": sum(1 for result in results if result["status"] == "skipped"),
        "failed_batches": len(failures),
        "merge_summary": merge_summary,
    }
    trial.write_json(run_dir / "run_summary.json", final_summary)
    print(json.dumps(final_summary, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(f"{len(failures)} batch(es) failed; see {run_dir / 'batch_results.json'}")


if __name__ == "__main__":
    main()
