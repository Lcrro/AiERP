from __future__ import annotations

from pathlib import Path

from nexterp_agent.agent_runtime.operation_reference_data import OperationReferenceDataCatalog


ROOT = Path(__file__).resolve().parents[3]


def test_project_options_use_erpnext_names_and_business_labels() -> None:
    options = OperationReferenceDataCatalog(ROOT).options("project", query="合流")

    assert options == [{
        "value": "PROJ-0010",
        "label": "合流1.3标",
        "meta": "合流污水一期复线工程（其他部分）FXQ1.3标4-15井",
        "source_code": "PRJ-HL-13",
        "default_warehouse_code": "WH-HL-13",
    }]


def test_warehouse_options_follow_selected_project() -> None:
    options = OperationReferenceDataCatalog(ROOT).options("warehouse", project="PROJ-0010")

    assert any(option["value"] == "合流1.3标仓库 - SD" for option in options)
    assert all(option["project"] in ("", "PRJ-HL-13") for option in options)
    assert not any(option["value"] == "南京一期仓库 - SD" for option in options)


def test_item_search_and_uom_options_come_from_material_master() -> None:
    catalog = OperationReferenceDataCatalog(ROOT)

    items = catalog.options("item", query="MAT-CEM-000008")
    units = catalog.options("uom", item_code="MAT-CEM-000008")

    assert items[0]["value"] == "MAT-CEM-000008"
    assert items[0]["label"] == "水泥 42.5 袋装 50kg"
    assert units == [{"value": "包", "label": "包", "meta": "物料允许单位"}]
