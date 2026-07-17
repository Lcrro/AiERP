from __future__ import annotations

import argparse
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile


TEST_SITE = "fac.localhost"


def _artifact(bench: Path, value: str) -> Path:
    path = (bench / value).resolve()
    backup_root = (bench / "sites" / TEST_SITE / "private" / "backups").resolve()
    if not path.is_file() or backup_root not in path.parents:
        raise RuntimeError(f"Invalid baseline artifact: {value}")
    return path


def _restore_database(database: Path, site_config: dict[str, object]) -> None:
    db_name = str(site_config.get("db_name") or "")
    db_password = str(site_config.get("db_password") or "")
    if not db_name or not db_password:
        raise RuntimeError("Site database credentials are missing")
    env = os.environ.copy()
    env["MYSQL_PWD"] = db_password
    process = subprocess.Popen(
        ["mariadb", "--user", db_name, db_name],
        stdin=subprocess.PIPE,
        env=env,
    )
    assert process.stdin is not None
    with gzip.open(database, "rb") as source:
        shutil.copyfileobj(source, process.stdin)
    process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("MariaDB restore failed")


def _restore_files(bench: Path, archive: Path, relative_target: str) -> None:
    target = bench / "sites" / TEST_SITE / relative_target
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as bundle:
        bundle.extractall(bench / "sites", filter="data")


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore the local civil ERPNext golden baseline")
    parser.add_argument("--bench", required=True)
    parser.add_argument("--site", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--public-files", required=True)
    parser.add_argument("--private-files", required=True)
    args = parser.parse_args()

    if args.site != TEST_SITE:
        raise RuntimeError(f"Refusing to restore non-test site: {args.site}")
    bench = Path(args.bench).resolve()
    site_config_path = bench / "sites" / args.site / "site_config.json"
    site_config = json.loads(site_config_path.read_text(encoding="utf-8"))
    database = _artifact(bench, args.database)
    public_files = _artifact(bench, args.public_files)
    private_files = _artifact(bench, args.private_files)

    _restore_database(database, site_config)
    _restore_files(bench, public_files, "public/files")
    _restore_files(bench, private_files, "private/files")
    print("Civil ERPNext database and files restored.")


if __name__ == "__main__":
    main()

