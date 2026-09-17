from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexterp_agent.item_master.procurement_batch_review import (
    ProcurementBatchReviewStore,
    ProcurementReviewRuleCatalog,
    source_decision_hash,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _job(tmp_path: Path, *, selected_end: int = 101) -> tuple[Path, list[dict]]:
    job_dir = tmp_path / "jobs" / "pilot-review"
    job_dir.mkdir(parents=True)
    audit = {
        "status": "completed",
        "writes_erpnext": False,
        "source": {
            "source_sheet": "实际采购清单",
            "selected_start_row": 2,
            "selected_end_row": selected_end,
            "selected_row_count": 100,
        },
    }
    (job_dir / "audit.json").write_text(json.dumps(audit, ensure_ascii=False), encoding="utf-8")
    decisions = [
        {
            "cluster_id": "CL-0001",
            "queue": "needs_review",
            "source_rows": [15],
            "raw_names": ["Φ165变Φ110大小头"],
            "standard_type": "异径管",
            "gpc_brick_code": "10004024",
        },
        {
            "cluster_id": "CL-0002",
            "queue": "needs_review",
            "source_rows": [30],
            "raw_names": ["水管配件一批143元"],
            "standard_type": "水管配件",
            "gpc_brick_code": "",
        },
    ]
    _write_jsonl(job_dir / "decisions.jsonl", decisions)
    return job_dir, decisions


def test_rule_catalog_matches_reusable_positive_and_negative_rules() -> None:
    catalog = ProcurementReviewRuleCatalog()

    connector = catalog.match("PPR Φ110 90度弯头")
    cutting_tip = catalog.match("100型2#割嘴")

    assert any(row["rule_id"] == "R-PIPE-CONNECTOR" for row in connector)
    assert any(row["rule_id"] == "R-CUTTING-NOZZLE-DEFER" for row in cutting_tip)
    assert len(catalog.rules) == 19


def test_review_store_binds_decision_hash_and_freezes_only_when_complete(tmp_path: Path) -> None:
    _job(tmp_path)
    store = ProcurementBatchReviewStore(tmp_path, allowed_gpc_codes={"10008009"})
    status = store.status("pilot-review")
    first = status["items"][0]
    second = status["items"][1]

    saved = store.save("pilot-review", {
        "cluster_id": first["cluster_id"],
        "source_decision_sha256": first["source_decision_sha256"],
        "action": "revised",
        "materialization": "ready",
        "rule_ids": ["R-PIPE-CONNECTOR"],
        "rationale": "普通异径接头不属于调节流量的阀门。",
        "final_material": {
            "standard_type": "PPR异径接头",
            "gpc_brick_code": "10008009",
            "main_template_id": "standard_component",
            "stock_uom": "件",
            "constraint_ids": ["pressure_fluid"],
        },
    })
    assert saved["status"]["summary"]["reviewed"] == 1
    with pytest.raises(ValueError, match="仍有 1 个"):
        store.freeze("pilot-review")

    store.save("pilot-review", {
        "cluster_id": second["cluster_id"],
        "source_decision_sha256": second["source_decision_sha256"],
        "action": "excluded",
        "materialization": "excluded",
        "rule_ids": ["R-BUNDLE-SPLIT"],
        "rationale": "笼统一批没有可复用的逐项身份，必须拆单。",
        "final_material": {},
    })
    release = store.freeze("pilot-review")

    assert release["decision_count"] == 2
    assert release["rules_catalog_sha256"] == store.rules.catalog_sha256
    assert release["next_rows_processed"] is False
    assert release["writes_erpnext"] is False
    assert release["source"]["selected_end_row"] == 101
    assert store.status("pilot-review")["summary"]["frozen"] is True


def test_review_store_rejects_stale_candidate_and_out_of_scope_source(tmp_path: Path) -> None:
    _job(tmp_path)
    store = ProcurementBatchReviewStore(tmp_path)
    item = store.status("pilot-review")["items"][0]
    with pytest.raises(ValueError, match="候选内容已变化"):
        store.save("pilot-review", {
            "cluster_id": item["cluster_id"],
            "source_decision_sha256": "stale",
            "action": "deferred",
            "materialization": "hold",
            "rule_ids": ["R-PIPE-CONNECTOR"],
            "rationale": "暂缓等待必要信息完成后再审。",
        })

    other = tmp_path / "other"
    _job(other, selected_end=301)
    with pytest.raises(ValueError, match="只允许到源表第 101 行"):
        ProcurementBatchReviewStore(other).status("pilot-review")


def test_source_hash_is_stable_and_sensitive() -> None:
    row = {"cluster_id": "CL-1", "source_rows": [15], "raw_names": ["异径管"]}
    assert source_decision_hash(row) == source_decision_hash(dict(reversed(list(row.items()))))
    assert source_decision_hash(row) != source_decision_hash({**row, "source_rows": [16]})
