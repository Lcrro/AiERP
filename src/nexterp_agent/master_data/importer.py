from __future__ import annotations

from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

from .release import MasterDataRelease


class ERPNextImportClient(Protocol):
    def get_document(self, doctype: str, name: str) -> Any: ...

    def search_documents(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | list[Any] | None = None,
        fields: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str | None = None,
    ) -> Any: ...

    def create_document(self, doctype: str, data: dict[str, Any]) -> Any: ...

    def update_document(self, doctype: str, name: str, data: dict[str, Any]) -> Any: ...


@dataclass(frozen=True)
class ImportOperation:
    key: str
    stage: str
    doctype: str
    data: dict[str, Any]
    lookup_name: str | None = None
    lookup_filters: dict[str, Any] = field(default_factory=dict)
    update_existing: bool = True
    update_exclude: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "stage": self.stage,
            "doctype": self.doctype,
            "lookup_name": self.lookup_name,
            "lookup_filters": self.lookup_filters,
            "update_existing": self.update_existing,
            "update_exclude": list(self.update_exclude),
            "data": self.data,
        }


def _active(value: str) -> bool:
    return value in {"active", "candidate", "1", ""}


def _roles(value: str) -> list[dict[str, str]]:
    return [{"role": role.strip()} for role in value.split(";") if role.strip()]


DESIGNATION_MAP = {
    "总经理": "Managing Director",
    "材料设备主管": "Manager",
    "项目经理": "Project Manager",
    "技术负责人": "Engineer",
    "材料员": "Administrative Assistant",
    "经营主管": "Chief Operating Officer",
    "系统管理员": "Software Developer",
    "财务人员": "Accountant",
}


def _operation(
    *,
    key: str,
    stage: str,
    doctype: str,
    data: dict[str, Any],
    lookup_name: str | None = None,
    lookup_filters: dict[str, Any] | None = None,
    update_existing: bool = True,
    update_exclude: tuple[str, ...] = (),
) -> ImportOperation:
    return ImportOperation(
        key=key,
        stage=stage,
        doctype=doctype,
        data={name: value for name, value in data.items() if value not in (None, "")},
        lookup_name=lookup_name,
        lookup_filters=lookup_filters or {},
        update_existing=update_existing,
        update_exclude=update_exclude,
    )


