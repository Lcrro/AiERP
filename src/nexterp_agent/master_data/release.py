from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MASTER_DATA_DIR = REPO_ROOT / "data" / "master_data" / "release_v0_1"
DEFAULT_MATERIAL_RELEASE = REPO_ROOT / "data" / "material_master" / "release_v1_0" / "material_master_release_v1_0.tsv"


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


@dataclass(frozen=True)
class MasterDataRelease:
    master_data_dir: Path = DEFAULT_MASTER_DATA_DIR
    material_release_path: Path = DEFAULT_MATERIAL_RELEASE

    def table(self, name: str, *, include_candidates: bool = True) -> list[dict[str, str]]:
        rows = read_tsv(self.master_data_dir / name)
        allowed = {"active", "candidate"} if include_candidates else {"active"}
        return [row for row in rows if not row.get("status") or row.get("status") in allowed]

    @property
    def materials(self) -> list[dict[str, str]]:
        return read_tsv(self.material_release_path)

    @property
    def companies(self) -> dict[str, dict[str, str]]:
        return {row["company_code"]: row for row in self.table("companies.tsv")}

    @property
    def roles(self) -> dict[str, dict[str, str]]:
        return {row["role_code"]: row for row in self.table("role_profiles.tsv")}

    @property
    def projects(self) -> dict[str, dict[str, str]]:
        return {row["project_code"]: row for row in self.table("projects.tsv")}

    @property
    def warehouses(self) -> dict[str, dict[str, str]]:
        return {row["warehouse_code"]: row for row in self.table("warehouses.tsv")}

    @property
    def employees(self) -> dict[str, dict[str, str]]:
        return {row["employee_code"]: row for row in self.table("employees.tsv")}

    @property
    def assignments(self) -> list[dict[str, str]]:
        return self.table("employee_assignments.tsv")

    @property
    def departments(self) -> dict[str, dict[str, str]]:
        return {row["department_code"]: row for row in self.table("departments.tsv")}

    def company_name(self, code: str) -> str:
        return self.companies[code]["erpnext_company_name"]

    def company_abbr(self, code: str) -> str:
        return self.companies[code]["abbr"]

    def cost_center_name(self, row: dict[str, str]) -> str:
        if not row.get("parent_cost_center_code") and row.get("is_group") == "1":
            return f"{self.company_name(row['company_code'])} - {self.company_abbr(row['company_code'])}"
        return f"{row['cost_center_name']} - {self.company_abbr(row['company_code'])}"
