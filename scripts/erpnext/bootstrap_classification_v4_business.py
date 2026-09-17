"""Prepare the isolated ChatGPT classification V4 Site for business testing.

This command is intentionally idempotent and only targets
``material-classification-v4.localhost``.  It adds the minimum Company,
Project, Warehouse, Supplier, User and Material Request workflow masters
needed by the Nexterp portal.  It never touches ``material-test.localhost``.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
for import_root in (ROOT / "src", ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

import requests  # noqa: E402
from urllib.parse import quote  # noqa: E402
from scripts.erpnext.sync_gpc_materials_to_test_site import SyncError  # noqa: E402


SITE = "material-classification-v4.localhost"
BASE_URL = "http://127.0.0.1:8004"
DEFAULT_SECRET = ROOT / ".secrets" / "erpnext-material-classification-v4" / "site-secrets.json"
DEFAULT_CREDENTIALS = ROOT / ".secrets" / "erpnext-material-classification-v4" / "user-api-credentials.json"

COMPANY = "Nexterp分类示范有限公司"
ABBR = "NCV"
PROJECT_CODE = "PRJ-HL-13"
PROJECT_NAME = "PROJ-0001"
ROOT_WAREHOUSE = "分类示范仓库 - NCV"
PROJECT_WAREHOUSE = "合流1.3标仓库 - NCV"
COST_CENTER = f"合流1.3标 - {ABBR}"

USERS: tuple[dict[str, Any], ...] = (
    {"email": "mao.xiaoquan@stec-up.local", "full_name": "毛晓泉（材料员）", "roles": ["Purchase User", "Stock User", "Projects User"]},
    {"email": "pan.feng@stec-up.local", "full_name": "潘丰（材料设备主管）", "roles": ["Purchase Manager", "Purchase User", "Stock Manager", "Stock User", "Projects User"]},
    {"email": "hu.yinhu@stec-up.local", "full_name": "胡银虎（项目经理）", "roles": ["Projects Manager", "Projects User", "Purchase User", "Stock User"]},
    {"email": "procurement.test@stec-up.local", "full_name": "采购测试员", "roles": ["Purchase User", "Purchase Manager"]},
    {"email": "warehouse.test@stec-up.local", "full_name": "仓管测试员", "roles": ["Stock User", "Stock Manager", "Purchase User"]},
)


class V4SessionClient:
    def __init__(self, password: str) -> None:
        self.session = requests.Session()
        self.session.headers.update({"Host": SITE, "Accept": "application/json"})
        response = self.session.post(f"{BASE_URL}/api/method/login", data={"usr": "Administrator", "pwd": password}, timeout=30)
        self._raise(response, "login")

    @staticmethod
    def _raise(response: requests.Response, operation: str) -> None:
        if response.ok:
            return
        try:
            payload = response.json()
        except ValueError:
            payload = response.text[:500]
        raise SyncError(f"V4 ERPNext {operation} failed ({response.status_code}): {payload}")

    def get_doc(self, doctype: str, name: str) -> dict[str, Any] | None:
        response = self.session.get(f"{BASE_URL}/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}", timeout=30)
        if response.status_code == 404:
            return None
        self._raise(response, f"get {doctype} {name}")
        return response.json().get("data") or {}

    def create_doc(self, doctype: str, document: Mapping[str, Any]) -> dict[str, Any]:
        response = self.session.post(f"{BASE_URL}/api/resource/{quote(doctype, safe='')}", json=dict(document), timeout=60)
        self._raise(response, f"create {doctype}")
        return response.json().get("data") or {}

    def update_doc(self, doctype: str, name: str, document: Mapping[str, Any]) -> dict[str, Any]:
        response = self.session.put(f"{BASE_URL}/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}", json=dict(document), timeout=60)
        self._raise(response, f"update {doctype} {name}")
        return response.json().get("data") or {}

    def method(self, dotted_path: str, payload: Mapping[str, Any] | None = None, *, http_method: str = "GET") -> Any:
        request = self.session.post if http_method.upper() == "POST" else self.session.get
        kwargs = {"json": dict(payload or {})} if http_method.upper() == "POST" else {"params": dict(payload or {})}
        response = request(f"{BASE_URL}/api/method/{dotted_path}", timeout=30, **kwargs)
        self._raise(response, dotted_path)
        body = response.json()
        return body.get("message", body)


def _load_admin(secret_path: Path) -> V4SessionClient:
    if not secret_path.is_file():
        raise SyncError(f"V4 Site secret file does not exist: {secret_path}")
    payload = json.loads(secret_path.read_text(encoding="utf-8-sig"))
    if payload.get("site") != SITE or not payload.get("admin_password"):
        raise SyncError("V4 Site secret file is incomplete or belongs to another Site")
    return V4SessionClient(str(payload["admin_password"]))


def _ensure(client: V4SessionClient, doctype: str, name: str, document: Mapping[str, Any]) -> str:
    existing = client.get_doc(doctype, name)
    if existing is not None:
        return "existing"
    payload = dict(document)
    payload["name"] = name
    client.create_doc(doctype, payload)
    if client.get_doc(doctype, name) is None:
        raise SyncError(f"{doctype} 回读失败：{name}")
    return "created"


def ensure_business_masters(client: V4SessionClient) -> dict[str, Any]:
    result: dict[str, Any] = {"created": [], "existing": [], "users": {}, "workflow": "existing"}

    # The importer already creates the Company and All Item Groups.  These
    # checks make the command safe when run against a fresh V4 Site.
    masters = [
        ("Warehouse Type", "Transit", {"name": "Transit"}),
        ("Company", COMPANY, {"company_name": COMPANY, "abbr": ABBR, "default_currency": "CNY", "country": "China", "is_group": 0}),
        ("Fiscal Year", "2026", {"year": "2026", "year_start_date": "2026-01-01", "year_end_date": "2026-12-31", "disabled": 0, "companies": [{"company": COMPANY}]}),
        ("Warehouse", ROOT_WAREHOUSE, {"warehouse_name": ROOT_WAREHOUSE, "company": COMPANY, "is_group": 1}),
        ("Warehouse", PROJECT_WAREHOUSE, {"warehouse_name": PROJECT_WAREHOUSE, "parent_warehouse": ROOT_WAREHOUSE, "company": COMPANY, "is_group": 0}),
        ("Cost Center", COST_CENTER, {"cost_center_name": "合流1.3标", "company": COMPANY, "parent_cost_center": f"{COMPANY} - {ABBR}", "is_group": 0}),
        ("Project", PROJECT_NAME, {"project_name": PROJECT_CODE, "status": "Open", "company": COMPANY, "cost_center": COST_CENTER, "expected_start_date": "2026-01-01"}),
        ("Supplier", "测试建材供应商甲", {"supplier_name": "测试建材供应商甲", "supplier_type": "Company", "country": "China"}),
        ("Supplier", "测试建材供应商乙", {"supplier_name": "测试建材供应商乙", "supplier_type": "Company", "country": "China"}),
        ("Price List", "Nexterp分类示范采购价目表", {"price_list_name": "Nexterp分类示范采购价目表", "buying": 1, "selling": 0, "enabled": 1, "currency": "CNY"}),
    ]
    for doctype, name, document in masters:
        state = _ensure(client, doctype, name, document)
        result[state].append({"doctype": doctype, "name": name})

    for state_name in ("Nexterp材料草稿", "Nexterp主管审批", "Nexterp项目审批", "Nexterp已批准"):
        state = _ensure(client, "Workflow State", state_name, {"workflow_state_name": state_name})
        result[state].append({"doctype": "Workflow State", "name": state_name})
    for action_name in ("提交", "主管通过", "项目通过", "退回"):
        state = _ensure(client, "Workflow Action Master", action_name, {"workflow_action_name": action_name})
        result[state].append({"doctype": "Workflow Action Master", "name": action_name})

    workflow_name = "Nexterp材料申请三级审批"
    workflow = {
        "workflow_name": workflow_name,
        "document_type": "Material Request",
        "is_active": 1,
        "override_status": 1,
        "workflow_state_field": "workflow_state",
        "states": [
            {"state": "Nexterp材料草稿", "doc_status": "0", "allow_edit": "Purchase User"},
            {"state": "Nexterp主管审批", "doc_status": "0", "allow_edit": "Purchase Manager"},
            {"state": "Nexterp项目审批", "doc_status": "0", "allow_edit": "Projects Manager"},
            {"state": "Nexterp已批准", "doc_status": "1", "allow_edit": "Purchase Manager"},
        ],
        "transitions": [
            {"state": "Nexterp材料草稿", "action": "提交", "next_state": "Nexterp主管审批", "allowed": "Purchase User"},
            {"state": "Nexterp主管审批", "action": "主管通过", "next_state": "Nexterp项目审批", "allowed": "Purchase Manager"},
            {"state": "Nexterp项目审批", "action": "项目通过", "next_state": "Nexterp已批准", "allowed": "Projects Manager"},
            {"state": "Nexterp主管审批", "action": "退回", "next_state": "Nexterp材料草稿", "allowed": "Purchase Manager"},
            {"state": "Nexterp项目审批", "action": "退回", "next_state": "Nexterp材料草稿", "allowed": "Projects Manager"},
        ],
    }
    if client.get_doc("Workflow", workflow_name) is None:
        _ensure(client, "Workflow", workflow_name, workflow)
        result["workflow"] = "created"

    for expected in USERS:
        email = str(expected["email"])
        current = client.get_doc("User", email)
        if current is None:
            _ensure(client, "User", email, {"email": email, "first_name": expected["full_name"], "enabled": 1, "send_welcome_email": 0, "language": "zh", "time_zone": "Asia/Shanghai", "roles": [{"role": role} for role in expected["roles"]]})
            user_state = "created"
        else:
            current_roles = {str(row.get("role")) for row in current.get("roles") or [] if isinstance(row, dict) and row.get("role")}
            missing = [role for role in expected["roles"] if role not in current_roles]
            if missing:
                merged = sorted(current_roles | set(expected["roles"]))
                client.update_doc("User", email, {"roles": [{"doctype": "Has Role", "role": role} for role in merged]})
                user_state = "updated"
            else:
                user_state = "existing"
        result["users"][email] = user_state

    return result


def generate_credentials(client: V4SessionClient, output: Path) -> None:
    users: dict[str, dict[str, str]] = {}
    if output.is_file():
        payload = json.loads(output.read_text(encoding="utf-8-sig"))
        if (
            isinstance(payload, dict)
            and payload.get("site") == SITE
            and isinstance(payload.get("users"), dict)
        ):
            users = dict(payload["users"])
    for row in USERS:
        email = str(row["email"])
        current = users.get(email)
        if isinstance(current, dict) and current.get("api_key") and current.get("api_secret"):
            # Keep an existing key pair stable across repeated bootstrap runs;
            # rotating credentials would invalidate the running portal for no
            # business-data reason.  Generate only missing user credentials.
            continue
        result = client.method("frappe.core.doctype.user.user.generate_keys", {"user": email}, http_method="POST")
        if not isinstance(result, dict) or not result.get("api_key") or not result.get("api_secret"):
            raise SyncError(f"无法为 V4 测试用户生成 API 凭据：{email}")
        users[email] = {"api_key": str(result["api_key"]), "api_secret": str(result["api_secret"])}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"profile": "classification_v4", "site": SITE, "users": users}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secret-file", type=Path, default=DEFAULT_SECRET)
    parser.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS)
    args = parser.parse_args()
    try:
        client = _load_admin(args.secret_file)
        result = ensure_business_masters(client)
        generate_credentials(client, args.credentials)
        print(json.dumps({"site": SITE, "company": COMPANY, "project": PROJECT_CODE, "warehouse": PROJECT_WAREHOUSE, "masters": result, "credentials_file": str(args.credentials)}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
