"""Initialize and synchronize the reviewed GPC material catalog to a test Site.

This command intentionally targets only the fixed local material test Site.  It
uses Frappe REST resources, explicit release confirmation and post-write
readback; it never writes directly to the ERPNext/MariaDB database.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping
from urllib.parse import quote
import uuid

import requests


ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from nexterp_agent.item_master.erpnext_material_release import (  # noqa: E402
    DEFAULT_ITEM_CODE_MAP_PATH,
    DEFAULT_RELEASE_ROOT,
    ERP_ROOT_ITEM_GROUP,
    ITEM_CUSTOM_FIELDS,
    MaterialReleaseError,
    build_material_release,
    write_material_release,
)
from nexterp_agent.item_master.reference_catalog_database import (  # noqa: E402
    DEFAULT_REFERENCE_CATALOG_DATABASE_PATH,
)


BASE_URL = "http://localhost:8003"
SITE_HOST = "material-test.localhost"
DEFAULT_SECRET_PATH = ROOT / ".secrets" / "erpnext-material-test" / "site-secrets.json"
DEFAULT_JOURNAL_PATH = ROOT / ".runtime" / "erpnext-material-test" / "sync-journal.json"
COMPANY_NAME = "Nexterp物料测试有限公司"
COMPANY_ABBR = "NMT"
TRANSACTION_DOCTYPES = (
    "Material Request",
    "Purchase Order",
    "Purchase Receipt",
    "Purchase Invoice",
    "Stock Entry",
    "Stock Ledger Entry",
    "Sales Invoice",
    "Payment Entry",
    "GL Entry",
)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class SyncError(RuntimeError):
    """Raised when a target write or readback cannot be proven correct."""


@dataclass
class FrappeSessionClient:
    base_url: str
    site_host: str
    username: str
    password: str

    def __post_init__(self) -> None:
        if self.base_url.rstrip("/") != BASE_URL:
            raise SyncError(f"Refusing non-test ERPNext URL: {self.base_url}")
        if self.site_host != SITE_HOST:
            raise SyncError(f"Refusing non-test ERPNext Site: {self.site_host}")
        self.base_url = self.base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Host": self.site_host, "Accept": "application/json"})

    def login(self) -> None:
        response = self.session.post(
            f"{self.base_url}/api/method/login",
            data={"usr": self.username, "pwd": self.password},
            timeout=30,
        )
        self._raise(response, "login")

    def method(
        self,
        dotted_path: str,
        payload: Mapping[str, Any] | None = None,
        *,
        http_method: str = "GET",
    ) -> Any:
        request = self.session.post if http_method.upper() == "POST" else self.session.get
        kwargs = {"json": dict(payload or {})} if http_method.upper() == "POST" else {"params": dict(payload or {})}
        response = request(f"{self.base_url}/api/method/{dotted_path}", timeout=30, **kwargs)
        self._raise(response, dotted_path)
        body = response.json()
        return body.get("message", body)

    def get_doc(self, doctype: str, name: str) -> dict[str, Any] | None:
        response = self.session.get(
            f"{self.base_url}/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}",
            timeout=30,
        )
        if response.status_code == 404:
            return None
        self._raise(response, f"get {doctype} {name}")
        return response.json().get("data")

    def list_docs(
        self,
        doctype: str,
        *,
        fields: Iterable[str],
        filters: list[Any] | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        response = self.session.get(
            f"{self.base_url}/api/resource/{quote(doctype, safe='')}",
            params={
                "fields": json.dumps(list(fields), ensure_ascii=False),
                "filters": json.dumps(filters or [], ensure_ascii=False),
                "limit_page_length": limit,
            },
            timeout=60,
        )
        self._raise(response, f"list {doctype}")
        return list(response.json().get("data") or [])

    def create_doc(self, doctype: str, document: Mapping[str, Any]) -> dict[str, Any]:
        response = self.session.post(
            f"{self.base_url}/api/resource/{quote(doctype, safe='')}",
            json=dict(document),
            timeout=60,
        )
        self._raise(response, f"create {doctype}")
        return response.json().get("data") or {}

    def update_doc(self, doctype: str, name: str, document: Mapping[str, Any]) -> dict[str, Any]:
        response = self.session.put(
            f"{self.base_url}/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}",
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
        raise SyncError(f"ERPNext {operation} failed ({response.status_code}): {payload}")


def _load_client(secret_path: Path) -> FrappeSessionClient:
    if not secret_path.is_file():
        raise SyncError(f"Site secret file does not exist: {secret_path}")
    secrets = json.loads(secret_path.read_text(encoding="utf-8-sig"))
    if secrets.get("site") != SITE_HOST or not secrets.get("admin_password"):
        raise SyncError("Material-test secret file is incomplete or belongs to another Site")
    client = FrappeSessionClient(
        base_url=BASE_URL,
        site_host=SITE_HOST,
        username="Administrator",
        password=str(secrets["admin_password"]),
    )
    client.login()
    return client


def _custom_field_doc(definition: Mapping[str, Any], index: int) -> dict[str, Any]:
    insert_after = "description" if index == 0 else ITEM_CUSTOM_FIELDS[index - 1]["fieldname"]
    return {
        "dt": "Item",
        "fieldname": definition["fieldname"],
        "label": definition["label"],
        "fieldtype": definition["fieldtype"],
        "insert_after": insert_after,
        "read_only": int(definition.get("read_only", 0)),
        "unique": int(definition.get("unique", 0)),
        "no_copy": 1,
        "allow_on_submit": 0,
    }


def initialize_target(client: FrappeSessionClient) -> dict[str, Any]:
    """Create only the minimal company and catalog-link schema."""

    result: dict[str, Any] = {
        "warehouse_type_transit": "existing",
        "root_item_group": "existing",
        "company": "existing",
        "custom_fields": {"created": 0, "existing": 0},
    }
    if client.get_doc("Warehouse Type", "Transit") is None:
        client.create_doc("Warehouse Type", {"name": "Transit"})
        result["warehouse_type_transit"] = "created"
    if client.get_doc("Item Group", "All Item Groups") is None:
        client.create_doc(
            "Item Group",
            {"item_group_name": "All Item Groups", "is_group": 1},
        )
        result["root_item_group"] = "created"
    if client.get_doc("Company", COMPANY_NAME) is None:
        client.create_doc(
            "Company",
            {
                "company_name": COMPANY_NAME,
                "abbr": COMPANY_ABBR,
                "default_currency": "CNY",
                "country": "China",
                "is_group": 0,
            },
        )
        result["company"] = "created"

    for index, definition in enumerate(ITEM_CUSTOM_FIELDS):
        name = f"Item-{definition['fieldname']}"
        existing = client.get_doc("Custom Field", name)
        if existing is None:
            client.create_doc("Custom Field", _custom_field_doc(definition, index))
            result["custom_fields"]["created"] += 1
        else:
            expected = _custom_field_doc(definition, index)
            mismatches = {
                key: (existing.get(key), value)
                for key, value in expected.items()
                if str(existing.get(key) or "") != str(value or "")
            }
            if set(mismatches) == {"insert_after"}:
                client.update_doc("Custom Field", name, {"insert_after": expected["insert_after"]})
                mismatches = {}
            if mismatches:
                raise SyncError(f"Custom Field {name} conflicts with the required schema: {mismatches}")
            result["custom_fields"]["existing"] += 1
    return result


def _erp_item(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "item_code": item["item_code"],
        "item_name": item["item_name"],
        "item_group": item["item_group"],
        "stock_uom": item["stock_uom"],
        "description": item["description"],
        "is_stock_item": 1,
        "include_item_in_manufacturing": 0,
        "is_purchase_item": 1,
        "is_sales_item": 0,
        "disabled": 0,
        "custom_nexterp_source_id": item["source_id"],
        "custom_nexterp_standard_type_code": item["standard_type_code"],
        "custom_nexterp_gpc_brick_code": item["gpc_brick_code"],
        "custom_nexterp_classification_source": item["classification_source"],
        "custom_nexterp_classification_path": item["classification_path"],
        "custom_nexterp_catalog_revision": item["catalog_revision"],
        "custom_nexterp_source_hash": item["source_hash"],
        "custom_nexterp_attributes_json": item["attributes_json"],
    }


def _verify_fields(actual: Mapping[str, Any], expected: Mapping[str, Any], keys: Iterable[str]) -> dict[str, Any]:
    mismatches = {}
    for key in keys:
        actual_value = actual.get(key)
        expected_value = expected.get(key)
        if str(actual_value if actual_value is not None else "") != str(
            expected_value if expected_value is not None else ""
        ):
            mismatches[key] = {"actual": actual_value, "expected": expected_value}
    return mismatches


def target_plan(client: FrappeSessionClient, release: Mapping[str, Any]) -> dict[str, Any]:
    existing_rows = client.list_docs(
        "Item",
        fields=[
            "item_code",
            "custom_nexterp_source_id",
            "custom_nexterp_source_hash",
            "disabled",
        ],
        filters=[["custom_nexterp_source_id", "!=", ""]],
        limit=1000,
    )
    by_code = {row["item_code"]: row for row in existing_rows}
    summary = {"create": 0, "update": 0, "unchanged": 0, "conflict": 0, "extra": 0}
    conflicts = []
    release_codes = {item["item_code"] for item in release["items"]}
    extras = sorted(code for code in by_code if code not in release_codes)
    summary["extra"] = len(extras)
    for item in release["items"]:
        existing = by_code.get(item["item_code"])
        if existing is None:
            summary["create"] += 1
        elif existing.get("custom_nexterp_source_id") != item["source_id"]:
            summary["conflict"] += 1
            conflicts.append(
                {
                    "item_code": item["item_code"],
                    "expected_source_id": item["source_id"],
                    "actual_source_id": existing.get("custom_nexterp_source_id"),
                }
            )
        elif existing.get("custom_nexterp_source_hash") == item["source_hash"] and not existing.get("disabled"):
            summary["unchanged"] += 1
        else:
            summary["update"] += 1
    return {
        "summary": summary,
        "conflicts": conflicts,
        "extra_item_codes": extras,
        "target_managed_items": len(existing_rows),
    }


def verify_release(client: FrappeSessionClient, release: Mapping[str, Any]) -> dict[str, Any]:
    """Read back every projected record without mutating the target Site."""

    plan = target_plan(client, release)
    mismatches: list[dict[str, Any]] = []
    for row in release["uoms"]:
        actual = client.get_doc("UOM", str(row["uom_name"]))
        if actual is None:
            mismatches.append({"doctype": "UOM", "name": row["uom_name"], "error": "missing"})
    for row in release["item_groups"]:
        name = str(row["item_group_name"])
        actual = client.get_doc("Item Group", name)
        expected = {
            "item_group_name": name,
            "parent_item_group": row["parent_item_group"],
            "is_group": row["is_group"],
        }
        difference = _verify_fields(actual or {}, expected, expected)
        if actual is None or difference:
            mismatches.append(
                {"doctype": "Item Group", "name": name, "error": "missing" if actual is None else difference}
            )
    for item in release["items"]:
        name = str(item["item_code"])
        actual = client.get_doc("Item", name)
        expected = _erp_item(item)
        difference = _verify_fields(actual or {}, expected, expected)
        if actual is None or difference:
            mismatches.append(
                {"doctype": "Item", "name": name, "error": "missing" if actual is None else difference}
            )
    expected_summary = {
        "create": 0,
        "update": 0,
        "unchanged": len(release["items"]),
        "conflict": 0,
        "extra": 0,
    }
    transaction_counts = _transaction_counts(client)
    return {
        # A catalog verification must remain valid after the isolated test Site
        # has acquired an E2E transaction chain. Existing transactions are
        # reported for audit, but are not an integrity failure.
        "verified": not mismatches and plan["summary"] == expected_summary,
        "plan": plan,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:20],
        "readback_counts": {
            "item_groups": len(release["item_groups"]),
            "uoms": len(release["uoms"]),
            "items": len(release["items"]),
        },
        "transaction_counts": transaction_counts,
        "transactions_present": any(transaction_counts.values()),
    }


def _transaction_counts(client: FrappeSessionClient) -> dict[str, int]:
    return {
        doctype: int(client.method("frappe.client.get_count", {"doctype": doctype}) or 0)
        for doctype in TRANSACTION_DOCTYPES
    }


def _ensure_uom(client: FrappeSessionClient, row: Mapping[str, Any]) -> str:
    name = str(row["uom_name"])
    existing = client.get_doc("UOM", name)
    if existing is None:
        client.create_doc("UOM", row)
        action = "created"
    else:
        action = "existing"
    readback = client.get_doc("UOM", name)
    if readback is None:
        raise SyncError(f"UOM readback failed: {name}")
    return action


def _ensure_item_group(client: FrappeSessionClient, row: Mapping[str, Any]) -> str:
    name = str(row["item_group_name"])
    existing = client.get_doc("Item Group", name)
    expected = {
        "item_group_name": name,
        "parent_item_group": row["parent_item_group"],
        "is_group": row["is_group"],
    }
    if existing is None:
        client.create_doc("Item Group", expected)
        action = "created"
    else:
        mismatches = _verify_fields(existing, expected, expected)
        if mismatches:
            raise SyncError(f"Item Group {name} conflicts with release: {mismatches}")
        action = "existing"
    readback = client.get_doc("Item Group", name)
    if readback is None or _verify_fields(readback, expected, expected):
        raise SyncError(f"Item Group readback failed: {name}")
    return action


def _apply_item(client: FrappeSessionClient, item: Mapping[str, Any]) -> str:
    expected = _erp_item(item)
    existing = client.get_doc("Item", str(item["item_code"]))
    if existing is None:
        client.create_doc("Item", expected)
        action = "created"
    else:
        if existing.get("custom_nexterp_source_id") != item["source_id"]:
            raise SyncError(
                f"Item code conflict {item['item_code']}: target source is "
                f"{existing.get('custom_nexterp_source_id')!r}"
            )
        if existing.get("custom_nexterp_source_hash") == item["source_hash"] and not existing.get("disabled"):
            action = "unchanged"
        else:
            client.update_doc("Item", str(item["item_code"]), expected)
            action = "updated"

    readback = client.get_doc("Item", str(item["item_code"]))
    if readback is None:
        raise SyncError(f"Item readback failed: {item['item_code']}")
    verify_keys = tuple(expected)
    mismatches = _verify_fields(readback, expected, verify_keys)
    if mismatches:
        raise SyncError(f"Item readback mismatch {item['item_code']}: {mismatches}")
    return action


def _load_journal(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": 1, "requests": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("requests"), dict):
        raise SyncError(f"Invalid sync journal: {path}")
    return payload


def _write_journal(path: Path, journal: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(journal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def apply_release(
    client: FrappeSessionClient,
    release: Mapping[str, Any],
    *,
    request_id: str,
    journal_path: Path,
) -> dict[str, Any]:
    try:
        uuid.UUID(request_id)
    except ValueError as exc:
        raise SyncError("request_id must be a UUID") from exc

    journal = _load_journal(journal_path)
    previous = journal["requests"].get(request_id)
    if previous:
        if previous.get("release_hash") != release["release_hash"]:
            raise SyncError("request_id was already used for a different release")
        if previous.get("status") == "verified":
            return dict(previous["result"])

    plan = target_plan(client, release)
    if plan["summary"]["conflict"]:
        raise SyncError(f"Target plan contains conflicts: {plan['conflicts'][:10]}")

    result: dict[str, Any] = {
        "request_id": request_id,
        "release_hash": release["release_hash"],
        "catalog_revision": release["catalog_revision"],
        "item_groups": {"created": 0, "existing": 0},
        "uoms": {"created": 0, "existing": 0},
        "items": {"created": 0, "updated": 0, "unchanged": 0},
        "transaction_counts_before": _transaction_counts(client),
    }
    for row in release["uoms"]:
        result["uoms"][_ensure_uom(client, row)] += 1
    for row in release["item_groups"]:
        result["item_groups"][_ensure_item_group(client, row)] += 1
    for item in release["items"]:
        result["items"][_apply_item(client, item)] += 1

    verification = target_plan(client, release)
    if verification["summary"] != {
        "create": 0,
        "update": 0,
        "unchanged": len(release["items"]),
        "conflict": 0,
        "extra": 0,
    }:
        raise SyncError(f"Post-apply verification failed: {verification}")
    result["transaction_counts_after"] = _transaction_counts(client)
    if result["transaction_counts_after"] != result["transaction_counts_before"]:
        raise SyncError(
            "Catalog synchronization changed transaction counts: "
            f"before={result['transaction_counts_before']}, "
            f"after={result['transaction_counts_after']}"
        )
    result["verified_at"] = _now()
    result["post_apply"] = verification
    journal["requests"][request_id] = {
        "release_hash": release["release_hash"],
        "status": "verified",
        "result": result,
    }
    _write_journal(journal_path, journal)
    return result


def _release(args: argparse.Namespace) -> dict[str, Any]:
    """Build a release using read-only catalog access."""

    return build_material_release(Path(args.database), code_map_path=Path(args.code_map))


def _freeze_release(args: argparse.Namespace, release: Mapping[str, Any]) -> Path:
    return write_material_release(
        release,
        release_root=Path(args.release_root),
        code_map_path=Path(args.code_map),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("initialize", "plan", "apply", "verify"))
    parser.add_argument("--database", type=Path, default=DEFAULT_REFERENCE_CATALOG_DATABASE_PATH)
    parser.add_argument("--code-map", type=Path, default=DEFAULT_ITEM_CODE_MAP_PATH)
    parser.add_argument("--release-root", type=Path, default=DEFAULT_RELEASE_ROOT)
    parser.add_argument("--secret-file", type=Path, default=DEFAULT_SECRET_PATH)
    parser.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL_PATH)
    parser.add_argument("--request-id")
    parser.add_argument("--confirm-release-hash")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        client = _load_client(Path(args.secret_file))
        if args.action == "initialize":
            initialized = initialize_target(client)
            print(json.dumps({"site": SITE_HOST, "initialized": initialized}, ensure_ascii=False, indent=2))
            return 0

        release = _release(args)
        if args.action == "plan":
            request_id = str(args.request_id or uuid.uuid4())
            try:
                uuid.UUID(request_id)
            except ValueError as exc:
                raise SyncError("request_id must be a UUID") from exc
            plan = target_plan(client, release)
            print(
                json.dumps(
                    {
                        "site": SITE_HOST,
                        "request_id": request_id,
                        "release_hash": release["release_hash"],
                        "catalog_revision": release["catalog_revision"],
                        "counts": release["counts"],
                        "plan": plan,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0 if not plan["summary"]["conflict"] else 2

        if args.action == "verify":
            verification = verify_release(client, release)
            print(
                json.dumps(
                    {"release_hash": release["release_hash"], **verification},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0 if verification["verified"] else 3

        if not args.request_id:
            raise SyncError("apply requires --request-id")
        if args.confirm_release_hash != release["release_hash"]:
            raise SyncError(
                "apply requires --confirm-release-hash matching the frozen release; run plan first"
            )
        _freeze_release(args, release)
        initialize_target(client)
        result = apply_release(
            client,
            release,
            request_id=args.request_id,
            journal_path=Path(args.journal),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (MaterialReleaseError, SyncError, requests.RequestException, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
