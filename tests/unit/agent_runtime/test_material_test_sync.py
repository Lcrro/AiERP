from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
from uuid import uuid4

import pytest

from nexterp_agent.workbench.material_test_sync import MaterialTestSyncGate
from nexterp_agent.workbench.server import AgentWorkbenchService


RELEASE_HASH = "a" * 64
ROOT = Path(__file__).resolve().parents[3]
EMPLOYEE = {
    "employee_code": "EMP-MAOXIAOQUAN",
    "employee_name": "毛晓泉",
    "user_email": "mao.xiaoquan@stec-up.local",
}


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

    def plan_runner(request_id: str, employee: dict) -> dict:
        assert employee == EMPLOYEE
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

    def apply_runner(request_id: str, release_hash: str, employee: dict) -> dict:
        assert employee == EMPLOYEE
        applied.append((request_id, release_hash))
        return {"request_id": request_id, "release_hash": release_hash, "items": {"created": 1}}

    gate = MaterialTestSyncGate(plan_runner=plan_runner, apply_runner=apply_runner)
    plan = gate.plan(employee=EMPLOYEE)
    result = gate.apply(request_id=plan["request_id"], release_hash=plan["release_hash"], employee=EMPLOYEE)
    replay = gate.apply(request_id=plan["request_id"], release_hash=plan["release_hash"], employee=EMPLOYEE)

    assert plan["summary"]["create"] == 1
    assert result == replay
    assert applied == [(plan["request_id"], RELEASE_HASH)]
    assert plan["employee"] == EMPLOYEE
    assert result["employee"] == EMPLOYEE


def test_sync_gate_mismatch_is_a_noop() -> None:
    writes: list[tuple[str, str]] = []
    gate = MaterialTestSyncGate(
        plan_runner=lambda request_id, _employee: {
            "request_id": request_id,
            "release_hash": RELEASE_HASH,
            "plan": {"summary": {"create": 0}, "target_managed_items": 0},
        },
        apply_runner=lambda request_id, release_hash, _employee: writes.append((request_id, release_hash)) or {},
    )
    plan = gate.plan(employee=EMPLOYEE)

    with pytest.raises(ValueError, match="release_hash.*不一致"):
        gate.apply(request_id=plan["request_id"], release_hash="b" * 64, employee=EMPLOYEE)
    with pytest.raises(ValueError, match="未找到"):
        gate.apply(request_id=str(uuid4()), release_hash=RELEASE_HASH, employee=EMPLOYEE)

    assert writes == []


def test_sync_gate_conflict_plan_is_a_noop() -> None:
    writes: list[tuple[str, str]] = []
    gate = MaterialTestSyncGate(
        plan_runner=lambda request_id, _employee: {
            "request_id": request_id,
            "release_hash": RELEASE_HASH,
            "plan": {"summary": {"conflict": 1}, "target_managed_items": 1},
        },
        apply_runner=lambda request_id, release_hash, _employee: writes.append((request_id, release_hash)) or {},
    )
    plan = gate.plan(employee=EMPLOYEE)

    with pytest.raises(ValueError, match="包含冲突"):
        gate.apply(request_id=plan["request_id"], release_hash=plan["release_hash"], employee=EMPLOYEE)

    assert writes == []


def test_sync_gate_rejects_a_different_confirming_employee() -> None:
    gate = MaterialTestSyncGate(
        plan_runner=lambda request_id, _employee: {
            "request_id": request_id,
            "release_hash": RELEASE_HASH,
            "plan": {"summary": {}, "target_managed_items": 0},
        }
    )
    plan = gate.plan(employee=EMPLOYEE)
    other = {**EMPLOYEE, "user_email": "other@stec-up.local"}

    with pytest.raises(PermissionError, match="确认员工"):
        gate.apply(
            request_id=plan["request_id"],
            release_hash=plan["release_hash"],
            employee=other,
        )


def test_apply_is_serialized_across_different_frozen_plans() -> None:
    first_started = threading.Event()
    release_first = threading.Event()
    second_finished = threading.Event()
    active = 0
    maximum_active = 0
    counter_lock = threading.Lock()

    def plan_runner(request_id: str, _employee: dict) -> dict:
        return {
            "request_id": request_id,
            "release_hash": RELEASE_HASH,
            "plan": {"summary": {}, "target_managed_items": 0},
        }

    def apply_runner(request_id: str, release_hash: str, _employee: dict) -> dict:
        nonlocal active, maximum_active
        with counter_lock:
            active += 1
            maximum_active = max(maximum_active, active)
            is_first = not first_started.is_set()
        if is_first:
            first_started.set()
            assert release_first.wait(timeout=2)
        with counter_lock:
            active -= 1
        return {"request_id": request_id, "release_hash": release_hash}

    first_gate = MaterialTestSyncGate(plan_runner=plan_runner, apply_runner=apply_runner)
    second_gate = MaterialTestSyncGate(plan_runner=plan_runner, apply_runner=apply_runner)
    first = first_gate.plan(employee=EMPLOYEE)
    second = second_gate.plan(employee=EMPLOYEE)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(
            first_gate.apply,
            request_id=first["request_id"],
            release_hash=first["release_hash"],
            employee=EMPLOYEE,
        )
        assert first_started.wait(timeout=2)
        second_future = pool.submit(
            second_gate.apply,
            request_id=second["request_id"],
            release_hash=second["release_hash"],
            employee=EMPLOYEE,
        )
        second_future.add_done_callback(lambda _future: second_finished.set())
        assert not second_finished.wait(timeout=0.1)
        release_first.set()
        first_future.result(timeout=2)
        second_future.result(timeout=2)

    assert maximum_active == 1


def test_workbench_sync_is_profile_scoped_requires_cookie_and_rejects_low_level_parameters() -> None:
    service = AgentWorkbenchService.__new__(AgentWorkbenchService)
    service.profile = "civil"
    with pytest.raises(PermissionError, match="material_test"):
        service.material_test_sync_plan("")

    service.profile = "material_test"
    service.material_test_sync = MaterialTestSyncGate(
        plan_runner=lambda request_id, _employee: {
            "request_id": request_id,
            "release_hash": RELEASE_HASH,
            "plan": {"summary": {}, "target_managed_items": 0},
        }
    )
    with pytest.raises(PermissionError, match="登录员工"):
        service.material_test_sync_plan("")
    plan = service.material_test_sync_plan(
        "nexterp_business_user=mao.xiaoquan%40stec-up.local"
    )
    assert plan["employee"] == EMPLOYEE
    with pytest.raises(ValueError, match="只接受"):
        service.material_test_sync_apply("", {
            "request_id": str(uuid4()),
            "release_hash": RELEASE_HASH,
            "site_url": "https://example.invalid",
        })
    with pytest.raises(ValueError, match="只接受"):
        service.material_test_sync_apply(
            "nexterp_business_user=mao.xiaoquan%40stec-up.local",
            {
                "request_id": plan["request_id"],
                "release_hash": RELEASE_HASH,
                "employee": EMPLOYEE,
            },
        )
