"""Install the repository-maintenance Skill without overwriting local edits."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "skills" / "nexterp-project-maintainer"


def files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and "__pycache__" not in path.parts)


def digest(root: Path) -> str:
    hasher = hashlib.sha256()
    for path in files(root):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        hasher.update(relative)
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def destination() -> Path:
    configured = os.environ.get("CODEX_HOME")
    base = Path(configured).expanduser() if configured else Path.home() / ".codex"
    return base / "skills" / SOURCE.name


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare source and installed Skill")
    parser.add_argument("--install", action="store_true", help="install or update Skill")
    parser.add_argument("--force", action="store_true", help="overwrite a different installed Skill")
    args = parser.parse_args()
    if not SOURCE.exists():
        parser.error(f"source Skill does not exist: {SOURCE}")
    target = destination()
    source_hash = digest(SOURCE)
    target_hash = digest(target) if target.exists() else None
    if args.check or not args.install:
        print(f"source: {SOURCE}")
        print(f"target: {target}")
        print(f"source_hash: {source_hash}")
        print(f"target_hash: {target_hash or '<not installed>'}")
        print("status: up_to_date" if source_hash == target_hash else "status: update_available")
        if not args.install:
            return 0
    if target.exists() and target_hash != source_hash and not args.force:
        print("Refusing to overwrite a different installed Skill; use --force after reviewing local edits.")
        return 2
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(SOURCE, target)
    print(f"Installed {SOURCE.name} to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
