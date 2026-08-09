from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def run_installer(root: Path, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/dev/install_project_skill.py", *args],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_skill_installs_to_isolated_codex_home(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    isolated_home = tmp_path / "codex-home"
    env = os.environ.copy()
    env["CODEX_HOME"] = str(isolated_home)
    result = run_installer(root, "--install", env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    destination = isolated_home / "skills" / "nexterp-project-maintainer"
    assert (destination / "SKILL.md").exists()
    assert (destination / "agents" / "openai.yaml").exists()
    check = run_installer(root, "--check", env=env)
    assert check.returncode == 0
    assert "status: up_to_date" in check.stdout


def test_skill_does_not_overwrite_local_change_without_force(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    isolated_home = tmp_path / "codex-home"
    env = os.environ.copy()
    env["CODEX_HOME"] = str(isolated_home)
    first = run_installer(root, "--install", env=env)
    assert first.returncode == 0
    destination = isolated_home / "skills" / "nexterp-project-maintainer" / "SKILL.md"
    destination.write_text(destination.read_text(encoding="utf-8") + "\nlocal edit\n", encoding="utf-8")
    second = run_installer(root, "--install", env=env)
    assert second.returncode == 2
    assert "local edit" in destination.read_text(encoding="utf-8")
