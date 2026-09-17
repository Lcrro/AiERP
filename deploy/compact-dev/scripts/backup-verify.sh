#!/bin/bash
# Re-verify backup manifest files exist, non-empty, and match SHA256.
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/_common.sh"
load_backup_root

python3 - "$BACKUP_ROOT" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
manifest_path = root / "BACKUP_MANIFEST.json"
if not manifest_path.is_file():
    print(f"FAIL missing manifest: {manifest_path}")
    sys.exit(1)
manifest = json.loads(manifest_path.read_text())
ok = True
required_kinds = {"mysql_dump", "site_files", "site_config"}
seen = set()
for f in manifest.get("files", []):
    p = root / f["path"]
    kind = f.get("kind")
    if kind:
        seen.add(kind)
    if not p.is_file():
        print(f"MISSING {f['path']}")
        ok = False
        continue
    size = p.stat().st_size
    if size == 0:
        print(f"EMPTY {f['path']}")
        ok = False
        continue
    if size != f.get("bytes"):
        print(f"SIZE_MISMATCH {f['path']} actual={size} expected={f.get('bytes')}")
        ok = False
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    if digest != f.get("sha256"):
        print(f"HASH_MISMATCH {f['path']}")
        ok = False
missing_kinds = required_kinds - seen
if missing_kinds:
    print(f"MISSING_KINDS {sorted(missing_kinds)}")
    ok = False
baseline = root / "baseline" / "BASELINE.json"
if baseline.is_file():
    b = json.loads(baseline.read_text())
    sites = b.get("sites", {})
    print("BASELINE items:",
          {k: v.get("items") for k, v in sites.items()})
print("backup_root", root)
print("files_checked", len(manifest.get("files", [])))
print("backup_ok", "YES" if ok else "NO")
sys.exit(0 if ok else 1)
PY
