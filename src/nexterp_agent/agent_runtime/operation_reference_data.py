from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from nexterp_agent.item_master.release_resolver import ReleaseMaterialResolver


class OperationReferenceDataCatalog:
    """Read-only demo provider mirroring the ERPNext tables used by field slots."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.master_data = root / "data" / "master_data" / "release_v0_1"
        self.material_file = root / "data" / "material_master" / "release_v1_0" / "material_master_release_v1_0.tsv"
        self.material_resolver = ReleaseMaterialResolver(self.material_file)

    def options(self, entity: str, *, query: str = "", project: str = "", item_code: str = "") -> list[dict[str, Any]]:
        if entity == "company":
            return self._companies()
        if entity == "project":
            return self._projects(query)
        if entity == "warehouse":
            return self._warehouses(project, query)
        if entity == "item":
            return self._items(query)
        if entity == "uom":
            return self._uoms(item_code)
        if entity == "supplier":
            return self._suppliers(query)
        return []

    def _companies(self) -> list[dict[str, Any]]:
        return [
            {"value": row["erpnext_company_name"], "label": row["company_name"], "meta": row["company_code"]}
            for row in self._read(self.master_data / "companies.tsv")
            if row.get("status") == "active"
        ]

    def _projects(self, query: str) -> list[dict[str, Any]]:
        needle = query.casefold().strip()
        erpnext_names = self._project_erpnext_names()
        rows = []
        for row in self._read(self.master_data / "projects.tsv"):
            haystack = " ".join((
                row.get("project_code", ""),
                row.get("project_name", ""),
                row.get("project_short_name", ""),
                erpnext_names.get(row.get("project_code", ""), ""),
            )).casefold()
            if row.get("status") != "active" or (needle and needle not in haystack):
                continue
            rows.append({
                "value": erpnext_names.get(row["project_code"], row["project_code"]),
                "label": row["project_short_name"],
                "meta": row["project_name"],
                "source_code": row["project_code"],
                "default_warehouse_code": row.get("default_warehouse_code", ""),
            })
        return rows[:20]

    def _warehouses(self, project: str, query: str) -> list[dict[str, Any]]:
        needle = query.casefold().strip()
        source_project = self._project_source_code(project)
        rows = []
        for row in self._read(self.master_data / "warehouses.tsv"):
            haystack = " ".join((row.get("warehouse_code", ""), row.get("warehouse_name", ""), row.get("erpnext_warehouse_name", ""))).casefold()
            if row.get("status") != "active" or row.get("is_group") == "1":
                continue
            if source_project and row.get("project_code") not in ("", source_project):
                continue
            if needle and needle not in haystack:
                continue
            rows.append({
                "value": row["erpnext_warehouse_name"],
                "label": row["warehouse_name"],
                "meta": row.get("warehouse_type", ""),
                "project": row.get("project_code", ""),
            })
        return rows[:20]

    def _items(self, query: str) -> list[dict[str, Any]]:
        ranked = self.material_resolver.resolve(query, limit=40).get("candidates", [])
        rows = []
        for candidate in ranked:
            row = candidate.get("data") or {}
            if row.get("status") != "active":
                continue
            rows.append({
                "value": candidate["item_code"],
                "label": candidate.get("sku_name") or candidate.get("item_name") or candidate["item_code"],
                "meta": row.get("required_specs", ""),
                "stock_uom": row.get("stock_uom", ""),
                "purchase_uom": row.get("purchase_uom", ""),
                "score": candidate.get("score", 0),
                "match_reason": candidate.get("match_reason", ""),
            })
            if len(rows) >= 20:
                break
        return rows

    def _uoms(self, item_code: str) -> list[dict[str, Any]]:
        for row in self._read(self.material_file):
            if row.get("item_code") != item_code:
                continue
            units = []
            for value in (row.get("stock_uom", ""), row.get("purchase_uom", "")):
                if value and value not in units:
                    units.append(value)
            return [{"value": value, "label": value, "meta": "物料允许单位"} for value in units]
        return []

    def _suppliers(self, query: str) -> list[dict[str, Any]]:
        needle = query.casefold().strip()
        rows = []
        for row in self._read(self.master_data / "suppliers.tsv"):
            haystack = " ".join((
                row.get("supplier_code", ""),
                row.get("supplier_name", ""),
                row.get("primary_category", ""),
            )).casefold()
            if row.get("status") != "active" or (needle and needle not in haystack):
                continue
            rows.append({
                "value": row["supplier_name"],
                "label": row["supplier_name"],
                "source_code": row.get("supplier_code", ""),
                "meta": row.get("primary_category", ""),
            })
        return rows[:20]

    def _project_erpnext_names(self) -> dict[str, str]:
        report = self.root / "data" / "runtime" / "master_data_apply_report.json"
        if not report.exists():
            return {}
        payload = json.loads(report.read_text(encoding="utf-8"))
        names = {}
        for row in payload.get("results", []):
            key = str(row.get("key") or "")
            if key.startswith("project-team:") and row.get("name"):
                names[key.removeprefix("project-team:")] = str(row["name"])
        return names

    def _project_source_code(self, value: str) -> str:
        for source_code, erpnext_name in self._project_erpnext_names().items():
            if value in (source_code, erpnext_name):
                return source_code
        return value

    @staticmethod
    def _read(path: Path) -> list[dict[str, str]]:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle, delimiter="\t"))
