"""Cross-platform bootstrap and verification for a Nexterp team handoff."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid


ROOT = Path(__file__).resolve().parents[2]
CONFIRMATION_TEXT = "BOOTSTRAP-NEXTERP-TEST-SANDBOX"


def venv_python_path(root: Path = ROOT, *, os_name: str = os.name) -> Path:
    return root / ".venv" / ("Scripts/python.exe" if os_name == "nt" else "bin/python")


def run(
    command: list[str | Path],
    *,
    python: Path | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    rendered = [str(part) for part in command]
    if python is not None:
        rendered.insert(0, str(python))
    return subprocess.run(
        rendered,
        cwd=ROOT,
        check=True,
        capture_output=capture_output,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def run_json(script_and_args: list[str | Path], *, python: Path) -> dict:
    output = run(script_and_args, python=python, capture_output=True).stdout
    try:
        result = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"command did not return JSON: {' '.join(map(str, script_and_args))}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("JSON command returned a non-object payload")
    return result


def assert_command(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"missing required command: {name}")


def doctor(*, workbook: Path | None = None) -> dict:
    for name in ("git", "docker"):
        assert_command(name)
    docker_version = run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        capture_output=True,
    ).stdout.strip()
    return {
        "repository": str(ROOT),
        "git": run(["git", "rev-parse", "--short", "HEAD"], capture_output=True).stdout.strip(),
        "python": run([sys.executable, "--version"], capture_output=True).stdout.strip(),
        "docker": docker_version,
        "platform": sys.platform,
        "venv_exists": venv_python_path().is_file(),
        "env_exists": (ROOT / ".env").is_file(),
        "v4_workbook": bool(workbook and workbook.is_file()),
    }


def ensure_python_environment() -> Path:
    python = venv_python_path()
    if not python.is_file():
        run([sys.executable, "-m", "venv", ROOT / ".venv"])
    run([python, "-m", "pip", "install", "-e", ".[dev]"])
    env_file = ROOT / ".env"
    if not env_file.is_file():
        shutil.copyfile(ROOT / ".env.example", env_file)
        print("Created .env from .env.example; populate only locally required values.")
    return python


def require_workbook(path: Path | None) -> Path:
    if path is None or not path.is_file():
        raise RuntimeError("--v4-workbook must point to the securely transferred V4 workbook")
    return path.resolve()


def bootstrap(*, workbook: Path | None, confirmation: str) -> None:
    if confirmation != CONFIRMATION_TEXT:
        raise RuntimeError(f"re-run with --confirm {CONFIRMATION_TEXT}")
    source = require_workbook(workbook)
    doctor(workbook=source)
    python = ensure_python_environment()
    site_manager = ROOT / "scripts" / "test_env" / "material_sites.py"
    run([site_manager, "--site", "material-test", "--action", "bootstrap"], python=python)
    run([ROOT / "scripts/material_master/sync_reference_catalog_database.py", "--version", "2026-05"], python=python)
    gpc = ROOT / "scripts/erpnext/sync_gpc_materials_to_test_site.py"
    run([gpc, "initialize"], python=python)
    gpc_plan = run_json([gpc, "plan"], python=python)
    run([
        gpc, "apply", "--request-id", str(uuid.uuid4()),
        "--confirm-release-hash", str(gpc_plan["release_hash"]),
    ], python=python)
    run([gpc, "verify"], python=python)

    business = ROOT / "scripts/erpnext/bootstrap_material_test_business.py"
    business_plan = run_json([business, "plan"], python=python)
    run([
        business, "apply", "--request-id", str(uuid.uuid4()),
        "--confirm-plan-hash", str(business_plan["plan_hash"]),
    ], python=python)
    run([business, "verify"], python=python)

    run([site_manager, "--site", "classification-v4", "--action", "bootstrap"], python=python)
    importer = ROOT / "scripts/erpnext/import_classification_v4_workbook.py"
    v4_plan = run_json([importer, "plan", "--input", source], python=python)
    run([
        importer, "apply", "--input", source,
        "--request-id", str(uuid.uuid4()),
        "--confirm-release-hash", str(v4_plan["release_hash"]),
    ], python=python)
    run([importer, "verify", "--input", source], python=python)
    run([ROOT / "scripts/erpnext/bootstrap_classification_v4_business.py"], python=python)
    print("Bootstrap completed. Start the portal with:")
    print(f"{python} scripts/dev/agent_workbench.py --port 8788 --profile material_test")


def verify(*, workbook: Path | None) -> None:
    source = require_workbook(workbook)
    doctor(workbook=source)
    python = venv_python_path()
    if not python.is_file():
        raise RuntimeError("Python environment is missing; run bootstrap first")
    commands = [
        [ROOT / "scripts/erpnext/sync_gpc_materials_to_test_site.py", "verify"],
        [ROOT / "scripts/erpnext/bootstrap_material_test_business.py", "verify"],
        [ROOT / "scripts/erpnext/import_classification_v4_workbook.py", "verify", "--input", source],
        [ROOT / "scripts/dev/project_context.py", "snapshot"],
        [ROOT / "scripts/dev/project_context.py", "audit-docs"],
        [ROOT / "scripts/dev/project_context.py", "check"],
    ]
    for command in commands:
        run(command, python=python)
    print("Both material test Sites and repository context passed verification.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare or verify a Nexterp development machine")
    parser.add_argument("action", choices=("doctor", "bootstrap", "verify"), nargs="?", default="doctor")
    parser.add_argument("--v4-workbook", type=Path)
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    try:
        if args.action == "doctor":
            print(json.dumps(doctor(workbook=args.v4_workbook), ensure_ascii=False, indent=2))
        elif args.action == "bootstrap":
            bootstrap(workbook=args.v4_workbook, confirmation=args.confirm)
        else:
            verify(workbook=args.v4_workbook)
    except (RuntimeError, subprocess.CalledProcessError, OSError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
