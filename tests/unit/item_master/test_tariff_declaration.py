from __future__ import annotations

import json
from pathlib import Path
import time

from nexterp_agent.item_master.tariff_declaration import (
    DeclarationParserState,
    TariffDeclarationJobManager,
    _deduplicate_profiles,
    parse_declaration_page_text,
    validate_declaration_profiles,
)


def test_parse_sand_rows_keeps_heading_and_declaration_attributes() -> None:
    rows = parse_declaration_page_text(
        """
        25.05 各种天然砂，不论是否着色，但
        第二十六章的含金属矿砂除外：
        1.来源（如海砂、湖砂或河砂等）
        2505.1000 -硅砂及石英砂
        2505.9000 -其他
        """,
        page=105,
    )

    assert [row.code for row in rows] == ["25051000", "25059000"]
    assert all(row.heading_code == "2505" for row in rows)
    assert rows[0].heading_name == "各种天然砂，不论是否着色，但第二十六章的含金属矿砂除外："
    assert rows[1].declaration_attributes == ("来源（如海砂、湖砂或河砂等）",)


def test_parser_restores_wrapped_tariff_name_before_attributes() -> None:
    rows = parse_declaration_page_text(
        "7318.1510 ----抗拉强度在800兆帕及以\n上 1.材质；2.抗拉强度；3.品牌（中文或外文名称）；4.型号；5.杆径",
        page=431,
    )

    assert len(rows) == 1
    assert rows[0].name == "抗拉强度在800兆帕及以上"
    assert rows[0].declaration_attributes[:2] == ("材质", "抗拉强度")
    assert rows[0].declaration_attributes[2] == "品牌（中文或外文名称）"
    assert rows[0].classification_attributes[:2] == ("材质", "抗拉强度")


def test_parser_carries_hierarchy_and_attributes_across_pages() -> None:
    state = DeclarationParserState()
    page_one = """
        84.81 用于管道、锅炉、罐、桶或类似品的龙头，旋塞、阀门及类似装置：
        -其他器具：
        --换向阀：
    """
    page_two = "8481.8029 ----其他 1.用途；2.是否电磁式；3.品牌（中文或外文名称）；4.型号"
    rows = parse_declaration_page_text(page_one, page=525, state=state, finalize=False)
    rows += parse_declaration_page_text(page_two, page=525, state=state)

    assert len(rows) == 1
    assert rows[0].hierarchy_path == ("其他器具：", "换向阀：")
    assert rows[0].heading_name.startswith("用于管道、锅炉")
    assert rows[0].classification_attributes[:2] == ("用途", "是否电磁式")


def test_deduplicate_and_validate_profiles() -> None:
    rows = parse_declaration_page_text("25.05 天然砂\n2505.9000 -其他 1.来源", page=1)
    rows += parse_declaration_page_text("25.05 天然砂\n2505.9000 -其他 1.来源；2.粒度", page=2)
    rows = _deduplicate_profiles(rows)
    assert len(rows) == 1
    assert rows[0].declaration_attributes == ("来源", "粒度")
    assert validate_declaration_profiles(rows) == []


def test_demo_job_writes_read_only_evidence_package(tmp_path: Path) -> None:
    manager = TariffDeclarationJobManager(tmp_path)
    job = manager.start({"mode": "demo"})
    done = manager.snapshot(job["job_id"])
    for _ in range(100):
        if done["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.02)
        done = manager.snapshot(job["job_id"])
    assert done["status"] == "completed"
    assert done["issues_found"] == 0
    profile_path = Path(done["output_files"][0])
    assert json.loads(profile_path.read_text(encoding="utf-8"))['code'] == "25059000"
    manifest = json.loads(Path(done["output_files"][1]).read_text(encoding="utf-8"))
    assert manifest["erpnext_written"] is False
