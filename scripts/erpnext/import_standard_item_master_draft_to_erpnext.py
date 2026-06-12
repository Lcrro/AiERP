from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass
from html import escape
from pathlib import Path
from time import monotonic
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.erpnext import ERPNextClient
from nexterp_agent.erpnext.config import load_erpnext_settings

DEFAULT_INPUT = ROOT / "data" / "material_purchase_2024" / "standard_item_master_draft.tsv"
DEFAULT_REPORT_JSON = ROOT / "data" / "material_purchase_2024" / "erpnext_item_import_report.json"
DEFAULT_REPORT_TSV = ROOT / "data" / "material_purchase_2024" / "erpnext_item_import_report.tsv"
ITEM_GROUP_ROOT_CANDIDATES = ("所有物料群组", "All Item Groups")
WHOLE_NUMBER_UOMS = {
    "个",
    "只",
    "件",
    "套",
    "把",
    "根",
    "支",
    "张",
    "包",
    "盒",
    "桶",
    "瓶",
    "块",
    "卷",
    "台",
    "双",
    "付",
    "副",
    "条",
    "本",
    "袋",
    "片",
    "盘",
    "箱",
    "组",
    "节",
    "辆",
    "部",
    "床",
}
REQUIRED_INPUT_COLUMNS = {
    "draft_sku_id",
    "draft_item_code",
    "release_status",
    "放行等级",
    "标准名称",
    "必填规格",
    "辅助规格",
    "标准分组",
    "标准单位",
    "别名/土名",
}


