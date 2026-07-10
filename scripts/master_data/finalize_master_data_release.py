from __future__ import annotations

import csv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MASTER_DIR = REPO_ROOT / "data" / "master_data" / "release_v0_1"
MATERIAL_PATH = REPO_ROOT / "data" / "material_master" / "release_v1_0" / "material_master_release_v1_0.tsv"
TEST_SUPPLIER_CODE = "SUP-TEST-ALL"
TEST_PRICE_LIST_CODE = "PL-BUY-STD"


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def lead_time_for_group(top_group: str) -> int:
    if top_group in {"清洁办公后勤", "劳保防护", "包装覆盖周转"}:
        return 2
    if top_group in {"建筑材料", "电气电料", "紧固件与连接件", "工具量具", "工具耗材"}:
        return 3
    if top_group in {"管材管件阀门", "金属材料", "液压气动", "设备备件"}:
        return 7
    if top_group in {"定制加工件", "施工机械设备"}:
        return 14
    return 5


def build_supplier_item_policies(material_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for material in material_rows:
        rows.append(
            {
                "supplier_code": TEST_SUPPLIER_CODE,
                "top_group": material["top_group"],
                "material_family": material["material_family"],
                "item_code": material["item_code"],
                "preferred_rank": "1",
                "price_list_code": TEST_PRICE_LIST_CODE,
                "default_purchase_uom": material["purchase_uom"],
                "default_rate": material["estimated_rate"],
                "lead_time_days": str(lead_time_for_group(material["top_group"])),
                "price_valid_from": "2026-07-01",
                "price_valid_to": "2027-06-30",
                "note": "测试综合供应商初始化价格；非真实报价，不得用于生产采购。",
            }
        )
    return rows


def build_project_teams(assignments: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for assignment in assignments:
        if assignment["scope_type"] not in {"project", "base"} or assignment["is_active"] != "1":
            continue
        rows.append(
            {
                "project_code": assignment["scope_code"],
                "team_code": assignment["assignment_code"],
                "team_name": assignment["scope_name"],
                "employee_code": assignment["employee_code"],
                "member_role": assignment["position"],
                "status": "active",
                "note": "由 employee_assignments.tsv 中的有效项目/基地任职关系生成。",
            }
        )
    return rows


def main() -> int:
    material_rows = read_tsv(MATERIAL_PATH)
    policies = build_supplier_item_policies(material_rows)
    write_tsv(
        MASTER_DIR / "supplier_item_policies.tsv",
        [
            "supplier_code",
            "top_group",
            "material_family",
            "item_code",
            "preferred_rank",
            "price_list_code",
            "default_purchase_uom",
            "default_rate",
            "lead_time_days",
            "price_valid_from",
            "price_valid_to",
            "note",
        ],
        policies,
    )

    assignments = read_tsv(MASTER_DIR / "employee_assignments.tsv")
    project_teams = build_project_teams(assignments)
    write_tsv(
        MASTER_DIR / "project_teams.tsv",
        ["project_code", "team_code", "team_name", "employee_code", "member_role", "status", "note"],
        project_teams,
    )

    write_tsv(
        MASTER_DIR / "stock_opening_balances.tsv",
        ["opening_id", "warehouse_code", "item_code", "qty", "valuation_rate", "posting_date", "note"],
        [],
    )

    print(f"supplier_item_policies={len(policies)}")
    print(f"project_teams={len(project_teams)}")
    print("stock_opening_balances=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
