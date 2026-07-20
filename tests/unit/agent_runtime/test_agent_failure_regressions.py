from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from nexterp_agent.agent_runtime.capability_registry import CapabilityRegistry
from nexterp_agent.agent_runtime.deepseek_agent_runtime import (
    DeepSeekAgentRuntime,
    _merge_capability_intent,
    validate_agent_action,
)
from nexterp_agent.agent_runtime.session import RuntimeSessionStore


CASES_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "agent_runtime_failure_cases.json"
CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]


class SequencePlanner:
    def __init__(self, actions: list[dict]) -> None:
        self.actions = deepcopy(actions)

    def __call__(self, _messages):
        return self.actions.pop(0)


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_historical_agent_failure(case: dict, tmp_path: Path) -> None:
    kind = case["kind"]
    if kind == "action_validation":
        with pytest.raises(ValueError) as exc:
            validate_agent_action(deepcopy(case["payload"]))
        assert case["error_contains"] in str(exc.value)
        return

    if kind == "capability_validation":
        with pytest.raises(ValueError) as exc:
            CapabilityRegistry().validate_intent(case["capability_id"], case["intent"])
        assert case["error_contains"] in str(exc.value)
        return

    if kind == "intent_merge":
        assert _merge_capability_intent(case["previous"], case["update"]) == case["expected"]
        return

    if kind == "runtime_sequence":
        runtime = DeepSeekAgentRuntime(
            planner=SequencePlanner(case["actions"]),
            session_store=RuntimeSessionStore(tmp_path / case["id"]),
            max_steps=max(5, len(case["actions"]) + 1),
        )
        result = runtime.run_once(case["text"], user=case["user"])
        assert result.status == case["expected_status"]
        assert any(step["action"] == case["expected_step_action"] for step in result.steps)
        if "expected_tool_result_count" in case:
            assert len(result.tool_results) == case["expected_tool_result_count"]
        if case.get("message_contains"):
            assert case["message_contains"] in result.message
        return

    raise AssertionError(f"Unknown regression case kind: {kind}")
