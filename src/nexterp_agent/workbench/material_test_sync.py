"""Gated workbench access to the fixed material-test catalog sync command."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
import threading
from typing import Any, Callable
from uuid import UUID, uuid4


ROOT = Path(__file__).resolve().parents[3]
SYNC_SCRIPT = ROOT / "scripts" / "erpnext" / "sync_gpc_materials_to_test_site.py"
_RELEASE_HASH = re.compile(r"^[0-9a-f]{64}$")


def _validate_tokens(release_hash: str, request_id: str) -> None:
    if not _RELEASE_HASH.fullmatch(release_hash):
        raise ValueError("release_hash 格式无效")
    try:
        UUID(request_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("request_id 格式无效") from exc


def _run_sync_command(action: str, *, request_id: str, release_hash: str = "") -> dict[str, Any]:
    """Run only the allow-listed fixed-site script actions and arguments."""

    if action not in {"plan", "apply"}:
        raise ValueError("不支持的同步动作")
    command = [sys.executable, str(SYNC_SCRIPT), action, "--request-id", request_id]
    if action == "apply":
        _validate_tokens(release_hash, request_id)
        command.extend(["--confirm-release-hash", release_hash])
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    # The existing command uses exit 2 to report a valid read-only plan that
    # contains conflicts.  The workbench must still display that diff, while
    # the gate below prevents it from reaching apply.
    if completed.returncode and not (action == "plan" and completed.returncode == 2):
        message = completed.stderr.strip() or completed.stdout.strip() or "ERPNext 同步命令失败"
        raise RuntimeError(message)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("ERPNext 同步命令未返回有效 JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("ERPNext 同步命令返回格式无效")
    return payload


def run_material_test_plan(request_id: str) -> dict[str, Any]:
    return _run_sync_command("plan", request_id=request_id)


def run_material_test_apply(request_id: str, release_hash: str) -> dict[str, Any]:
    return _run_sync_command("apply", request_id=request_id, release_hash=release_hash)


@dataclass
class _FrozenPlan:
    request_id: str
    release_hash: str
    payload: dict[str, Any]
    status: str = "pending"
    result: dict[str, Any] | None = None


class MaterialTestSyncGate:
    """Bind apply to the exact release hash and request ID returned by plan."""

    def __init__(
        self,
        *,
        plan_runner: Callable[[str], dict[str, Any]] = run_material_test_plan,
        apply_runner: Callable[[str, str], dict[str, Any]] = run_material_test_apply,
    ) -> None:
        self._plan_runner = plan_runner
        self._apply_runner = apply_runner
        self._lock = threading.Lock()
        self._plans: dict[str, _FrozenPlan] = {}

    def plan(self) -> dict[str, Any]:
        request_id = str(uuid4())
        payload = dict(self._plan_runner(request_id))
        returned_request_id = str(payload.get("request_id") or "")
        release_hash = str(payload.get("release_hash") or "")
        _validate_tokens(release_hash, returned_request_id)
        if returned_request_id != request_id:
            raise RuntimeError("同步计划返回了不一致的 request_id")
        plan = payload.get("plan")
        if not isinstance(plan, dict) or not isinstance(plan.get("summary"), dict):
            raise RuntimeError("同步计划缺少 release diff summary")
        response = {
            "request_id": request_id,
            "release_hash": release_hash,
            "catalog_revision": payload.get("catalog_revision"),
            "counts": dict(payload.get("counts") or {}),
            "summary": dict(plan["summary"]),
            "conflicts": list(plan.get("conflicts") or []),
            "extra_item_codes": list(plan.get("extra_item_codes") or []),
            "target_managed_items": int(plan.get("target_managed_items") or 0),
        }
        with self._lock:
            self._plans[request_id] = _FrozenPlan(request_id, release_hash, response)
        return dict(response)

    def apply(self, *, request_id: str, release_hash: str) -> dict[str, Any]:
        _validate_tokens(release_hash, request_id)
        with self._lock:
            frozen = self._plans.get(request_id)
            if frozen is None:
                raise ValueError("未找到该 request_id 的同步计划，请重新执行计划")
            if frozen.release_hash != release_hash:
                raise ValueError("release_hash 与已确认计划不一致，未执行写入")
            if int((frozen.payload.get("summary") or {}).get("conflict") or 0):
                raise ValueError("同步计划包含冲突，未执行写入")
            if frozen.status == "complete" and frozen.result is not None:
                return dict(frozen.result)
            if frozen.status == "applying":
                raise ValueError("该同步计划正在执行")
            frozen.status = "applying"
        try:
            result = dict(self._apply_runner(request_id, release_hash))
            if str(result.get("request_id") or "") != request_id:
                raise RuntimeError("同步结果 request_id 与确认值不一致")
            if str(result.get("release_hash") or "") != release_hash:
                raise RuntimeError("同步结果 release_hash 与确认值不一致")
        except Exception:
            with self._lock:
                frozen.status = "pending"
            raise
        with self._lock:
            frozen.status = "complete"
            frozen.result = result
        return dict(result)
