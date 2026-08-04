from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from nexterp_agent.item_master.type_governance import PROMPT_VERSION
from nexterp_agent.item_master.type_governance_postgres import (
    PostgresTypeGovernanceCatalog,
)


load_dotenv()


@pytest.mark.integration
def test_type_governance_schema_and_exports_are_repeatable() -> None:
    dsn = os.getenv("MATERIAL_CATALOG_DATABASE_URL")
    if not dsn:
        pytest.skip("MATERIAL_CATALOG_DATABASE_URL is not configured")
    catalog = PostgresTypeGovernanceCatalog(dsn)

    catalog.setup_schema()
    catalog.setup_schema()
    first = catalog.export_rows()
    second = catalog.export_rows()

    assert first == second
    assert set(first) == {
        "material_type_dictionary",
        "material_type_aliases",
        "material_attribute_templates",
        "material_name_decisions",
        "sku_type_mapping",
        "material_governance_issues",
    }
    frozen = catalog.frozen_family_hashes(prompt_version=PROMPT_VERSION)
    if ("工具耗材", "钻头") in frozen:
        drill_mappings = [
            row
            for row in first["sku_type_mapping"]
            if row["item_code"].startswith("TOOL-")
            and any(
                item["type_id"] == row["type_id"]
                and item["top_group"] == "工具耗材"
                and item["material_family"] == "钻头"
                for item in first["material_type_dictionary"]
            )
        ]
        assert len(drill_mappings) == 54
