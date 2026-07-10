from __future__ import annotations

import argparse
import csv
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RELEASE_DIR = REPO_ROOT / "data" / "master_data" / "release_v0_1"
DEFAULT_MATERIAL_PATH = (
    REPO_ROOT
    / "data"
    / "material_master"
    / "release_v0_3"
    / "material_master_release_v0_3.tsv"
)

ALLOWED_STATUS = {"active", "candidate", "disabled"}
ALLOWED_PROJECT_OPERATING_STATUS = {"在建", "基地运营", "储备"}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return list(reader)


def check_column_counts(path: Path) -> list[str]:
    issues: list[str] = []
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    if not lines:
        return [f"{path.name}: empty file"]
    expected = len(lines[0].split("\t"))
    for line_no, line in enumerate(lines, start=1):
        actual = len(line.split("\t"))
        if actual != expected:
            issues.append(
                f"{path.name}: line {line_no} has {actual} columns, expected {expected}"
            )
    return issues


def index_by(
    rows: list[dict[str, str]], keys: list[str], table_name: str
) -> tuple[dict[str, dict[str, str]], list[str]]:
    index: dict[str, dict[str, str]] = {}
    issues: list[str] = []
    for row_no, row in enumerate(rows, start=2):
        values = [row.get(key, "").strip() for key in keys]
        value = "::".join(values)
        if any(not value_part for value_part in values):
            issues.append(
                f"{table_name}: line {row_no} missing primary key {'+'.join(keys)}"
            )
            continue
        if value in index:
            issues.append(
                f"{table_name}: duplicate primary key {'+'.join(keys)}={value}"
            )
        index[value] = row
    return index, issues


def check_status(rows: list[dict[str, str]], table_name: str) -> list[str]:
    issues: list[str] = []
    for row_no, row in enumerate(rows, start=2):
        status = row.get("status", "").strip()
        if status and status not in ALLOWED_STATUS:
            issues.append(f"{table_name}: line {row_no} unsupported status={status}")
    return issues


def require_ref(
    issues: list[str],
    table_name: str,
    row_no: int,
    field: str,
    index: dict[str, dict[str, str]],
    value: str,
) -> None:
    if value and value not in index:
        issues.append(f"{table_name}: line {row_no} missing {field} reference {value}")


def parse_decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value.strip() or "0")
    except InvalidOperation:
        return None


