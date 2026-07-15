from __future__ import annotations

import csv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MASTER_DIR = REPO_ROOT / "data" / "master_data" / "release_v0_1"


def read_tsv(name: str) -> list[dict[str, str]]:
    with (MASTER_DIR / name).open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def test_test_supplier_has_a_price_for_every_released_item() -> None:
    policies = read_tsv("supplier_item_policies.tsv")

    assert len(policies) == 1979
    assert {row["supplier_code"] for row in policies} == {"SUP-TEST-ALL"}
    assert len({row["item_code"] for row in policies}) == 1979
    assert all(float(row["default_rate"]) > 0 for row in policies)


def test_project_teams_are_derived_from_active_assignments() -> None:
    teams = read_tsv("project_teams.tsv")

    assert len(teams) == 6
    assert {row["project_code"] for row in teams} == {"PRJ-HL-13", "PRJ-WCL-BASE"}
    assert any(row["employee_code"] == "EMP-HUYINHU" and row["member_role"] == "项目经理" for row in teams)


def test_zero_inventory_does_not_create_opening_rows() -> None:
    assert read_tsv("stock_opening_balances.tsv") == []
