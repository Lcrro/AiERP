from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from nexterp_agent.workbench.material_test_sync import MaterialTestSyncGate
from nexterp_agent.workbench.server import AgentWorkbenchService


RELEASE_HASH = "a" * 64
ROOT = Path(__file__).resolve().parents[3]


def test_material_classification_surface_exposes_two_step_sync_control() -> None:
    html = (ROOT / "tools" / "tariff_taxonomy_browser.html").read_text(encoding="utf-8")
    script = (ROOT / "tools" / "workbench" / "tariff-taxonomy-browser.js").read_text(encoding="utf-8")
    server = (ROOT / "src" / "nexterp_agent" / "workbench" / "server.py").read_text(encoding="utf-8")

    assert "同步 ERPNext 测试账套" in html
    assert "sync-release-hash" in html and "sync-request-id" in html
    assert "/api/material-test-sync/plan" in script
    assert "/api/material-test-sync/apply" in script
    assert "state.materialTestSyncAvailable && state.catalog === \"gpc\"" in script
    assert 'set(payload) - {"release_hash", "request_id"}' in server


def test_sync_gate_applies_only_the_exact_frozen_plan_and_replays_result() -> None:
    applied: list[tuple[str, str]] = []

    def plan_runner(request_id: str) -> dict:
        return {
            "request_id": request_id,
            "release_hash": RELEASE_HASH,
            "catalog_revision": 12,
            "counts": {"items": 3},
            "plan": {
                "summary": {"create": 1, "update": 1, "unchanged": 1, "conflict": 0, "extra": 0},
                "conflicts": [],
                "extra_item_codes": [],
                "target_managed_items": 2,
            },
        }

    def apply_runner(request_id: str, release_hash: str) -> dict:
        applied.append((request_id, release_hash))
        return {"request_id": request_id, "release_hash": release_hash, "items": {"created": 1}}

    gate = MaterialTestSyncGate(plan_runner=plan_runner, apply_runner=apply_runner)
    plan = gate.plan()
    result = gate.apply(request_id=plan["request_id"], release_hash=plan["release_hash"])
    replay = gate.apply(request_id=plan["request_id"], release_hash=plan["release_hash"])

    assert plan["summary"]["create"] == 1
    assert result == replay
    assert applied == [(plan["request_id"], RELEASE_HASH)]


def test_sync_gate_mismatch_is_a_noop() -> None:
    writes: list[tuple[str, str]] = []
    gate = MaterialTestSyncGate(
        plan_runner=lambda request_id: {
            "request_id": request_id,
            "release_hash": RELEASE_HASH,
            "plan": {"summary": {"create": 0}, "target_managed_items": 0},
        },
        apply_runner=lambda request_id, release_hash: writes.append((request_id, release_hash)) or {},
    )
    plan = gate.plan()

    with pytest.raises(ValueError, match="release_hash.*不一致"):
        gate.apply(request_id=plan["request_id"], release_hash="b" * 64)
    with pytest.raises(ValueError, match="未找到"):
        gate.apply(request_id=str(uuid4()), release_hash=RELEASE_HASH)

    assert writes == []


def test_sync_gate_conflict_plan_is_a_noop() -> None:
    writes: list[tuple[str, str]] = []
    gate = MaterialTestSyncGate(
        plan_runner=lambda request_id: {
            "request_id": request_id,
            "release_hash": RELEASE_HASH,
            "plan": {"summary": {"conflict": 1}, "target_managed_items": 1},
        },
        apply_runner=lambda request_id, release_hash: writes.append((request_id, release_hash)) or {},
    )
    plan = gate.plan()

    with pytest.raises(ValueError, match="包含冲突"):
        gate.apply(request_id=plan["request_id"], release_hash=plan["release_hash"])

    assert writes == []


def test_workbench_sync_is_profile_scoped_and_rejects_low_level_parameters() -> None:
    service = AgentWorkbenchService.__new__(AgentWorkbenchService)
    service.profile = "civil"
    with pytest.raises(PermissionError, match="material_test"):
        service.material_test_sync_plan()

    service.profile = "material_test"
    service.material_test_sync = MaterialTestSyncGate(
        plan_runner=lambda request_id: {
            "request_id": request_id,
            "release_hash": RELEASE_HASH,
            "plan": {"summary": {}, "target_managed_items": 0},
        }
    )
    with pytest.raises(ValueError, match="只接受"):
        service.material_test_sync_apply({
            "request_id": str(uuid4()),
            "release_hash": RELEASE_HASH,
            "site_url": "https://example.invalid",
        })