def validate_release(release_dir: Path, material_path: Path) -> dict[str, object]:
    table_keys = {
        "companies.tsv": ["company_code"],
        "departments.tsv": ["department_code"],
        "role_profiles.tsv": ["role_code"],
        "employees.tsv": ["employee_code"],
        "employee_assignments.tsv": ["assignment_code"],
        "user_accounts.tsv": ["user_email"],
        "projects.tsv": ["project_code"],
        "project_teams.tsv": ["project_code", "employee_code"],
        "warehouses.tsv": ["warehouse_code"],
        "cost_centers.tsv": ["cost_center_code"],
        "suppliers.tsv": ["supplier_code"],
        "supplier_contacts.tsv": ["contact_code"],
        "payment_terms.tsv": ["payment_term_code"],
        "price_lists.tsv": ["price_list_code"],
        "supplier_item_policies.tsv": ["supplier_code", "item_code"],
        "stock_opening_balances.tsv": ["opening_id"],
        "manifest.tsv": ["table_file"],
    }

    issues: list[str] = []
    tables: dict[str, list[dict[str, str]]] = {}
    indexes: dict[str, dict[str, dict[str, str]]] = {}

    for table_name, key in table_keys.items():
        path = release_dir / table_name
        if not path.exists():
            issues.append(f"missing table: {table_name}")
            continue
        issues.extend(check_column_counts(path))
        rows = read_tsv(path)
        tables[table_name] = rows
        index, key_issues = index_by(rows, key, table_name)
        indexes[table_name] = index
        issues.extend(key_issues)
        issues.extend(check_status(rows, table_name))

    if issues:
        return {"ok": False, "issues": issues, "table_counts": {}}

    companies = indexes["companies.tsv"]
    departments = indexes["departments.tsv"]
    roles = indexes["role_profiles.tsv"]
    employees = indexes["employees.tsv"]
    projects = indexes["projects.tsv"]
    warehouses = indexes["warehouses.tsv"]
    cost_centers = indexes["cost_centers.tsv"]
    suppliers = indexes["suppliers.tsv"]
    payment_terms = indexes["payment_terms.tsv"]
    price_lists = indexes["price_lists.tsv"]

    material_rows = read_tsv(material_path)
    material_codes = {row.get("item_code", "").strip() for row in material_rows}

    for row_no, row in enumerate(tables["departments.tsv"], start=2):
        require_ref(issues, "departments.tsv", row_no, "company_code", companies, row["company_code"])
        require_ref(
            issues,
            "departments.tsv",
            row_no,
            "parent_department_code",
            departments,
            row["parent_department_code"],
        )

    for row_no, row in enumerate(tables["cost_centers.tsv"], start=2):
        require_ref(issues, "cost_centers.tsv", row_no, "company_code", companies, row["company_code"])
        require_ref(
            issues,
            "cost_centers.tsv",
            row_no,
            "parent_cost_center_code",
            cost_centers,
            row["parent_cost_center_code"],
        )
        require_ref(issues, "cost_centers.tsv", row_no, "project_code", projects, row["project_code"])

    for row_no, row in enumerate(tables["warehouses.tsv"], start=2):
        require_ref(issues, "warehouses.tsv", row_no, "company_code", companies, row["company_code"])
        require_ref(
            issues,
            "warehouses.tsv",
            row_no,
            "parent_warehouse_code",
            warehouses,
            row["parent_warehouse_code"],
        )
        require_ref(
            issues,
            "warehouses.tsv",
            row_no,
            "manager_employee_code",
            employees,
            row["manager_employee_code"],
        )

    for row_no, row in enumerate(tables["projects.tsv"], start=2):
        require_ref(issues, "projects.tsv", row_no, "company_code", companies, row["company_code"])
        require_ref(issues, "projects.tsv", row_no, "cost_center_code", cost_centers, row["cost_center_code"])
        require_ref(
            issues,
            "projects.tsv",
            row_no,
            "project_manager_employee_code",
            employees,
            row["project_manager_employee_code"],
        )
        require_ref(
            issues,
            "projects.tsv",
            row_no,
            "default_warehouse_code",
            warehouses,
            row["default_warehouse_code"],
        )
        operating_status = row.get("project_operating_status", "").strip()
        if operating_status and operating_status not in ALLOWED_PROJECT_OPERATING_STATUS:
            issues.append(
                f"projects.tsv: line {row_no} unsupported project_operating_status={operating_status}"
            )

    for row_no, row in enumerate(tables["employees.tsv"], start=2):
        require_ref(issues, "employees.tsv", row_no, "department_code", departments, row["department_code"])
        require_ref(issues, "employees.tsv", row_no, "role_code", roles, row["role_code"])
        require_ref(
            issues,
            "employees.tsv",
            row_no,
            "default_project_code",
            projects,
            row["default_project_code"],
        )
        require_ref(
            issues,
            "employees.tsv",
            row_no,
            "default_warehouse_code",
            warehouses,
            row["default_warehouse_code"],
        )

    for row_no, row in enumerate(tables["employee_assignments.tsv"], start=2):
        require_ref(
            issues,
            "employee_assignments.tsv",
            row_no,
            "employee_code",
            employees,
            row["employee_code"],
        )
        require_ref(
            issues,
            "employee_assignments.tsv",
            row_no,
            "role_code",
            roles,
            row["role_code"],
        )
        scope_type = row.get("scope_type", "").strip()
        scope_code = row.get("scope_code", "").strip()
        if scope_type == "organization":
            require_ref(
                issues,
                "employee_assignments.tsv",
                row_no,
                "scope_code",
                departments,
                scope_code,
            )
        elif scope_type in {"project", "base"}:
            require_ref(
                issues,
                "employee_assignments.tsv",
                row_no,
                "scope_code",
                projects,
                scope_code,
            )
        else:
            issues.append(
                f"employee_assignments.tsv: line {row_no} unsupported scope_type={scope_type}"
            )
        for flag_field in ("is_primary", "is_active"):
            flag = row.get(flag_field, "").strip()
            if flag not in {"0", "1"}:
                issues.append(
                    f"employee_assignments.tsv: line {row_no} unsupported {flag_field}={flag}"
                )

    for row_no, row in enumerate(tables["user_accounts.tsv"], start=2):
        require_ref(issues, "user_accounts.tsv", row_no, "employee_code", employees, row["employee_code"])
        require_ref(issues, "user_accounts.tsv", row_no, "role_code", roles, row["role_code"])

    for row_no, row in enumerate(tables["project_teams.tsv"], start=2):
        require_ref(issues, "project_teams.tsv", row_no, "project_code", projects, row["project_code"])
        require_ref(issues, "project_teams.tsv", row_no, "employee_code", employees, row["employee_code"])

    for row_no, row in enumerate(tables["suppliers.tsv"], start=2):
        require_ref(
            issues,
            "suppliers.tsv",
            row_no,
            "default_payment_term",
            payment_terms,
            row["default_payment_term"],
        )

    for row_no, row in enumerate(tables["supplier_contacts.tsv"], start=2):
        require_ref(
            issues,
            "supplier_contacts.tsv",
            row_no,
            "supplier_code",
            suppliers,
            row["supplier_code"],
        )

    for row_no, row in enumerate(tables["supplier_item_policies.tsv"], start=2):
        require_ref(
            issues,
            "supplier_item_policies.tsv",
            row_no,
            "supplier_code",
            suppliers,
            row["supplier_code"],
        )
        require_ref(
            issues,
            "supplier_item_policies.tsv",
            row_no,
            "price_list_code",
            price_lists,
            row["price_list_code"],
        )
        item_code = row["item_code"].strip()
        if item_code and item_code not in material_codes:
            issues.append(
                f"supplier_item_policies.tsv: line {row_no} missing material item_code {item_code}"
            )

    for row_no, row in enumerate(tables["stock_opening_balances.tsv"], start=2):
        require_ref(
            issues,
            "stock_opening_balances.tsv",
            row_no,
            "warehouse_code",
            warehouses,
            row["warehouse_code"],
        )
        item_code = row["item_code"].strip()
        if item_code and item_code not in material_codes:
            issues.append(
                f"stock_opening_balances.tsv: line {row_no} missing material item_code {item_code}"
            )
        qty = parse_decimal(row.get("qty", ""))
        valuation_rate = parse_decimal(row.get("valuation_rate", ""))
        if qty is None:
            issues.append(f"stock_opening_balances.tsv: line {row_no} invalid qty={row.get('qty')}")
        elif qty != 0:
            issues.append(f"stock_opening_balances.tsv: line {row_no} qty must be 0, got {qty}")
        if valuation_rate is None:
            issues.append(
                f"stock_opening_balances.tsv: line {row_no} invalid valuation_rate={row.get('valuation_rate')}"
            )
        elif valuation_rate != 0:
            issues.append(
                f"stock_opening_balances.tsv: line {row_no} valuation_rate must be 0, got {valuation_rate}"
            )

    table_counts = {name: len(rows) for name, rows in sorted(tables.items())}
    return {"ok": not issues, "issues": issues, "table_counts": table_counts}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate master data release TSV files.")
    parser.add_argument("--release-dir", type=Path, default=DEFAULT_RELEASE_DIR)
    parser.add_argument("--material-path", type=Path, default=DEFAULT_MATERIAL_PATH)
    parser.add_argument("--json", action="store_true", help="Print full validation result as JSON.")
    args = parser.parse_args()

    result = validate_release(args.release_dir, args.material_path)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print("Master data release validation OK")
        for table_name, count in result["table_counts"].items():
            print(f"- {table_name}: {count}")
    else:
        print("Master data release validation FAILED")
        for issue in result["issues"]:
            print(f"- {issue}")

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
