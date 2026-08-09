from __future__ import annotations

import json
import copy
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.dev import project_context


def test_project_context_config_and_resume_are_compact() -> None:
    config = project_context.load_config()
    summary = project_context.resume_text(config)
    assert config["current_milestone"]["id"] == "project-maintenance-skill-v0.1"
    assert len(summary.encode("utf-8")) <= 8192
    assert ".env" not in summary
    assert "api_secret" not in summary.lower()


def test_config_validation_rejects_missing_module_path() -> None:
    config = copy.deepcopy(project_context.load_config())
    config["module_paths"]["item_master"] = ["does/not/exist"]
    with pytest.raises(ValueError, match="missing paths"):
        project_context.validate_config(config)


def test_snapshot_is_stable_for_same_git_state() -> None:
    config = project_context.load_config()
    first, first_map = project_context.snapshot(config)
    second, second_map = project_context.snapshot(config)
    assert first == second
    assert first_map == second_map
    assert first["sensitive_files_in_context"] == []


def test_document_audit_has_no_broken_links() -> None:
    result = project_context.doc_audit(project_context.load_config())
    assert result["markdown_count"] > 0
    assert result["broken_links"] == []


def test_cli_check_succeeds_after_generated_context_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [sys.executable, "scripts/dev/project_context.py", "snapshot"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [sys.executable, "scripts/dev/project_context.py", "audit-docs"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [sys.executable, "scripts/dev/project_context.py", "check"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["ok"] is True
