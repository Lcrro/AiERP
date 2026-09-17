from __future__ import annotations

import json
from pathlib import Path

from scripts.dev.team_handoff_bootstrap import venv_python_path
from scripts.test_env.material_sites import compose_prefix, ensure_secrets, get_site_config


def test_virtual_environment_python_path_is_platform_specific(tmp_path: Path) -> None:
    assert venv_python_path(tmp_path, os_name="nt") == tmp_path / ".venv" / "Scripts/python.exe"
    assert venv_python_path(tmp_path, os_name="posix") == tmp_path / ".venv" / "bin/python"


def test_material_site_paths_and_compose_arguments_are_platform_neutral(tmp_path: Path) -> None:
    config = get_site_config("material-test", root=tmp_path)
    prefix = compose_prefix(config)

    assert config.site_name == "material-test.localhost"
    assert config.http_port == 8003
    assert prefix[:2] == ["docker", "compose"]
    assert "--env-file" in prefix
    env_index = prefix.index("--env-file") + 1
    assert Path(prefix[env_index]) == config.stack_env_path
    assert Path(prefix[-1]) == config.frappe_docker_root / "overrides" / "compose.noproxy.yaml"


def test_generated_site_secrets_stay_below_ignored_secret_root(tmp_path: Path) -> None:
    config = get_site_config("classification-v4", root=tmp_path)
    payload = ensure_secrets(config)

    assert payload["site"] == "material-classification-v4.localhost"
    assert len(payload["admin_password"]) >= 32
    assert config.secret_json_path.is_file()
    assert config.stack_env_path.is_file()
    assert json.loads(config.secret_json_path.read_text(encoding="utf-8"))["site"] == payload["site"]
    assert str(config.secret_root).startswith(str(tmp_path / ".secrets"))
