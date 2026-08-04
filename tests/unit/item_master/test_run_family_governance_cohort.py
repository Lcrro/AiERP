from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "material_master" / "run_family_governance_cohort.py"
SPEC = importlib.util.spec_from_file_location("run_family_governance_cohort", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_build_command_keeps_each_family_isolated() -> None:
    command = MODULE.build_command(
        {"top_group": "管材管件阀门", "material_family": "弯头"},
        chunk_size=20,
        row_concurrency=2,
        reuse=True,
        reuse_review=False,
    )

    assert "--top-group" in command
    assert "管材管件阀门" in command
    assert "--material-family" in command
    assert "弯头" in command
    assert "--reuse-guide" in command
    assert "--reuse-responses" in command
    assert "--reuse-review" not in command


def test_default_cohort_is_absolute() -> None:
    assert MODULE.DEFAULT_COHORT.is_absolute()
