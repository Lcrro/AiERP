from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "scenarios" / "run_civil_agent_day.py"
SPEC = importlib.util.spec_from_file_location("civil_agent_day", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_day_runner_defines_full_chronological_event_set() -> None:
    events = MODULE.build_events()

    assert len(events) == 17
    assert events[0].time == "08:00"
    assert events[-1].time == "18:00"
    assert [event.time for event in events] == sorted(event.time for event in events)


def test_day_runner_propagates_document_numbers_between_roles() -> None:
    state = {"Material Request": ["MAT-MR-TEST"], "Purchase Order": ["PUR-ORD-TEST"]}
    events = {event.time: event for event in MODULE.build_events()}

    assert "MAT-MR-TEST" in events["10:00"].commands(state)[0]
    assert all("PUR-ORD-TEST" in command for command in events["13:30"].commands(state)[:2])