def build_import_operations(release: MasterDataRelease | None = None) -> list[ImportOperation]:
    release = release or MasterDataRelease()
    operations: list[ImportOperation] = []

    companies = release.companies
    for row in companies.values():
        name = row["erpnext_company_name"]
        operations.append(
            _operation(
                key=f"company:{row['company_code']}",
                stage="organization",
                doctype="Company",
                lookup_name=name,
                update_exclude=("abbr", "country"),
                data={
                    "name": name,
                    "company_name": row["company_name"],
                    "abbr": row["abbr"],
                    "default_currency": row["default_currency"],
                    "country": row["country"],
                },
            )
        )

    departments = {row["department_code"]: row for row in release.table("departments.tsv")}
    for row in departments.values():
        parent = departments.get(row["parent_department_code"])
        operations.append(
            _operation(
                key=f"department:{row['department_code']}",
                stage="organization",
                doctype="Department",
                lookup_name=row["erpnext_department_name"],
                data={
                    "name": row["erpnext_department_name"],
                    "department_name": row["department_name"],
                    "company": release.company_name(row["company_code"]),
                    "parent_department": parent["erpnext_department_name"] if parent else None,
                    "is_group": 1,
                },
            )
        )

    for role in release.roles.values():
        operations.append(
            _operation(
                key=f"role-profile:{role['role_code']}",
                stage="access",
                doctype="Role Profile",
                lookup_name=role["role_name"],
                data={"name": role["role_name"], "role_profile": role["role_name"], "roles": _roles(role["erpnext_roles"])},
            )
        )

    cost_centers = {row["cost_center_code"]: row for row in release.table("cost_centers.tsv")}
    for row in cost_centers.values():
        parent = cost_centers.get(row["parent_cost_center_code"])
        name = release.cost_center_name(row)
        cost_center_label = release.company_name(row["company_code"]) if parent is None else row["cost_center_name"]
        operations.append(
            _operation(
                key=f"cost-center:{row['cost_center_code']}",
                stage="finance-foundation",
                doctype="Cost Center",
                lookup_name=name,
                update_existing=parent is not None,
                data={
                    "name": name,
                    "cost_center_name": cost_center_label,
                    "company": release.company_name(row["company_code"]),
                    "parent_cost_center": release.cost_center_name(parent) if parent else None,
                    "is_group": int(row["is_group"] or "0"),
                },
            )
        )

    warehouses = release.warehouses
    for row in warehouses.values():
        parent = warehouses.get(row["parent_warehouse_code"])
        operations.append(
            _operation(
                key=f"warehouse:{row['warehouse_code']}",
                stage="stock-foundation",
                doctype="Warehouse",
                lookup_name=row["erpnext_warehouse_name"],
                data={
                    "name": row["erpnext_warehouse_name"],
                    "warehouse_name": row["warehouse_name"],
                    "company": release.company_name(row["company_code"]),
                    "parent_warehouse": parent["erpnext_warehouse_name"] if parent else None,
                    "is_group": int(row["is_group"] or "0"),
                },
            )
        )

    project_types = sorted({row["project_type"] for row in release.projects.values() if row["project_type"]})
    for project_type in project_types:
        operations.append(
            _operation(
                key=f"project-type:{project_type}",
                stage="projects",
                doctype="Project Type",
                lookup_name=project_type,
                data={"name": project_type, "project_type": project_type},
            )
        )

    for row in release.projects.values():
        cost_center = cost_centers[row["cost_center_code"]]
        operations.append(
            _operation(
                key=f"project:{row['project_code']}",
                stage="projects",
                doctype="Project",
                lookup_filters={"project_name": row["project_name"]},
                data={
                    "project_name": row["project_name"],
                    "company": release.company_name(row["company_code"]),
                    "status": "Open" if row["project_operating_status"] in {"在建", "基地运营"} else "Completed",
                    "project_type": row["project_type"],
                    "expected_start_date": row["expected_start_date"],
                    "expected_end_date": row["expected_end_date"],
                    "cost_center": release.cost_center_name(cost_center),
                    "notes": f"项目简称：{row['project_short_name']}。{row['note']}",
                },
            )
        )

    for row in release.table("user_accounts.tsv"):
        role = release.roles[row["role_code"]]
        operations.append(
            _operation(
                key=f"user:{row['user_email']}",
                stage="people",
                doctype="User",
                lookup_name=row["user_email"],
                data={
                    "name": row["user_email"],
                    "email": row["user_email"],
                    "first_name": row["full_name"],
                    "enabled": int(row["enabled"]),
                    "send_welcome_email": int(row["send_welcome_email"]),
                    "language": row["language"],
                    "time_zone": row["timezone"],
                    "roles": _roles(role["erpnext_roles"]),
                    "role_profile_name": role["role_name"],
                },
            )
        )

    department_names = {code: row["erpnext_department_name"] for code, row in departments.items()}
    for row in release.employees.values():
        operations.append(
            _operation(
                key=f"employee:{row['employee_code']}",
                stage="people",
                doctype="Employee",
                lookup_filters={"employee_number": row["employee_code"]},
                data={
                    "employee_number": row["employee_code"],
                    "first_name": row["employee_name"],
                    "employee_name": row["employee_name"],
                    "gender": "Male" if row["gender"] == "男" else "Female",
                    "date_of_birth": "1990-01-01",
                    "date_of_joining": "2026-07-01",
                    "company": release.company_name("STEC"),
                    "department": department_names[row["department_code"]],
                    "designation": DESIGNATION_MAP.get(row["position"], "Employee"),
                    "user_id": row["user_email"],
                    "status": "Active" if _active(row["status"]) else "Inactive",
                },
            )
        )

    team_users: dict[str, list[dict[str, str]]] = {}
    for team in release.table("project_teams.tsv"):
        employee = release.employees[team["employee_code"]]
        team_users.setdefault(team["project_code"], []).append(
            {"user": employee["user_email"], "welcome_email_sent": 1}
        )
    for project_code, users in team_users.items():
        project = release.projects[project_code]
        cost_center = cost_centers[project["cost_center_code"]]
        operations.append(
            _operation(
                key=f"project-team:{project_code}",
                stage="people",
                doctype="Project",
                lookup_filters={"project_name": project["project_name"]},
                data={
                    "project_name": project["project_name"],
                    "company": release.company_name(project["company_code"]),
                    "cost_center": release.cost_center_name(cost_center),
                    "users": users,
                },
            )
        )

    for row in release.table("payment_terms.tsv"):
        operations.append(
            _operation(
                key=f"payment-term:{row['payment_term_code']}",
                stage="buying-foundation",
                doctype="Payment Term",
                lookup_name=row["payment_term_name"],
                data={"name": row["payment_term_name"], "payment_term_name": row["payment_term_name"]},
            )
        )
        operations.append(
            _operation(
                key=f"payment-template:{row['payment_term_code']}",
                stage="buying-foundation",
                doctype="Payment Terms Template",
                lookup_name=row["erpnext_payment_terms_template"],
                data={
                    "name": row["erpnext_payment_terms_template"],
                    "template_name": row["erpnext_payment_terms_template"],
                    "terms": [
                        {
                            "payment_term": row["payment_term_name"],
                            "invoice_portion": 100,
                            "credit_days_based_on": "Day(s) after invoice date",
                            "credit_days": int(row["days"] or "0"),
                        }
                    ],
                },
            )
        )

    price_lists = {row["price_list_code"]: row for row in release.table("price_lists.tsv")}
    for row in price_lists.values():
        operations.append(
            _operation(
                key=f"price-list:{row['price_list_code']}",
                stage="buying-foundation",
                doctype="Price List",
                lookup_name=row["price_list_name"],
                data={
                    "name": row["price_list_name"],
                    "price_list_name": row["price_list_name"],
                    "currency": row["currency"],
                    "buying": 1 if row["buying_or_selling"] == "Buying" else 0,
                    "selling": 1 if row["buying_or_selling"] == "Selling" else 0,
                    "enabled": int(row["enabled"]),
                },
            )
        )

    supplier_groups = sorted({row["supplier_group"] for row in release.table("suppliers.tsv")})
    for group in supplier_groups:
        operations.append(
            _operation(
                key=f"supplier-group:{group}",
                stage="buying-foundation",
                doctype="Supplier Group",
                lookup_name=group,
                data={"name": group, "supplier_group_name": group, "parent_supplier_group": "All Supplier Groups", "is_group": 0},
            )
        )

    suppliers = {row["supplier_code"]: row for row in release.table("suppliers.tsv")}
    payment_templates = {row["payment_term_code"]: row["erpnext_payment_terms_template"] for row in release.table("payment_terms.tsv")}
    for row in suppliers.values():
        operations.append(
            _operation(
                key=f"supplier:{row['supplier_code']}",
                stage="buying-foundation",
                doctype="Supplier",
                lookup_filters={"supplier_name": row["supplier_name"]},
                data={
                    "supplier_name": row["supplier_name"],
                    "supplier_group": row["supplier_group"],
                    "supplier_type": row["supplier_type"],
                    "default_currency": row["default_currency"],
                    "payment_terms": payment_templates.get(row["default_payment_term"]),
                },
            )
        )

    for row in release.table("supplier_contacts.tsv"):
        operations.append(
            _operation(
                key=f"supplier-contact:{row['contact_code']}",
                stage="buying-foundation",
                doctype="Contact",
                lookup_filters={
                    "first_name": row["contact_name"],
                    "company_name": suppliers[row["supplier_code"]]["supplier_name"],
                },
                data={
                    "first_name": row["contact_name"],
                    "company_name": suppliers[row["supplier_code"]]["supplier_name"],
                    "designation": row["role"],
                    "is_primary_contact": int(row["is_primary"]),
                    "email_ids": [{"email_id": row["email"], "is_primary": 1}] if row["email"] else [],
                    "phone_nos": [{"phone": row["phone"], "is_primary_phone": 1}] if row["phone"] else [],
                    "links": [
                        {
                            "link_doctype": "Supplier",
                            "link_name": suppliers[row["supplier_code"]]["supplier_name"],
                        }
                    ],
                },
            )
        )

    item_groups = sorted({row["item_group"] for row in release.materials})
    for group in item_groups:
        operations.append(
            _operation(
                key=f"item-group:{group}",
                stage="items",
                doctype="Item Group",
                lookup_name=group,
                data={"name": group, "item_group_name": group, "parent_item_group": "All Item Groups", "is_group": 0},
            )
        )

    uoms = sorted({row["stock_uom"] for row in release.materials} | {row["purchase_uom"] for row in release.materials})
    for uom in uoms:
        operations.append(
            _operation(
                key=f"uom:{uom}",
                stage="items",
                doctype="UOM",
                lookup_name=uom,
                data={"name": uom, "uom_name": uom, "must_be_whole_number": 0},
            )
        )

    for row in release.materials:
        description = f"{row['sku_name']}\n规格：{row['required_specs']}"
        if row["aliases"]:
            description += f"\n别名：{row['aliases']}"
        operations.append(
            _operation(
                key=f"item:{row['item_code']}",
                stage="items",
                doctype="Item",
                lookup_name=row["item_code"],
                update_exclude=("stock_uom",),
                data={
                    "name": row["item_code"],
                    "item_code": row["item_code"],
                    "item_name": row["sku_name"],
                    "description": description,
                    "item_group": row["item_group"],
                    "stock_uom": row["stock_uom"],
                    "is_stock_item": 1,
                    "is_purchase_item": 1,
                    "is_sales_item": 0,
                    "include_item_in_manufacturing": 0,
                    "disabled": 0,
                },
            )
        )

    for row in release.table("supplier_item_policies.tsv"):
        supplier = suppliers[row["supplier_code"]]
        price_list = price_lists[row["price_list_code"]]
        operations.append(
            _operation(
                key=f"item-price:{row['supplier_code']}:{row['item_code']}",
                stage="prices",
                doctype="Item Price",
                lookup_filters={
                    "item_code": row["item_code"],
                    "price_list": price_list["price_list_name"],
                    "supplier": supplier["supplier_name"],
                    "uom": row["default_purchase_uom"],
                },
                data={
                    "item_code": row["item_code"],
                    "price_list": price_list["price_list_name"],
                    "supplier": supplier["supplier_name"],
                    "uom": row["default_purchase_uom"],
                    "price_list_rate": float(row["default_rate"]),
                    "currency": supplier["default_currency"],
                    "valid_from": row["price_valid_from"],
                    "valid_upto": row["price_valid_to"],
                    "buying": 1,
                },
            )
        )

    return operations


