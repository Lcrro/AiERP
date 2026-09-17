from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


DEFAULT_RUNTIME_PUBLICATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "runtime"
    / "material-intake-publications-v0.8.jsonl"
)


class PublishedMaterialType(BaseModel):
    """User-confirmed standard type snapshot used by runtime retrieval."""

    model_config = ConfigDict(extra="forbid")

    type_id: str
    top_group: str
    material_family: str
    standard_name: str
    definition: str = ""
    includes: str = ""
    excludes: str = ""
    aliases: list[str] = Field(default_factory=list)
    attributes: list[dict[str, Any]] = Field(default_factory=list)
    item_group: str
    code_prefix: str
    is_new: bool = False


class PublishedMaterialSku(BaseModel):
    """ERPNext-verified SKU snapshot merged into high-recall retrieval."""

    model_config = ConfigDict(extra="forbid")

    item_code: str
    type_id: str
    standard_name: str
    item_name: str
    sku_name: str
    item_group: str
    stock_uom: str
    required_specs: str = ""
    optional_specs: str = ""
    item_doc: dict[str, Any]
    erpnext_readback: dict[str, Any]


class MaterialPublication(BaseModel):
    """One atomic publication created only after ERPNext readback succeeds."""

    model_config = ConfigDict(extra="forbid")

    publication_id: str
    request_id: str
    draft_id: str
    analysis_id: str
    confirmed_by: str
    confirmed_at: str
    material_type: PublishedMaterialType
    sku: PublishedMaterialSku
    enabled: bool = True


class RuntimeMaterialPublicationStore:
    """Append-only runtime catalog for user-confirmed, ERPNext-verified items.

    The governed repository release remains immutable. Runtime publications are
    local business data under ``data/runtime`` and can later be migrated into
    the PostgreSQL governance catalog without changing the analyzer contract.
    """

    def __init__(self, path: str | Path = DEFAULT_RUNTIME_PUBLICATION_PATH) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def active(self) -> list[MaterialPublication]:
        if not self.path.exists():
            return []
        latest: dict[str, MaterialPublication] = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                publication = MaterialPublication.model_validate_json(line)
            except (ValueError, json.JSONDecodeError):
                continue
            latest[publication.sku.item_code] = publication
        return [row for row in latest.values() if row.enabled]

    def find_item(self, item_code: str) -> MaterialPublication | None:
        return next((row for row in self.active() if row.sku.item_code == item_code), None)

    def record_verified(
        self,
        *,
        request_id: str,
        draft_id: str,
        analysis_id: str,
        confirmed_by: str,
        material_type: dict[str, Any],
        sku: dict[str, Any],
    ) -> MaterialPublication:
        publication = MaterialPublication(
            publication_id=f"PUB-{request_id}-{draft_id}",
            request_id=request_id,
            draft_id=draft_id,
            analysis_id=analysis_id,
            confirmed_by=confirmed_by,
            confirmed_at=datetime.now(timezone.utc).isoformat(),
            material_type=PublishedMaterialType.model_validate(deepcopy(material_type)),
            sku=PublishedMaterialSku.model_validate(deepcopy(sku)),
        )
        with self._lock:
            existing = self.find_item(publication.sku.item_code)
            if existing is not None:
                if _publication_business_payload(existing) != _publication_business_payload(publication):
                    raise ValueError(f"运行期目录中的物料编码 {publication.sku.item_code} 与本次发布内容冲突")
                return existing
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(publication.model_dump_json() + "\n")
        return publication


def _publication_business_payload(publication: MaterialPublication) -> dict[str, Any]:
    return {
        "material_type": publication.material_type.model_dump(mode="json"),
        "sku": {
            key: value
            for key, value in publication.sku.model_dump(mode="json").items()
            if key != "erpnext_readback"
        },
    }
