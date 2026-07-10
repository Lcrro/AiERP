from __future__ import annotations

import csv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
RELEASE_PATH = REPO_ROOT / "data" / "material_master" / "release_v1_0" / "material_master_release_v1_0.tsv"


def load_release() -> list[dict[str, str]]:
    with RELEASE_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def test_authoritative_release_has_1979_unique_rows() -> None:
    rows = load_release()

    assert len(rows) == 1979
    assert len({row["item_code"] for row in rows}) == 1979
    assert all(row["item_name"] and row["sku_name"] and row["stock_uom"] for row in rows)


def test_fixed_length_pipe_uses_root_unit_and_root_price() -> None:
    row = next(row for row in load_release() if row["item_code"] == "PIPE-000411")

    assert row["stock_uom"] == "根"
    assert row["purchase_uom"] == "根"
    assert row["estimated_rate"] == "2520.00"
    assert "6m" in row["sku_name"]


def test_sandbox_unit_conflicts_receive_new_v1_codes() -> None:
    rows = load_release()
    codes = {row["item_code"] for row in rows}

    assert "SAFE-000006" not in codes
    assert "SAFE-000006-V1" in codes
    replacement = next(row for row in rows if row["item_code"] == "SAFE-000006-V1")
    assert replacement["source_item_codes"] == "SAFE-000006"
    assert replacement["stock_uom"] == "双"