class MasterDataImporter:
    def __init__(self, client: ERPNextImportClient | None = None, operations: list[ImportOperation] | None = None) -> None:
        self.client = client
        self.operations = operations or build_import_operations()

    def plan(self) -> dict[str, Any]:
        stages: dict[str, int] = {}
        doctypes: dict[str, int] = {}
        for operation in self.operations:
            stages[operation.stage] = stages.get(operation.stage, 0) + 1
            doctypes[operation.doctype] = doctypes.get(operation.doctype, 0) + 1
        return {
            "mode": "plan",
            "operation_count": len(self.operations),
            "stages": stages,
            "doctypes": doctypes,
            "operations": [operation.to_dict() for operation in self.operations],
        }

    def apply(self, *, stop_on_error: bool = True, workers: int = 1) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("ERPNext client is required for apply mode")
        if workers > 1:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                results = list(executor.map(self._apply_operation, self.operations))
            return _execution_summary("apply", self.operations, results)

        results: list[dict[str, Any]] = []
        for operation in self.operations:
            entry = self._apply_operation(operation)
            results.append(entry)
            if not entry["ok"] and stop_on_error:
                break
        return _execution_summary("apply", self.operations, results)

    def _apply_operation(self, operation: ImportOperation) -> dict[str, Any]:
        existing_name = self._find_existing_name(operation)
        if existing_name and operation.update_existing:
            update_data = {
                key: value
                for key, value in operation.data.items()
                if key != "name" and key not in operation.update_exclude
            }
            result = self.client.update_document(operation.doctype, existing_name, update_data)
            action = "updated"
        elif existing_name:
            return {"key": operation.key, "doctype": operation.doctype, "action": "skipped", "ok": True, "name": existing_name}
        else:
            result = self.client.create_document(operation.doctype, operation.data)
            action = "created"
        return {
            "key": operation.key,
            "doctype": operation.doctype,
            "action": action,
            "ok": bool(getattr(result, "ok", False)),
            "name": _result_name(result) or existing_name,
            "error_type": getattr(result, "error_type", None),
            "error": getattr(result, "error", None),
        }

    def verify(self, *, workers: int = 1) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("ERPNext client is required for verify mode")
        doctypes = {operation.doctype for operation in self.operations}
        if doctypes == {"Item"}:
            results = self._verify_items_bulk()
            return _execution_summary("verify", self.operations, results)
        if doctypes == {"Item Price"}:
            results = self._verify_item_prices_bulk()
            return _execution_summary("verify", self.operations, results)
        if len(doctypes) > 1:
            results: list[dict[str, Any]] = []
            for bulk_doctype in ("Item", "Item Price"):
                subset = [operation for operation in self.operations if operation.doctype == bulk_doctype]
                if subset:
                    results.extend(MasterDataImporter(self.client, subset).verify()["results"])
            remaining = [operation for operation in self.operations if operation.doctype not in {"Item", "Item Price"}]
            if workers > 1:
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    results.extend(executor.map(self._verify_operation, remaining))
            else:
                results.extend(self._verify_operation(operation) for operation in remaining)
            return _execution_summary("verify", self.operations, results)
        if workers > 1:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                results = list(executor.map(self._verify_operation, self.operations))
            return _execution_summary("verify", self.operations, results)

        results: list[dict[str, Any]] = []
        for operation in self.operations:
            results.append(self._verify_operation(operation))
        return _execution_summary("verify", self.operations, results)

    def _fetch_all(self, doctype: str, fields: list[str], *, page_size: int = 500) -> list[dict[str, Any]]:
        if self.client is None:
            raise RuntimeError("ERPNext client is required for lookup")
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            result = self.client.search_documents(doctype, fields=fields, limit=page_size, offset=offset)
            if not getattr(result, "ok", False) or not isinstance(getattr(result, "data", None), list):
                raise RuntimeError(f"Failed to list {doctype}: {getattr(result, 'error', None)}")
            page = result.data
            rows.extend(page)
            if len(page) < page_size:
                return rows
            offset += len(page)

    def _verify_items_bulk(self) -> list[dict[str, Any]]:
        existing = {row.get("name") for row in self._fetch_all("Item", ["name"])}
        return [
            {
                "key": operation.key,
                "doctype": operation.doctype,
                "ok": operation.lookup_name in existing,
                "name": operation.lookup_name if operation.lookup_name in existing else None,
                "action": "verified" if operation.lookup_name in existing else "missing",
            }
            for operation in self.operations
        ]

    def _verify_item_prices_bulk(self) -> list[dict[str, Any]]:
        fields = ["name", "item_code", "price_list", "supplier", "uom"]
        rows = self._fetch_all("Item Price", fields)
        existing = {
            (row.get("item_code"), row.get("price_list"), row.get("supplier"), row.get("uom")): row.get("name")
            for row in rows
        }
        results: list[dict[str, Any]] = []
        for operation in self.operations:
            filters = operation.lookup_filters
            identity = (filters.get("item_code"), filters.get("price_list"), filters.get("supplier"), filters.get("uom"))
            name = existing.get(identity)
            results.append(
                {
                    "key": operation.key,
                    "doctype": operation.doctype,
                    "ok": bool(name),
                    "name": name,
                    "action": "verified" if name else "missing",
                }
            )
        return results

    def _verify_operation(self, operation: ImportOperation) -> dict[str, Any]:
        existing_name = self._find_existing_name(operation)
        return {
            "key": operation.key,
            "doctype": operation.doctype,
            "ok": bool(existing_name),
            "name": existing_name,
            "action": "verified" if existing_name else "missing",
        }

    def _find_existing_name(self, operation: ImportOperation) -> str | None:
        if self.client is None:
            raise RuntimeError("ERPNext client is required for lookup")
        if operation.lookup_name:
            result = self.client.get_document(operation.doctype, operation.lookup_name)
            if getattr(result, "ok", False):
                return operation.lookup_name
        if operation.lookup_filters:
            result = self.client.search_documents(
                operation.doctype,
                filters=operation.lookup_filters,
                fields=["name"],
                limit=1,
            )
            if getattr(result, "ok", False) and isinstance(getattr(result, "data", None), list) and result.data:
                return result.data[0].get("name")
        return None


def _result_name(result: Any) -> str | None:
    data = getattr(result, "data", None)
    if isinstance(data, dict):
        return data.get("name")
    return None


def _execution_summary(mode: str, operations: list[ImportOperation], results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "mode": mode,
        "operation_count": len(operations),
        "processed_count": len(results),
        "ok_count": sum(bool(result["ok"]) for result in results),
        "failed_count": sum(not bool(result["ok"]) for result in results),
        "results": results,
    }
