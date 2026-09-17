"""Cross-platform lifecycle manager for Nexterp's two material test Sites.

The managed Sites are deliberately fixed and local.  This script never targets
an arbitrary ERPNext URL and keeps generated credentials under ``.secrets``.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
from typing import Sequence


ROOT = Path(__file__).resolve().parents[2]
ERPNEXT_VERSION = "v15.118.2"
FRAPPE_DOCKER_COMMIT = "e33f185a0cb14980f1fb8a24989df18f0a41d86b"


@dataclass(frozen=True)
class SiteConfig:
    key: str
    site_name: str
    project_name: str
    http_port: int
    runtime_root: Path
    secret_root: Path
    frappe_docker_root: Path
    supports_baseline: bool = False

    @property
    def secret_json_path(self) -> Path:
        return self.secret_root / "site-secrets.json"

    @property
    def stack_env_path(self) -> Path:
        return self.secret_root / "stack.env"

    @property
    def baseline_root(self) -> Path:
        return self.secret_root / "blank-baseline"


def get_site_config(key: str, *, root: Path = ROOT) -> SiteConfig:
    shared_frappe = root / ".runtime" / "erpnext-material-test" / "frappe_docker"
    configs = {
        "material-test": SiteConfig(
            key="material-test",
            site_name="material-test.localhost",
            project_name="nexterp-material-test",
            http_port=8003,
            runtime_root=root / ".runtime" / "erpnext-material-test",
            secret_root=root / ".secrets" / "erpnext-material-test",
            frappe_docker_root=shared_frappe,
            supports_baseline=True,
        ),
        "classification-v4": SiteConfig(
            key="classification-v4",
            site_name="material-classification-v4.localhost",
            project_name="nexterp-material-classification-v4",
            http_port=8004,
            runtime_root=root / ".runtime" / "erpnext-material-classification-v4",
            secret_root=root / ".secrets" / "erpnext-material-classification-v4",
            frappe_docker_root=shared_frappe,
        ),
    }
    try:
        return configs[key]
    except KeyError as exc:  # pragma: no cover - argparse prevents this
        raise ValueError(f"unsupported material Site: {key}") from exc


def run(
    command: Sequence[str],
    *,
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(part) for part in command],
        cwd=ROOT,
        check=check,
        capture_output=capture_output,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def assert_command(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"missing required command: {name}")


def ensure_docker_ready() -> None:
    assert_command("docker")
    result = run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Docker Engine is not ready. Start Docker and retry.")


def ensure_frappe_docker(config: SiteConfig) -> None:
    git_dir = config.frappe_docker_root / ".git"
    if not git_dir.is_dir():
        if config.key != "material-test":
            raise RuntimeError(
                "shared frappe_docker checkout is missing; bootstrap material-test first"
            )
        config.runtime_root.mkdir(parents=True, exist_ok=True)
        run([
            "git", "clone", "--no-checkout",
            "https://github.com/frappe/frappe_docker.git",
            str(config.frappe_docker_root),
        ])
        run([
            "git", "-C", str(config.frappe_docker_root), "fetch", "--depth", "1",
            "origin", FRAPPE_DOCKER_COMMIT,
        ])
        run([
            "git", "-C", str(config.frappe_docker_root), "checkout", "--detach",
            FRAPPE_DOCKER_COMMIT,
        ])
    actual = run(
        ["git", "-C", str(config.frappe_docker_root), "rev-parse", "HEAD"],
        capture_output=True,
    ).stdout.strip()
    if actual != FRAPPE_DOCKER_COMMIT:
        raise RuntimeError(
            f"frappe_docker commit mismatch: expected {FRAPPE_DOCKER_COMMIT}, got {actual}"
        )


def _secure_file(path: Path) -> None:
    if os.name != "nt":
        path.chmod(0o600)


def ensure_secrets(config: SiteConfig) -> dict[str, str]:
    config.secret_root.mkdir(parents=True, exist_ok=True)
    if not config.secret_json_path.is_file():
        payload = {
            "site": config.site_name,
            "db_root_password": secrets.token_urlsafe(32),
            "admin_password": secrets.token_urlsafe(32),
        }
        config.secret_json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        _secure_file(config.secret_json_path)
    payload = json.loads(config.secret_json_path.read_text(encoding="utf-8-sig"))
    if payload.get("site") != config.site_name:
        raise RuntimeError(f"secret file belongs to another Site: {config.secret_json_path}")
    if not payload.get("db_root_password") or not payload.get("admin_password"):
        raise RuntimeError(f"secret file is incomplete: {config.secret_json_path}")
    config.stack_env_path.write_text(
        "\n".join([
            f"ERPNEXT_VERSION={ERPNEXT_VERSION}",
            f"DB_PASSWORD={payload['db_root_password']}",
            f"HTTP_PUBLISH_PORT={config.http_port}",
            f"FRAPPE_SITE_NAME_HEADER={config.site_name}",
            "PULL_POLICY=missing",
            "RESTART_POLICY=unless-stopped",
            "",
        ]),
        encoding="utf-8",
    )
    _secure_file(config.stack_env_path)
    return payload


def compose_prefix(config: SiteConfig) -> list[str]:
    root = config.frappe_docker_root
    return [
        "docker", "compose",
        "--project-name", config.project_name,
        "--env-file", str(config.stack_env_path),
        "-f", str(root / "compose.yaml"),
        "-f", str(root / "overrides" / "compose.mariadb.yaml"),
        "-f", str(root / "overrides" / "compose.redis.yaml"),
        "-f", str(root / "overrides" / "compose.noproxy.yaml"),
    ]


def compose(
    config: SiteConfig,
    arguments: Sequence[str],
    *,
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return run(
        [*compose_prefix(config), *arguments],
        check=check,
        capture_output=capture_output,
    )


def wait_backend(config: SiteConfig, *, timeout_seconds: int = 120) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = compose(
            config,
            ["ps", "--status", "running", "-q", "backend"],
            check=False,
            capture_output=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return
        time.sleep(2)
    raise RuntimeError(f"ERPNext backend did not become ready within {timeout_seconds} seconds")


def site_exists(config: SiteConfig) -> bool:
    result = compose(
        config,
        ["exec", "-T", "backend", "bash", "-lc",
         f"test -f sites/{config.site_name}/site_config.json"],
        check=False,
    )
    return result.returncode == 0


def bootstrap_site(config: SiteConfig, credentials: dict[str, str]) -> None:
    if site_exists(config):
        return
    compose(config, [
        "exec", "-T",
        "-e", f"SITE_ADMIN_PASSWORD={credentials['admin_password']}",
        "-e", f"DB_ROOT_PASSWORD={credentials['db_root_password']}",
        "backend", "bash", "-lc",
        "bench new-site --mariadb-user-host-login-scope=\"%\" "
        "--db-root-username=root --db-root-password=\"$DB_ROOT_PASSWORD\" "
        "--admin-password=\"$SITE_ADMIN_PASSWORD\" --install-app erpnext "
        f"{config.site_name}",
    ])


def create_baseline(config: SiteConfig, *, force: bool) -> None:
    if not config.supports_baseline:
        raise RuntimeError(f"baseline is not supported for {config.key}")
    if not site_exists(config):
        raise RuntimeError(f"Site {config.site_name} does not exist; run bootstrap first")
    if config.baseline_root.exists():
        if not force:
            raise RuntimeError("blank baseline already exists; use --force to replace it")
        resolved = config.baseline_root.resolve()
        if config.secret_root.resolve() not in resolved.parents:
            raise RuntimeError("refusing to remove a baseline outside the secret root")
        shutil.rmtree(resolved)
    compose(config, [
        "exec", "-T", "backend", "bench", "--site", config.site_name,
        "backup", "--with-files", "--compress",
    ])
    config.baseline_root.mkdir(parents=True, exist_ok=True)
    compose(config, [
        "cp",
        f"backend:/home/frappe/frappe-bench/sites/{config.site_name}/private/backups/.",
        str(config.baseline_root),
    ])


def execute(*, site: str, action: str, force: bool = False) -> None:
    config = get_site_config(site)
    ensure_docker_ready()
    ensure_frappe_docker(config)
    credentials = ensure_secrets(config)
    if action == "stop":
        compose(config, ["down"])
        print(f"Stopped {config.project_name}; persistent volumes were preserved.")
        return
    if action == "status":
        compose(config, ["ps"])
        return
    compose(config, ["up", "-d"])
    wait_backend(config)
    if action == "start":
        print(f"Started {config.project_name} at http://localhost:{config.http_port}")
        return
    if action == "bootstrap":
        bootstrap_site(config, credentials)
        compose(config, ["exec", "-T", "backend", "bench", "--site", config.site_name, "list-apps"])
        print(f"ERPNext Site is ready at http://localhost:{config.http_port}")
        print(f"Credentials remain local under {config.secret_root.relative_to(ROOT)}.")
        return
    if action == "baseline":
        create_baseline(config, force=force)
        print(f"Blank baseline saved under {config.baseline_root.relative_to(ROOT)}.")
        return
    raise ValueError(f"unsupported action: {action}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage fixed Nexterp material ERPNext test Sites")
    parser.add_argument("--site", choices=("material-test", "classification-v4"), required=True)
    parser.add_argument("--action", choices=("bootstrap", "start", "stop", "status", "baseline"), default="status")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        execute(site=args.site, action=args.action, force=args.force)
    except (RuntimeError, subprocess.CalledProcessError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
