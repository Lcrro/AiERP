from __future__ import annotations

import json
from pathlib import Path

from nexterp_agent.workbench import server


ROOT = Path(__file__).resolve().parents[3]


def test_runtime_material_code_map_translates_legacy_publication_ids(tmp_path, monkeypatch) -> None:
    mapping_path = tmp_path / "material-item-code-map.json"
    mapping_path.write_text(
        json.dumps({"material_item_codes": {"LH-GPC-P0077-A": "1000557301001"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "MATERIAL_ITEM_CODE_MAP_PATH", mapping_path)

    assert server._load_material_item_code_map() == {"LH-GPC-P0077-A": "1000557301001"}


def test_marketplace_rehydrates_every_saved_cart_row_before_handoff() -> None:
    script = (ROOT / "tools" / "workbench" / "material-marketplace.js").read_text(encoding="utf-8")
    assert "hydrateCartRows" in script
    assert "savedRows = [...state.cart.values()]" in script
    assert "q=${encodeURIComponent(row.material_id)}" in script
    assert "group_variants=0" in script


def test_marketplace_displays_erpnext_item_code_not_publication_id() -> None:
    script = (ROOT / "tools" / "workbench" / "material-marketplace.js").read_text(encoding="utf-8")
    assert "const displayItemCode = row => row?.item_code" in script
    assert "<code>${esc(displayItemCode(row))}</code>" in script
    assert "<small>${esc(displayItemCode(row))}" in script
    assert "<div class=\"dialog-meta\"><span>${esc(displayItemCode(row))}</span>" in script
