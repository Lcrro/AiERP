from __future__ import annotations

import json
from uuid import uuid4

import pytest

from scripts.erpnext.sync_gpc_materials_to_test_site import SyncError, apply_release, target_plan


EMPLOYEE = {
    "employee_code": "EMP-MAOXIAOQUAN",
    "employee_name": "毛晓泉",
    "user_email": "mao.xiaoquan@stec-up.local",
}


def test_target_plan_reports_release_diff_with_mocked_erpnext_io() -> None:
    class FakeERPNextClient:
        def list_docs(self, doctype, *, fields, filters, limit):
            assert doctype == "Item"
            return [
                {"item_code": "ITEM-UPDATE", "custom_nexterp_source_id": "SRC-2", "custom_nexterp_source_hash": "old", "disabled": 0},
                {"item_code": "ITEM-SAME", "custom_nexterp_source_id": "SRC-3", "custom_nexterp_source_hash": "same", "disabled": 0},
                {"item_code": "ITEM-CONFLICT", "custom_nexterp_source_id": "OTHER", "custom_nexterp_source_hash": "x", "disabled": 0},
                {"item_code": "ITEM-EXTRA", "custom_nexterp_source_id": "SRC-X", "custom_nexterp_source_hash": "x", "disabled": 0},
            ]

    release = {"items": [
        {"item_code": "ITEM-CREATE", "source_id": "SRC-1", "source_hash": "new"},
        {"item_code": "ITEM-UPDATE", "source_id": "SRC-2", "source_hash": "new"},
        {"item_code": "ITEM-SAME", "source_id": "SRC-3", "source_hash": "same"},
        {"item_code": "ITEM-CONFLICT", "source_id": "SRC-4", "source_hash": "new"},
    ]}

    plan = target_plan(FakeERPNextClient(), release)

    assert plan["summary"] == {"create": 1, "update": 1, "unchanged": 1, "conflict": 1, "extra": 1}
    assert plan["extra_item_codes"] == ["ITEM-EXTRA"]
    assert plan["conflicts"][0]["item_code"] == "ITEM-CONFLICT"


def test_apply_journal_replay_is_attributed_to_the_same_employee(tmp_path) -> None:
    request_id = str(uuid4())
    release = {"release_hash": "a" * 64}
    result = {
        "request_id": request_id,
        "release_hash": release["release_hash"],
        "employee": EMPLOYEE,
    }
    journal_path = tmp_path / "sync-journal.json"
    journal_path.write_text(json.dumps({
        "schema_version": 1,
        "requests": {
            request_id: {
                "release_hash": release["release_hash"],
                "employee": EMPLOYEE,
                "status": "verified",
                "result": result,
            }
        },
    }), encoding="utf-8")

    assert apply_release(
        object(),
        release,
        request_id=request_id,
        journal_path=journal_path,
        employee=EMPLOYEE,
    ) == result

    with pytest.raises(SyncError, match="different employee"):
        apply_release(
            object(),
            release,
            request_id=request_id,
            journal_path=journal_path,
            employee={**EMPLOYEE, "user_email": "other@stec-up.local"},
        )