@dataclass
class ImportEvent:
    action: str
    doctype: str
    name: str
    ok: bool
    message: str = ""
    error_type: str = ""
    error: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import standard material SKU drafts into local ERPNext Items."
    )
    parser.add_argument("--profile", default="local", help="ERPNext env profile. Defaults to local.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--report-tsv", type=Path, default=DEFAULT_REPORT_TSV)
    parser.add_argument("--limit", type=int, default=None, help="Only process this many rows.")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many input rows.")
    parser.add_argument("--apply", action="store_true", help="Actually write to ERPNext.")
    parser.add_argument(
        "--update-existing",
        action="store_true",
        help="Update existing Item records instead of skipping them.",
    )
    parser.add_argument(
        "--no-setup-item-master",
        action="store_true",
        help="Do not call agent_bridge.api.setup_item_master before importing.",
    )
    args = parser.parse_args()

    rows = load_rows(args.input)
    selected_rows = rows[args.offset :]
    if args.limit is not None:
        selected_rows = selected_rows[: args.limit]

    settings = load_erpnext_settings(args.profile)
    client = ERPNextClient(
        settings.base_url,
        settings.api_key,
        settings.api_secret,
        host_header=settings.host_header,
        timeout=60,
    )

    started = monotonic()
    events: list[ImportEvent] = []

    user = client.get_logged_user()
    if not user.ok:
        print_result("auth", False, user.user_message or user.error or "ERPNext auth failed")
        return 1
    print(f"Connected to ERPNext as {user.data}")

    if not args.no_setup_item_master:
        if args.apply:
            setup = client.setup_item_master()
            events.append(
                ImportEvent(
                    action="setup_item_master",
                    doctype="Custom Field",
                    name="Item material fields",
                    ok=setup.ok,
                    message="ok" if setup.ok else setup.user_message or "",
                    error_type=setup.error_type or "",
                    error=setup.error or "",
                )
            )
            if not setup.ok:
                print_result("setup_item_master", False, setup.user_message or setup.error or "")
                write_reports(args.report_json, args.report_tsv, events, build_summary(args, rows, selected_rows, events, started))
                return 1
        else:
            events.append(
                ImportEvent(
                    action="dry_run_setup_item_master",
                    doctype="Custom Field",
                    name="Item material fields",
                    ok=True,
                    message="would call agent_bridge.api.setup_item_master",
                )
            )

    item_fields = load_doctype_fields(client, "Item")
    existing_items = load_existing_names(client, "Item")
    existing_uoms = load_existing_names(client, "UOM")
    existing_item_groups = load_existing_names(client, "Item Group")
    root_group = choose_item_group_root(existing_item_groups)

    group_name_map = build_item_group_name_map(selected_rows, existing_item_groups)
    ensure_uoms(client, selected_rows, existing_uoms, args.apply, events)
    ensure_item_groups(client, group_name_map, existing_item_groups, root_group, args.apply, events)
    import_items(
        client,
        selected_rows,
        item_fields,
        existing_items,
        group_name_map,
        args.apply,
        args.update_existing,
        events,
    )

    summary = build_summary(args, rows, selected_rows, events, started)
    write_reports(args.report_json, args.report_tsv, events, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed_total"] == 0 else 1


def load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        missing = REQUIRED_INPUT_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise RuntimeError(f"Input file is missing columns: {', '.join(sorted(missing))}")
        return [{key: clean_text(value) for key, value in row.items()} for row in reader]


def load_doctype_fields(client: ERPNextClient, doctype: str) -> set[str]:
    result = client.get_doctype_schema(doctype)
    if not result.ok:
        raise RuntimeError(f"Cannot load {doctype} schema: {result.error or result.user_message}")
    fields: set[str] = {"name"}
    raw_fields = result.data.get("fields", []) if isinstance(result.data, dict) else []
    for field in raw_fields:
        if isinstance(field, dict) and field.get("fieldname"):
            fields.add(str(field["fieldname"]))
    return fields


def load_existing_names(client: ERPNextClient, doctype: str) -> set[str]:
    names: set[str] = set()
    offset = 0
    limit = 500
    while True:
        result = client.search_documents(
            doctype,
            fields=["name"],
            limit=limit,
            offset=offset,
            order_by="modified desc",
        )
        if not result.ok:
            raise RuntimeError(f"Cannot load existing {doctype}: {result.error or result.user_message}")
        records = result.data if isinstance(result.data, list) else []
        for record in records:
            if isinstance(record, dict) and record.get("name"):
                names.add(str(record["name"]))
        if len(records) < limit:
            break
        offset += limit
    return names


def choose_item_group_root(existing_item_groups: set[str]) -> str:
    for candidate in ITEM_GROUP_ROOT_CANDIDATES:
        if candidate in existing_item_groups:
            return candidate
    return next(iter(sorted(existing_item_groups)), "所有物料群组")


def build_item_group_name_map(rows: list[dict[str, str]], existing_item_groups: set[str]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    used = set(existing_item_groups)
    for row in rows:
        source = clean_text(row["标准分组"])
        if not source:
            source = "未分类物料"
        if source in mapped:
            continue
        candidates = [source, source.replace("/", " - ")]
        target = next((name for name in candidates if name in existing_item_groups), candidates[0])
        if target not in used:
            used.add(target)
        mapped[source] = target
    return mapped


def ensure_uoms(
    client: ERPNextClient,
    rows: list[dict[str, str]],
    existing_uoms: set[str],
    apply: bool,
    events: list[ImportEvent],
) -> None:
    units = sorted({clean_text(row["标准单位"]) or "个" for row in rows})
    for unit in units:
        if unit in existing_uoms:
            events.append(ImportEvent("skip_existing", "UOM", unit, True, "already exists"))
            continue
        if not apply:
            events.append(ImportEvent("dry_run_create", "UOM", unit, True, "would create"))
            continue

        doc = {
            "doctype": "UOM",
            "uom_name": unit,
            "enabled": 1,
            "must_be_whole_number": 1 if unit in WHOLE_NUMBER_UOMS else 0,
        }
        result = client.create_document("UOM", doc)
        if result.ok:
            existing_uoms.add(unit)
            events.append(ImportEvent("create", "UOM", unit, True, "created"))
        else:
            events.append(
                ImportEvent(
                    "create",
                    "UOM",
                    unit,
                    False,
                    result.user_message or "",
                    result.error_type or "",
                    result.error or "",
                )
            )


def ensure_item_groups(
    client: ERPNextClient,
    group_name_map: dict[str, str],
    existing_item_groups: set[str],
    root_group: str,
    apply: bool,
    events: list[ImportEvent],
) -> None:
    for source_group, target_group in sorted(group_name_map.items(), key=lambda item: item[1]):
        if target_group in existing_item_groups:
            events.append(ImportEvent("skip_existing", "Item Group", target_group, True, "already exists"))
            continue
        if not apply:
            events.append(ImportEvent("dry_run_create", "Item Group", target_group, True, f"would create for {source_group}"))
            continue

        doc = {
            "doctype": "Item Group",
            "item_group_name": target_group,
            "parent_item_group": root_group,
            "is_group": 0,
        }
        result = client.create_document("Item Group", doc)
        if result.ok:
            existing_item_groups.add(target_group)
            events.append(ImportEvent("create", "Item Group", target_group, True, "created"))
            continue

        fallback = source_group.replace("/", " - ")
        if fallback != target_group and fallback not in existing_item_groups:
            fallback_doc = dict(doc)
            fallback_doc["item_group_name"] = fallback
            fallback_result = client.create_document("Item Group", fallback_doc)
            if fallback_result.ok:
                group_name_map[source_group] = fallback
                existing_item_groups.add(fallback)
                events.append(
                    ImportEvent(
                        "create",
                        "Item Group",
                        fallback,
                        True,
                        f"created fallback for {source_group}",
                    )
                )
                continue
            result = fallback_result
            target_group = fallback

        events.append(
            ImportEvent(
                "create",
                "Item Group",
                target_group,
                False,
                result.user_message or "",
                result.error_type or "",
                result.error or "",
            )
        )


def import_items(
    client: ERPNextClient,
    rows: list[dict[str, str]],
    item_fields: set[str],
    existing_items: set[str],
    group_name_map: dict[str, str],
    apply: bool,
    update_existing: bool,
    events: list[ImportEvent],
) -> None:
    total = len(rows)
    for index, row in enumerate(rows, start=1):
        item_code = row["draft_item_code"]
        if not item_code:
            events.append(ImportEvent("skip_invalid", "Item", "", False, error_type="missing_argument", error="draft_item_code is blank"))
            continue

        doc = build_item_doc(row, item_fields, group_name_map)
        if item_code in existing_items and not update_existing:
            events.append(ImportEvent("skip_existing", "Item", item_code, True, "already exists"))
        elif not apply:
            action = "dry_run_update" if item_code in existing_items else "dry_run_create"
            events.append(ImportEvent(action, "Item", item_code, True, "would write"))
        elif item_code in existing_items:
            result = client.update_document("Item", item_code, doc)
            append_write_event(events, "update", "Item", item_code, result)
        else:
            result = client.create_document("Item", doc)
            append_write_event(events, "create", "Item", item_code, result)
            if result.ok:
                existing_items.add(item_code)

        if index % 100 == 0 or index == total:
            print(f"Processed Items: {index}/{total}")


def build_item_doc(
    row: dict[str, str],
    item_fields: set[str],
    group_name_map: dict[str, str],
) -> dict[str, Any]:
    item_code = row["draft_item_code"]
    standard_name = clean_text(row["标准名称"]) or item_code
    required_specs = clean_text(row["必填规格"])
    optional_specs = clean_text(row["辅助规格"])
    aliases = clean_text(row["别名/土名"])
    source_group = clean_text(row["标准分组"]) or "未分类物料"
    item_group = group_name_map.get(source_group, source_group)
    stock_uom = clean_text(row["标准单位"]) or "个"

    doc: dict[str, Any] = {
        "doctype": "Item",
        "item_code": item_code,
        "item_name": clamp(standard_name, 140),
        "item_group": item_group,
        "stock_uom": stock_uom,
        "disabled": 0,
        "is_stock_item": 1,
        "is_purchase_item": 1,
        "is_sales_item": 0,
        "include_item_in_manufacturing": 0,
        "description": build_description(row, item_group),
    }

    optional_field_values = {
        "specification": clamp(join_parts(required_specs, optional_specs), 140),
        "raw_name": clamp(aliases or standard_name, 140),
        "alias_names": aliases,
    }
    for fieldname, value in optional_field_values.items():
        if fieldname in item_fields and value:
            doc[fieldname] = value

    return {key: value for key, value in doc.items() if value not in (None, "")}


def build_description(row: dict[str, str], item_group: str) -> str:
    fields = [
        ("SKU 草案编号", row["draft_sku_id"]),
        ("标准编码", row["draft_item_code"]),
        ("标准名称", row["标准名称"]),
        ("必填规格", row["必填规格"]),
        ("辅助规格", row["辅助规格"]),
        ("标准分组", item_group),
        ("标准单位", row["标准单位"]),
        ("别名/土名", row["别名/土名"]),
        ("放行等级", row["放行等级"]),
        ("草案状态", row["release_status"]),
        ("导入决策", row.get("import_decision", "")),
        ("整理依据", row.get("整理依据", "")),
        ("来源候选行", row.get("source_candidate_rows", "")),
        ("来源采购行", row.get("source_file_rows", "")),
    ]
    list_items = []
    for label, value in fields:
        value = clean_text(value)
        if value:
            list_items.append(f"<li><strong>{escape(label)}：</strong>{escape(value)}</li>")
    return "<p><strong>Agent 物料主数据草案导入</strong></p><ul>" + "".join(list_items) + "</ul>"


def append_write_event(
    events: list[ImportEvent],
    action: str,
    doctype: str,
    name: str,
    result: Any,
) -> None:
    if result.ok:
        events.append(ImportEvent(action, doctype, name, True, f"{action}d"))
        return
    events.append(
        ImportEvent(
            action,
            doctype,
            name,
            False,
            result.user_message or "",
            result.error_type or "",
            result.error or "",
        )
    )


def build_summary(
    args: argparse.Namespace,
    all_rows: list[dict[str, str]],
    selected_rows: list[dict[str, str]],
    events: list[ImportEvent],
    started: float,
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    failed_total = 0
    for event in events:
        key = f"{event.action}_{event.doctype}".replace(" ", "_").lower()
        counts[key] = counts.get(key, 0) + 1
        if not event.ok:
            failed_total += 1

    return {
        "mode": "apply" if args.apply else "dry_run",
        "profile": args.profile,
        "input": str(args.input),
        "total_input_rows": len(all_rows),
        "selected_rows": len(selected_rows),
        "offset": args.offset,
        "limit": args.limit,
        "update_existing": args.update_existing,
        "duration_seconds": round(monotonic() - started, 3),
        "failed_total": failed_total,
        "counts": counts,
        "report_json": str(args.report_json),
        "report_tsv": str(args.report_tsv),
    }


def write_reports(
    json_path: Path,
    tsv_path: Path,
    events: list[ImportEvent],
    summary: dict[str, Any],
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    tsv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps({"summary": summary, "events": [asdict(event) for event in events]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with tsv_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = list(ImportEvent.__dataclass_fields__.keys())
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for event in events:
            writer.writerow(asdict(event))


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\ufeff", "").strip()


def clamp(value: str, length: int) -> str:
    value = clean_text(value)
    if len(value) <= length:
        return value
    return value[: length - 1] + "…"


def join_parts(*values: str) -> str:
    return "；".join(value for value in (clean_text(value) for value in values) if value)


def print_result(name: str, ok: bool, message: str) -> None:
    status = "OK" if ok else "FAILED"
    print(f"{name}: {status} {message}".strip())


if __name__ == "__main__":
    raise SystemExit(main())
