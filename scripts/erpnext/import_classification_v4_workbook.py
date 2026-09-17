"""Import the user-provided Longhua V4 classification workbook into an isolated ERPNext Site.

The workbook is a classification/master-data release, not a set of transactions.  This
script therefore imports UOMs, a browsable Item Group hierarchy, and one ERPNext Item per
standard specification variant.  Historical purchase rows and raw-name mappings are kept
in the immutable source workbook and in the local JSON report; they are never fabricated
as ERPNext purchase documents.

The target is intentionally fixed to ``material-classification-v4.localhost`` so this
utility cannot accidentally write the existing material-test or civil Site.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid
from typing import Any, Iterable, Mapping
from urllib.parse import quote
import zipfile
import xml.etree.ElementTree as ET

import requests


ROOT = Path(__file__).resolve().parents[2]
TARGET_SITE = "material-classification-v4.localhost"
BASE_URL = "http://localhost:8004"
DEFAULT_SECRET_PATH = ROOT / ".secrets" / "erpnext-material-classification-v4" / "site-secrets.json"
DEFAULT_INPUT = Path.home() / "Downloads" / "龙华项目公司标准物料示范清单_第四轮附件治理.xlsx"
DEFAULT_RUNTIME_ROOT = ROOT / ".runtime" / "erpnext-material-classification-v4"
DEFAULT_REPORT_PATH = DEFAULT_RUNTIME_ROOT / "classification-v4-import-report.json"
DEFAULT_JOURNAL_PATH = DEFAULT_RUNTIME_ROOT / "classification-v4-import-journal.json"
ITEM_GROUP_ROOT = "分类示范 V4"
COMPANY_NAME = "Nexterp分类示范有限公司"
COMPANY_ABBR = "NCV"
SOURCE_VERSION = "龙华项目公司标准物料示范清单_V4"

CUSTOM_FIELDS: tuple[dict[str, Any], ...] = (
    {"fieldname": "custom_nexterp_v4_family_code", "label": "V4物料族编码", "fieldtype": "Data"},
    {"fieldname": "custom_nexterp_v4_family_name", "label": "V4物料族", "fieldtype": "Data"},
    {"fieldname": "custom_nexterp_v4_category_l1", "label": "V4一级分类", "fieldtype": "Data"},
    {"fieldname": "custom_nexterp_v4_category_l2", "label": "V4二级分类", "fieldtype": "Data"},
    {"fieldname": "custom_nexterp_v4_procurement_type", "label": "V4采购类型", "fieldtype": "Data"},
    {"fieldname": "custom_nexterp_v4_source_workbook", "label": "V4来源工作簿", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "custom_nexterp_v4_source_sheet", "label": "V4来源工作表", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "custom_nexterp_v4_source_row", "label": "V4来源行号", "fieldtype": "Int", "read_only": 1},
    {"fieldname": "custom_nexterp_v4_source_row_hash", "label": "V4来源行哈希", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "custom_nexterp_v4_release_hash", "label": "V4发布哈希", "fieldtype": "Data", "read_only": 1},
    {"fieldname": "custom_nexterp_v4_attributes_json", "label": "V4规格属性", "fieldtype": "Long Text", "read_only": 1},
)

WHOLE_NUMBER_UOMS = {
    "个", "只", "件", "套", "把", "根", "支", "张", "包", "盒", "桶", "瓶", "块",
    "卷", "台", "双", "付", "副", "条", "本", "袋", "片", "盘", "组", "节", "辆", "部",
}


class ImportError(RuntimeError):
    """Raised when the workbook or target Site cannot be proven safe to import."""


def _text(value: Any) -> str:
    return ("" if value is None else str(value)).replace("\ufeff", "").strip()


def _canonical(value: Any) -> str:
    # openpyxl exposes date cells as datetime objects; stringify only values
    # that are not JSON-native so the source hash remains deterministic.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: Any) -> str:
    raw = value if isinstance(value, (bytes, bytearray)) else _canonical(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass(frozen=True)
class WorkbookData:
    source_path: str
    source_workbook: str
    source_hash: str
    release_hash: str
    families: list[dict[str, Any]]
    variants: list[dict[str, Any]]
    categories: list[dict[str, Any]]
    units: list[dict[str, Any]]
    procurement_rows: list[dict[str, Any]]
    alias_rows: list[dict[str, Any]]

    @property
    def counts(self) -> dict[str, int]:
        return {
            "family_count": len(self.families),
            "variant_count": len(self.variants),
            "category_count": len(self.categories),
            "uom_count": len(self.units),
            "procurement_row_count": len(self.procurement_rows),
            "alias_row_count": len(self.alias_rows),
        }


XLSX_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def _column_index(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha())
    index = 0
    for character in letters.upper():
        index = index * 26 + ord(character) - ord("A") + 1
    return index - 1


def _read_xlsx_sheets(path: Path) -> dict[str, list[list[Any]]]:
    """Read cell values with the stdlib so the importer works in the project venv."""
    with zipfile.ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {node.attrib["Id"]: node.attrib["Target"] for node in relationships}
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(text.text or "" for text in item.iter("{%s}t" % XLSX_NS["main"])) for item in root]
        result: dict[str, list[list[Any]]] = {}
        for sheet in workbook.find("main:sheets", XLSX_NS):
            sheet_name = sheet.attrib["name"]
            target = targets[sheet.attrib["{%s}id" % XLSX_NS["r"]]]
            worksheet_path = target.lstrip("/") if target.startswith("/") else (target if target.startswith("xl/") else "xl/" + target)
            root = ET.fromstring(archive.read(worksheet_path))
            rows: list[list[Any]] = []
            for row in root.findall(".//main:sheetData/main:row", XLSX_NS):
                cells: dict[int, Any] = {}
                for cell in row.findall("main:c", XLSX_NS):
                    ref = cell.attrib.get("r", "")
                    index = _column_index(ref)
                    cell_type = cell.attrib.get("t")
                    value_node = cell.find("main:v", XLSX_NS)
                    value = ""
                    if cell_type == "inlineStr":
                        value = "".join(text.text or "" for text in cell.findall(".//main:t", XLSX_NS))
                    elif cell_type == "s" and value_node is not None:
                        value = shared[int(value_node.text or "0")]
                    elif value_node is not None:
                        value = value_node.text or ""
                    cells[index] = value
                width = max(cells, default=-1) + 1
                row_values = [cells.get(index, "") for index in range(width)]
                # Blank Excel rows are omitted from sheet XML.  Keep physical
                # row numbers so header_row/data_start refer to the workbook.
                row_number = int(row.attrib.get("r", len(rows) + 1))
                while len(rows) < row_number:
                    rows.append([])
                rows[row_number - 1] = row_values
            result[sheet_name] = rows
        return result


def _table(sheet_rows: list[list[Any]], *, header_row: int = 4, data_start: int = 5) -> list[dict[str, Any]]:
    header_values = sheet_rows[header_row - 1] if len(sheet_rows) >= header_row else []
    headers = [_text(value) for value in header_values]
    rows: list[dict[str, Any]] = []
    for excel_row, values in enumerate(sheet_rows[data_start - 1 :], start=data_start):
        if not any(value not in (None, "") for value in values):
            continue
        row = {headers[index]: (values[index] if index < len(values) else None) for index in range(len(headers)) if headers[index]}
        row["_source_row"] = excel_row
        rows.append(row)
    return rows


def _row_hash(row: Mapping[str, Any]) -> str:
    return _sha256({key: row[key] for key in sorted(row) if key != "_source_row"})


def load_workbook_data(path: Path) -> WorkbookData:
    if not path.is_file():
        raise ImportError(f"Workbook does not exist: {path}")
    source_bytes = path.read_bytes()
    workbook = _read_xlsx_sheets(path)
    required_sheets = {"标准物料主数据", "标准规格变体", "分类字典", "单位字典", "标准化采购流水", "原始名称映射"}
    missing_sheets = sorted(required_sheets - set(workbook))
    if missing_sheets:
        raise ImportError(f"Workbook is missing required sheets: {', '.join(missing_sheets)}")

    families = _table(workbook["标准物料主数据"])
    variants = _table(workbook["标准规格变体"])
    categories = _table(workbook["分类字典"])
    units = _table(workbook["单位字典"])
    procurement_rows = _table(workbook["标准化采购流水"])
    alias_rows = _table(workbook["原始名称映射"])

    _require_columns(families, "标准物料主数据", {"物料族编码", "一级分类", "二级分类", "物料族", "基本单位", "采购类型", "维护状态"})
    _require_columns(variants, "标准规格变体", {"规格变体编码", "物料族编码", "一级分类", "二级分类", "物料族", "采购类型", "基本单位", "标准物料名称", "状态"})
    _require_columns(categories, "分类字典", {"一级分类", "二级分类"})
    _require_columns(units, "单位字典", {"标准单位", "单位类型"})
    _require_columns(procurement_rows, "标准化采购流水", {"流水ID", "物料族编码", "规格变体编码", "标准单位"})
    _require_columns(alias_rows, "原始名称映射", {"原始材料名称", "物料族编码", "规格变体编码", "标准单位"})

    _assert_unique(families, "物料族编码", "标准物料主数据")
    _assert_unique(variants, "规格变体编码", "标准规格变体")
    family_codes = {_text(row["物料族编码"]) for row in families}
    missing_parents = sorted({_text(row["物料族编码"]) for row in variants} - family_codes)
    if missing_parents:
        raise ImportError(f"Variants reference missing families: {missing_parents[:10]}")
    if any(_text(row["维护状态"]) != "启用" for row in families):
        raise ImportError("标准物料主数据 contains non-enabled families")
    if any(_text(row["状态"]) != "启用" for row in variants):
        raise ImportError("标准规格变体 contains non-enabled variants")

    # Make source identity explicit on every imported variant.  Excel row number alone
    # is not treated as an identity; the workbook name/sheet/row/hash are all retained.
    source_workbook = path.name
    for row in variants:
        row["source_workbook"] = source_workbook
        row["source_sheet"] = "标准规格变体"
        row["source_row"] = int(row.pop("_source_row"))
        row["source_row_hash"] = _row_hash(row)
    # Other tables are also normalized into the release hash/report, but are not
    # written as ERPNext transaction documents.
    for collection, sheet in ((families, "标准物料主数据"), (categories, "分类字典"), (units, "单位字典"), (procurement_rows, "标准化采购流水"), (alias_rows, "原始名称映射")):
        for row in collection:
            row["source_sheet"] = sheet
            row["source_row"] = int(row.pop("_source_row"))
            row["source_row_hash"] = _row_hash(row)
    release_payload = {
        "source_workbook": source_workbook,
        "source_hash": _sha256(source_bytes),
        "families": families,
        "variants": variants,
        "categories": categories,
        "units": units,
        "procurement_rows": procurement_rows,
        "alias_rows": alias_rows,
    }
    return WorkbookData(
        source_path=str(path.resolve()),
        source_workbook=source_workbook,
        source_hash=release_payload["source_hash"],
        release_hash=_sha256(release_payload),
        families=families,
        variants=variants,
        categories=categories,
        units=units,
        procurement_rows=procurement_rows,
        alias_rows=alias_rows,
    )


def _require_columns(rows: list[dict[str, Any]], sheet: str, required: set[str]) -> None:
    actual = set(rows[0]) if rows else set()
    missing = sorted(required - actual)
    if missing:
        raise ImportError(f"{sheet} is missing columns: {', '.join(missing)}")


def _assert_unique(rows: Iterable[Mapping[str, Any]], column: str, sheet: str) -> None:
    values = [_text(row.get(column)) for row in rows]
    blank = sum(not value for value in values)
    duplicates = sorted(value for value, count in Counter(values).items() if value and count > 1)
    if blank or duplicates:
        raise ImportError(f"{sheet} has invalid {column}: blank={blank}, duplicates={duplicates[:10]}")


class FrappeClient:
    def __init__(self, secret_path: Path) -> None:
        if not secret_path.is_file():
            raise ImportError(f"Site secret file does not exist: {secret_path}")
        secrets = json.loads(secret_path.read_text(encoding="utf-8-sig"))
        if secrets.get("site") != TARGET_SITE or not secrets.get("admin_password"):
            raise ImportError("Classification Site secret file is incomplete or belongs to another Site")
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", "Host": TARGET_SITE})
        self.admin_password = str(secrets["admin_password"])
        self.login()

    def login(self) -> None:
        response = self.session.post(
            f"{BASE_URL}/api/method/login",
            data={"usr": "Administrator", "pwd": self.admin_password},
            timeout=60,
        )
        self._raise(response, "login")

    def list_docs(self, doctype: str, *, fields: list[str], filters: list[Any] | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            response = self.session.get(
                f"{BASE_URL}/api/resource/{quote(doctype, safe='')}",
                params={
                    "fields": json.dumps(fields, ensure_ascii=False),
                    "filters": json.dumps(filters or [], ensure_ascii=False),
                    "limit_page_length": 500,
                    "limit_start": offset,
                },
                timeout=60,
            )
            self._raise(response, f"list {doctype}")
            batch = list(response.json().get("data") or [])
            rows.extend(batch)
            if len(batch) < 500:
                return rows
            offset += len(batch)

    def get_doc(self, doctype: str, name: str) -> dict[str, Any] | None:
        response = self.session.get(
            f"{BASE_URL}/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}",
            timeout=60,
        )
        if response.status_code == 404:
            return None
        self._raise(response, f"get {doctype} {name}")
        return response.json().get("data") or {}

    def create_doc(self, doctype: str, document: Mapping[str, Any]) -> dict[str, Any]:
        response = self.session.post(
            f"{BASE_URL}/api/resource/{quote(doctype, safe='')}",
            json=dict(document),
            timeout=60,
        )
        self._raise(response, f"create {doctype}")
        return response.json().get("data") or {}

    def update_doc(self, doctype: str, name: str, document: Mapping[str, Any]) -> dict[str, Any]:
        response = self.session.put(
            f"{BASE_URL}/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}",
            json=dict(document),
            timeout=60,
        )
        self._raise(response, f"update {doctype} {name}")
        return response.json().get("data") or {}

    @staticmethod
    def _raise(response: requests.Response, operation: str) -> None:
        if response.ok:
            return
        try:
            payload: Any = response.json()
        except ValueError:
            payload = response.text[:1000]
        raise ImportError(f"ERPNext {operation} failed ({response.status_code}): {payload}")


def _custom_field_doc(definition: Mapping[str, Any], index: int) -> dict[str, Any]:
    insert_after = "description" if index == 0 else CUSTOM_FIELDS[index - 1]["fieldname"]
    return {
        "dt": "Item",
        "fieldname": definition["fieldname"],
        "label": definition["label"],
        "fieldtype": definition["fieldtype"],
        "insert_after": insert_after,
        "read_only": int(definition.get("read_only", 0)),
        "no_copy": 1,
        "allow_on_submit": 0,
    }


def ensure_schema(client: FrappeClient) -> dict[str, Any]:
    result = {"warehouse_type": "existing", "company": "existing", "root_item_group": "existing", "custom_fields": {"created": 0, "existing": 0}}
    # ERPNext's Company on_update creates default warehouses and validates their
    # warehouse type.  Seed the standard Transit type first so a first-run import
    # cannot fail halfway through company initialization.
    if client.get_doc("Warehouse Type", "Transit") is None:
        client.create_doc("Warehouse Type", {"name": "Transit"})
        result["warehouse_type"] = "created"
    if client.get_doc("Company", COMPANY_NAME) is None:
        client.create_doc("Company", {"company_name": COMPANY_NAME, "abbr": COMPANY_ABBR, "default_currency": "CNY", "country": "China", "is_group": 0})
        result["company"] = "created"
    if client.get_doc("Item Group", "All Item Groups") is None:
        client.create_doc("Item Group", {"item_group_name": "All Item Groups", "is_group": 1})
        result["root_item_group"] = "created"
    for index, definition in enumerate(CUSTOM_FIELDS):
        name = f"Item-{definition['fieldname']}"
        expected = _custom_field_doc(definition, index)
        actual = client.get_doc("Custom Field", name)
        if actual is None:
            client.create_doc("Custom Field", expected)
            result["custom_fields"]["created"] += 1
            continue
        mismatches = {key: (actual.get(key), value) for key, value in expected.items() if _text(actual.get(key)) != _text(value)}
        if mismatches:
            raise ImportError(f"Custom Field {name} conflicts with required schema: {mismatches}")
        result["custom_fields"]["existing"] += 1
    return result


def family_group_name(row: Mapping[str, Any]) -> str:
    return f"{_text(row['物料族编码'])} · {_text(row['物料族'])}"[:140]


def category_group_name(value: str) -> str:
    return _text(value)[:140]


def build_group_plan(data: WorkbookData) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = [{"item_group_name": ITEM_GROUP_ROOT, "parent_item_group": "All Item Groups", "is_group": 1, "kind": "root"}]
    top_names: set[str] = set()
    for row in data.families:
        top = category_group_name(row["一级分类"])
        second = category_group_name(row["二级分类"])
        if top not in top_names:
            groups.append({"item_group_name": top, "parent_item_group": ITEM_GROUP_ROOT, "is_group": 1, "kind": "category_l1"})
            top_names.add(top)
        second_key = (top, second)
        if not any(group.get("kind") == "category_l2" and group["item_group_name"] == second and group["parent_item_group"] == top for group in groups):
            groups.append({"item_group_name": second, "parent_item_group": top, "is_group": 1, "kind": "category_l2"})
        group_name = family_group_name(row)
        groups.append({"item_group_name": group_name, "parent_item_group": second, "is_group": 1, "kind": "family", "family_code": _text(row["物料族编码"])})
    # Frappe names are globally unique, so detect a family/category collision
    # before any write.  A collision is safer than silently suffixing a label.
    seen: dict[str, dict[str, Any]] = {}
    for group in groups:
        name = group["item_group_name"]
        if name in seen and (seen[name]["parent_item_group"], seen[name]["kind"]) != (group["parent_item_group"], group["kind"]):
            raise ImportError(f"Item Group name collision: {name}")
        seen[name] = group
    return groups


def build_item_doc(variant: Mapping[str, Any], family_by_code: Mapping[str, Mapping[str, Any]], release_hash: str) -> dict[str, Any]:
    family = family_by_code[_text(variant["物料族编码"])]
    procurement_type = _text(variant.get("采购类型")) or _text(family.get("采购类型")) or "标准品"
    service = procurement_type == "服务" or _text(family.get("采购类型")) == "服务"
    attributes = {
        "品牌": _text(variant.get("品牌")),
        "主规格/型号": _text(variant.get("主规格/型号")),
        "材质": _text(variant.get("材质")),
        "强度/等级": _text(variant.get("强度/等级")),
        "表面处理/颜色": _text(variant.get("表面处理/颜色")),
        "型式/功能": _text(variant.get("型式/功能")),
        "包装规格": _text(variant.get("包装规格")),
    }
    attributes = {key: value for key, value in attributes.items() if value}
    source_identity = {
        "source_dataset": SOURCE_VERSION,
        "source_document": _text(variant["source_workbook"]),
        "source_sheet": _text(variant["source_sheet"]),
        "source_row": int(variant["source_row"]),
        "source_row_hash": _text(variant["source_row_hash"]),
    }
    description_parts = [
        f"<p><strong>{_text(variant['标准物料名称'])}</strong></p>",
        f"<p>物料族：{_text(family['物料族编码'])} · {_text(family['物料族'])}<br>",
        f"分类：{_text(variant['一级分类'])} / {_text(variant['二级分类'])}<br>",
        f"采购类型：{procurement_type}<br>基本单位：{_text(variant['基本单位'])}</p>",
        f"<p>来源身份：{json.dumps(source_identity, ensure_ascii=False, sort_keys=True)}</p>",
    ]
    if attributes:
        description_parts.append("<p>规格属性：" + "；".join(f"{key}={value}" for key, value in attributes.items()) + "</p>")
    return {
        "doctype": "Item",
        "item_code": _text(variant["规格变体编码"]),
        "item_name": _text(variant["标准物料名称"])[:140],
        "item_group": family_group_name(family),
        "stock_uom": _text(variant["基本单位"]) or "个",
        "disabled": 0,
        "is_stock_item": 0 if service else 1,
        "is_purchase_item": 1,
        "is_sales_item": 0,
        "include_item_in_manufacturing": 0,
        "description": "".join(description_parts),
        "custom_nexterp_v4_family_code": _text(family["物料族编码"]),
        "custom_nexterp_v4_family_name": _text(family["物料族"]),
        "custom_nexterp_v4_category_l1": _text(variant["一级分类"]),
        "custom_nexterp_v4_category_l2": _text(variant["二级分类"]),
        "custom_nexterp_v4_procurement_type": procurement_type,
        "custom_nexterp_v4_source_workbook": _text(variant["source_workbook"]),
        "custom_nexterp_v4_source_sheet": _text(variant["source_sheet"]),
        "custom_nexterp_v4_source_row": int(variant["source_row"]),
        "custom_nexterp_v4_source_row_hash": _text(variant["source_row_hash"]),
        "custom_nexterp_v4_release_hash": release_hash,
        "custom_nexterp_v4_attributes_json": json.dumps(attributes, ensure_ascii=False, sort_keys=True),
    }


def target_plan(client: FrappeClient, data: WorkbookData) -> dict[str, Any]:
    # The plan command must work before the custom fields are created.  Read the
    # stable Item identity first, then read managed fields only for collisions.
    existing_items = {row.get("name"): row for row in client.list_docs("Item", fields=["name", "item_code"])}
    for code, row in list(existing_items.items()):
        if code:
            detail = client.get_doc("Item", str(code))
            if detail:
                existing_items[code] = detail
    existing_groups = {row.get("name") for row in client.list_docs("Item Group", fields=["name"])}
    existing_uoms = {row.get("name") for row in client.list_docs("UOM", fields=["name"])}
    groups = build_group_plan(data)
    summary = {"groups_create": 0, "groups_existing": 0, "uoms_create": 0, "uoms_existing": 0, "items_create": 0, "items_unchanged": 0, "items_update": 0, "conflict": 0}
    conflicts: list[dict[str, Any]] = []
    for group in groups:
        if group["item_group_name"] in existing_groups:
            summary["groups_existing"] += 1
        else:
            summary["groups_create"] += 1
    for row in data.units:
        unit = _text(row["标准单位"])
        if unit in existing_uoms:
            summary["uoms_existing"] += 1
        else:
            summary["uoms_create"] += 1
    for variant in data.variants:
        code = _text(variant["规格变体编码"])
        existing = existing_items.get(code)
        if existing is None:
            summary["items_create"] += 1
        elif _text(existing.get("custom_nexterp_v4_source_row_hash")) != _text(variant["source_row_hash"]):
            summary["conflict"] += 1
            conflicts.append({"item_code": code, "expected_source_row_hash": variant["source_row_hash"], "actual_source_row_hash": existing.get("custom_nexterp_v4_source_row_hash")})
        elif _text(existing.get("custom_nexterp_v4_release_hash")) == data.release_hash:
            summary["items_unchanged"] += 1
        else:
            summary["items_update"] += 1
    return {"summary": summary, "conflicts": conflicts, "managed_existing_items": len(existing_items), "group_count": len(groups)}


def _ensure_uoms(client: FrappeClient, data: WorkbookData) -> dict[str, int]:
    existing = {row.get("name") for row in client.list_docs("UOM", fields=["name"])}
    counts = {"created": 0, "existing": 0}
    for row in data.units:
        name = _text(row["标准单位"])
        if not name:
            continue
        if name in existing:
            counts["existing"] += 1
            continue
        client.create_doc("UOM", {"uom_name": name, "enabled": 1, "must_be_whole_number": 1 if name in WHOLE_NUMBER_UOMS else 0})
        existing.add(name)
        counts["created"] += 1
    return counts


def _ensure_groups(client: FrappeClient, groups: list[dict[str, Any]]) -> dict[str, int]:
    existing = {row.get("name") for row in client.list_docs("Item Group", fields=["name"])}
    counts = {"created": 0, "existing": 0}
    for group in groups:
        name = group["item_group_name"]
        if name in existing:
            counts["existing"] += 1
            continue
        client.create_doc("Item Group", {"item_group_name": name, "parent_item_group": group["parent_item_group"], "is_group": group["is_group"]})
        existing.add(name)
        counts["created"] += 1
    return counts


def apply_import(client: FrappeClient, data: WorkbookData, *, request_id: str, journal_path: Path) -> dict[str, Any]:
    try:
        uuid.UUID(request_id)
    except ValueError as exc:
        raise ImportError("request_id must be a UUID") from exc
    journal = json.loads(journal_path.read_text(encoding="utf-8")) if journal_path.is_file() else {"schema_version": 1, "requests": {}}
    previous = journal.get("requests", {}).get(request_id)
    if previous:
        if previous.get("release_hash") != data.release_hash:
            raise ImportError("request_id was already used for a different workbook release")
        if previous.get("status") == "verified":
            return dict(previous["result"])
    family_by_code = {_text(row["物料族编码"]): row for row in data.families}
    ensure_schema(client)
    # The schema is now guaranteed to exist, so subsequent reads can include
    # the source identity fields used for idempotency.
    plan = target_plan(client, data)
    if plan["summary"]["conflict"]:
        raise ImportError(f"Target contains source-row conflicts: {plan['conflicts'][:10]}")
    uom_result = _ensure_uoms(client, data)
    group_result = _ensure_groups(client, build_group_plan(data))
    existing_items = {row.get("name"): row for row in client.list_docs("Item", fields=["name", "custom_nexterp_v4_source_row_hash", "custom_nexterp_v4_release_hash"])}
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    for index, variant in enumerate(data.variants, start=1):
        code = _text(variant["规格变体编码"])
        doc = build_item_doc(variant, family_by_code, data.release_hash)
        existing = existing_items.get(code)
        if existing and _text(existing.get("custom_nexterp_v4_source_row_hash")) == _text(variant["source_row_hash"]) and _text(existing.get("custom_nexterp_v4_release_hash")) == data.release_hash:
            counts["unchanged"] += 1
        elif existing:
            client.update_doc("Item", code, doc)
            counts["updated"] += 1
        else:
            client.create_doc("Item", doc)
            counts["created"] += 1
        if index % 50 == 0 or index == len(data.variants):
            print(f"Processed V4 variants: {index}/{len(data.variants)}")
    result = {
        "site": TARGET_SITE,
        "request_id": request_id,
        "release_hash": data.release_hash,
        "source_workbook": data.source_workbook,
        "source_hash": data.source_hash,
        "counts": data.counts,
        "uoms": uom_result,
        "item_groups": group_result,
        "items": counts,
        "historical_rows_imported_as_transactions": 0,
        "verified_at": _now(),
    }
    verification = verify_import(client, data)
    if not verification["verified"]:
        raise ImportError(f"Post-import verification failed: {verification}")
    result["verification"] = verification
    journal.setdefault("requests", {})[request_id] = {"status": "verified", "release_hash": data.release_hash, "result": result}
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.write_text(json.dumps(journal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def verify_import(client: FrappeClient, data: WorkbookData) -> dict[str, Any]:
    family_by_code = {_text(row["物料族编码"]): row for row in data.families}
    missing: list[str] = []
    mismatches: list[dict[str, Any]] = []
    for group in build_group_plan(data):
        if client.get_doc("Item Group", group["item_group_name"]) is None:
            missing.append(f"Item Group:{group['item_group_name']}")
    for row in data.units:
        if client.get_doc("UOM", _text(row["标准单位"])) is None:
            missing.append(f"UOM:{row['标准单位']}")
    for variant in data.variants:
        code = _text(variant["规格变体编码"])
        actual = client.get_doc("Item", code)
        if actual is None:
            missing.append(f"Item:{code}")
            continue
        expected = build_item_doc(variant, family_by_code, data.release_hash)
        for key in ("item_code", "item_name", "item_group", "stock_uom", "is_stock_item", "custom_nexterp_v4_family_code", "custom_nexterp_v4_source_row", "custom_nexterp_v4_source_row_hash", "custom_nexterp_v4_release_hash"):
            if _text(actual.get(key)) != _text(expected.get(key)):
                mismatches.append({"item_code": code, "field": key, "actual": actual.get(key), "expected": expected.get(key)})
    return {"verified": not missing and not mismatches, "missing_count": len(missing), "mismatch_count": len(mismatches), "missing": missing[:20], "mismatches": mismatches[:20], "checked_variants": len(data.variants)}


def write_report(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "apply", "verify"))
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--secret-file", type=Path, default=DEFAULT_SECRET_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL_PATH)
    parser.add_argument("--request-id")
    parser.add_argument("--confirm-release-hash")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        data = load_workbook_data(args.input)
        client = FrappeClient(args.secret_file)
        if args.action == "plan":
            payload = {"action": "plan", "site": TARGET_SITE, "source": asdict(data), "target": target_plan(client, data)}
            payload["source"].pop("families", None)
            payload["source"].pop("variants", None)
            payload["source"].pop("categories", None)
            payload["source"].pop("units", None)
            payload["source"].pop("procurement_rows", None)
            payload["source"].pop("alias_rows", None)
            write_report(args.report, payload)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0 if not payload["target"]["summary"]["conflict"] else 2
        if args.action == "verify":
            verification = verify_import(client, data)
            payload = {"action": "verify", "site": TARGET_SITE, "release_hash": data.release_hash, "source_counts": data.counts, "verification": verification}
            write_report(args.report, payload)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0 if verification["verified"] else 3
        if not args.request_id:
            raise ImportError("apply requires --request-id")
        if args.confirm_release_hash != data.release_hash:
            raise ImportError("apply requires --confirm-release-hash matching the current plan")
        result = apply_import(client, data, request_id=args.request_id, journal_path=args.journal)
        write_report(args.report, {"action": "apply", **result})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ImportError, requests.RequestException, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
