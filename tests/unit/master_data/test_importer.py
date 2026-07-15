from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nexterp_agent.master_data import ImportOperation, MasterDataImporter, build_import_operations


@dataclass
class Result:
    ok: bool
    data: Any = None
    error_type: str | None = None
    error: str | None = None


class FakeClient:
    def __init__(self) -> None:
        self.documents: dict[tuple[str, str], dict[str, Any]] = {}
        self.updates: list[dict[str, Any]] = []

    def get_document(self, doctype: str, name: str) -> Result:
        data = self.documents.get((doctype, name))
        return Result(ok=data is not None, data=data, error_type=None if data else "not_found")

    def search_documents(self, doctype: str, *, filters=None, fields=None, limit=20, offset=0, order_by=None) -> Result:
        matches = []
        for (candidate_doctype, name), data in self.documents.items():
            if candidate_doctype != doctype:
                continue
            if all(data.get(key) == value for key, value in (filters or {}).items()):
                requested = fields or ["name"]
                matches.append({field: name if field == "name" else data.get(field) for field in requested})
        return Result(ok=True, data=matches[offset : offset + limit])

    def create_document(self, doctype: str, data: dict[str, Any]) -> Result:
        name = data.get("name") or f"generated-{len(self.documents) + 1}"
        stored = {**data, "name": name}
        self.documents[(doctype, name)] = stored
        return Result(ok=True, data=stored)

    def update_document(self, doctype: str, name: str, data: dict[str, Any]) -> Result:
        self.updates.append(data)
        stored = {**self.documents[(doctype, name)], **data, "name": name}
        self.documents[(doctype, name)] = stored
        return Result(ok=True, data=stored)


def test_release_builds_a_complete_ordered_plan() -> None:
    operations = build_import_operations()

    assert len(operations) > 4000
    assert sum(operation.doctype == "Item" for operation in operations) == 1979
    assert sum(operation.doctype == "Item Price" for operation in operations) == 1979
    assert sum(operation.doctype == "User" for operation in operations) == 8
    assert sum(operation.doctype == "Project" for operation in operations) == 10
    assert operations[0].doctype == "Company"


def test_apply_is_idempotent_for_named_and_composite_operations() -> None:
    client = FakeClient()
    operations = [
        ImportOperation("item:A", "items", "Item", {"name": "A", "item_code": "A"}, lookup_name="A"),
        ImportOperation(
            "price:A",
            "prices",
            "Item Price",
            {"item_code": "A", "price_list": "Standard Buying", "supplier": "SUP", "uom": "个", "price_list_rate": 1},
            lookup_filters={"item_code": "A", "price_list": "Standard Buying", "supplier": "SUP", "uom": "个"},
        ),
    ]
    importer = MasterDataImporter(client, operations)

    first = importer.apply()
    second = importer.apply()
    verification = importer.verify()

    assert first["failed_count"] == 0
    assert second["failed_count"] == 0
    assert second["processed_count"] == 2
    assert verification["failed_count"] == 0
    assert client.updates
    assert all("name" not in update for update in client.updates)
