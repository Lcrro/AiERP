from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.erpnext import ERPNextClient
from nexterp_agent.erpnext.config import load_erpnext_settings

DEFAULT_INPUT = ROOT / "data" / "material_purchase_2024" / "standard_item_master_draft.tsv"
DEFAULT_OUTPUT = ROOT / "data" / "material_purchase_2024" / "erpnext_item_import_verification.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify standard SKU drafts imported into ERPNext Items.")
    parser.add_argument("--profile", default="local")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    rows = load_rows(args.input)
    draft_codes = [row["draft_item_code"] for row in rows]

    settings = load_erpnext_settings(args.profile)
    client = ERPNextClient(
        settings.base_url,
        settings.api_key,
        settings.api_secret,
        host_header=settings.host_header,
        timeout=60,
    )

    erpnext_items = fetch_item_names(client)
    missing = [code for code in draft_codes if code not in erpnext_items]
    samples = fetch_samples(client, draft_codes)
    summary: dict[str, Any] = {
        "profile": args.profile,
        "input": str(args.input),
        "erpnext_item_count": len(erpnext_items),
        "draft_rows": len(rows),
        "draft_unique_codes": len(set(draft_codes)),
        "draft_codes_found": len(draft_codes) - len(missing),
        "draft_codes_missing": len(missing),
        "missing_sample": missing[:20],
        "sample_items": samples,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not missing else 1


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def fetch_item_names(client: ERPNextClient) -> set[str]:
    names: set[str] = set()
    offset = 0
    limit = 500
    while True:
        result = client.search_documents("Item", fields=["name"], limit=limit, offset=offset, order_by="name asc")
        if not result.ok:
            raise RuntimeError(result.error or result.user_message or "Cannot fetch Item list")
        records = result.data if isinstance(result.data, list) else []
        for record in records:
            if isinstance(record, dict) and record.get("name"):
                names.add(str(record["name"]))
        if len(records) < limit:
            break
        offset += limit
    return names


def fetch_samples(client: ERPNextClient, draft_codes: list[str]) -> list[dict[str, Any]]:
    indexes = [0, 1, 999, len(draft_codes) - 1]
    samples = []
    for index in indexes:
        if index < 0 or index >= len(draft_codes):
            continue
        code = draft_codes[index]
        result = client.get_document("Item", code)
        if not result.ok:
            samples.append({"item_code": code, "ok": False, "error": result.error})
            continue
        data = result.data or {}
        samples.append(
            {
                "item_code": code,
                "ok": True,
                "item_name": data.get("item_name"),
                "item_group": data.get("item_group"),
                "stock_uom": data.get("stock_uom"),
                "specification": data.get("specification"),
            }
        )
    return samples


if __name__ == "__main__":
    raise SystemExit(main())
