"""Promote only explicitly reviewed positive retrieval rows to aliases.

The review queue is intentionally inert: pending rows, negative rows, and
rows without reviewer audit fields never become production aliases.  This
command is the explicit human-review boundary and writes only the local
approved-alias JSONL projection; it never writes ERPNext.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.item_master.release_resolver import normalize_text


DEFAULT_REVIEW_PATH = ROOT / "data" / "material_master" / "retrieval_review_v0_1.jsonl"
DEFAULT_OUTPUT_PATH = ROOT / "data" / "material_master" / "approved_material_aliases_v0_1.jsonl"
APPROVED_DECISIONS = {"approved", "confirmed", "positive", "通过", "确认", "正确"}


def _read_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def promote_reviewed_aliases(
    review_path: str | Path = DEFAULT_REVIEW_PATH,
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> dict[str, Any]:
    """Write the deterministic approved-alias projection and return a report."""

    review_file = Path(review_path)
    output_file = Path(output_path)
    accepted: list[dict[str, Any]] = []
    skipped = {"pending": 0, "negative": 0, "missing_audit": 0, "invalid": 0, "conflict": 0}
    by_alias: dict[str, set[str]] = {}
    for row in _read_rows(review_file):
        role = str(row.get("sample_role") or "").strip().casefold()
        decision = str(row.get("review_decision") or "").strip().casefold()
        if not decision:
            skipped["pending"] += 1
            continue
        if "positive" not in role:
            skipped["negative"] += 1
            continue
        if decision not in APPROVED_DECISIONS:
            skipped["invalid"] += 1
            continue
        alias = str(row.get("query") or "").strip()
        target = str(row.get("expected_item_code") or "").strip()
        reviewer = str(row.get("reviewer") or "").strip()
        reviewed_at = str(row.get("reviewed_at") or "").strip()
        if not alias or not target.isdigit() or not reviewer or not reviewed_at:
            skipped["missing_audit"] += 1
            continue
        key = normalize_text(alias)
        by_alias.setdefault(key, set()).add(target)
        accepted.append({
            "alias": alias,
            "target_id": target,
            "review_id": str(row.get("review_id") or ""),
            "review_decision": "approved",
            "reviewer": reviewer,
            "reviewed_at": reviewed_at,
            "source_identity": row.get("source_identity") or {},
            "enabled": True,
        })

    conflicting = {key for key, targets in by_alias.items() if len(targets) > 1}
    if conflicting:
        skipped["conflict"] = sum(
            1 for row in accepted if normalize_text(row["alias"]) in conflicting
        )
        accepted = [row for row in accepted if normalize_text(row["alias"]) not in conflicting]
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in accepted:
        deduped[(normalize_text(row["alias"]), row["target_id"])] = row
    output_rows = [
        deduped[key]
        for key in sorted(deduped)
    ]
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in output_rows),
        encoding="utf-8",
    )
    return {
        "review_path": str(review_file),
        "output_path": str(output_file),
        "approved_alias_count": len(output_rows),
        "skipped": skipped,
        "writes_erpnext": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="将人工审核通过的正样本导出为已审核物料别名")
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()
    print(json.dumps(promote_reviewed_aliases(args.review, args.output), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
