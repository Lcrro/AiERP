#!/usr/bin/env python3
"""Translate GPC Attribute and Attribute Value names into Chinese work labels."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from import_gpc_reference import translate_with_deepseek, write_jsonl  # noqa: E402


RUNTIME_ROOT = ROOT / ".runtime" / "gpc-reference"
VERSION_RE = re.compile(r"^\d{4}-\d{2}$")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _source_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def extract_profile_terms(profiles: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return one stable row per official Attribute/Attribute Value code."""

    terms: dict[str, dict[str, Any]] = {}
    contexts: dict[str, set[str]] = {}
    for profile in profiles:
        brick_name = _text(profile.get("official_name"))
        for attribute in profile.get("attributes") or []:
            attribute_code = _text(attribute.get("code"))
            attribute_name = _text(attribute.get("name"))
            if attribute_code and attribute_name:
                existing = terms.get(attribute_code)
                if existing and existing["official_name"] != attribute_name:
                    raise ValueError(f"GPC 属性编码名称冲突：{attribute_code}")
                terms[attribute_code] = {"code": attribute_code, "official_name": attribute_name, "kind": "attribute"}
                if brick_name:
                    contexts.setdefault(attribute_code, set()).add(brick_name)
            for value in attribute.get("values") or []:
                value_code = _text(value.get("code"))
                value_name = _text(value.get("name"))
                if not value_code or not value_name:
                    continue
                existing = terms.get(value_code)
                if existing and existing["official_name"] != value_name:
                    raise ValueError(f"GPC 属性值编码名称冲突：{value_code}")
                terms[value_code] = {"code": value_code, "official_name": value_name, "kind": "attribute_value"}
                if attribute_name:
                    contexts.setdefault(value_code, set()).add(attribute_name)
    rows = []
    for code in sorted(terms):
        row = dict(terms[code])
        row["context"] = " | ".join(sorted(contexts.get(code, ()))[:4])
        rows.append(row)
    return rows


def placeholder(term: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": term["code"],
        "kind": term["kind"],
        "official_name": term["official_name"],
        "working_name": "",
        "status": "missing",
        "model": "",
        "source_hash": _source_hash(term["official_name"]),
    }


def translate_profile_terms(version: str, *, batch_size: int = 1500, min_batch_size: int = 125) -> dict[str, Any]:
    if not VERSION_RE.fullmatch(version):
        raise ValueError("GPC 版本必须是 YYYY-MM")
    version_root = (RUNTIME_ROOT / version).resolve()
    if version_root.parent != RUNTIME_ROOT.resolve():
        raise ValueError("GPC 运行期路径越界")
    profiles_path = version_root / "brick-profiles.jsonl"
    manifest_path = version_root / "manifest.json"
    audit_path = version_root / "audit.json"
    output_path = version_root / "profile-translations.zh-CN.jsonl"
    if not profiles_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(f"GPC {version} 尚未导入")

    terms = extract_profile_terms(load_jsonl(profiles_path))
    term_by_code = {term["code"]: term for term in terms}
    translations = {term["code"]: placeholder(term) for term in terms}
    if output_path.is_file():
        for row in load_jsonl(output_path):
            code = _text(row.get("code"))
            term = term_by_code.get(code)
            if term and row.get("source_hash") == _source_hash(term["official_name"]) and _text(row.get("working_name")):
                translations[code] = row

    request_count = 0
    failed_batches = 0
    current_batch_size = max(1, int(batch_size))
    min_size = max(1, int(min_batch_size))
    model = ""
    pass_summaries: list[dict[str, Any]] = []
    while True:
        missing = [term for term in terms if translations[term["code"]].get("status") != "machine"]
        if not missing:
            break
        translated_this_pass = 0
        pass_failures = 0
        for start in range(0, len(missing), current_batch_size):
            batch = missing[start : start + current_batch_size]
            translated, metadata = translate_with_deepseek(batch, batch_size=len(batch))
            request_count += int(metadata.get("request_count") or 0)
            failed_batches += int(metadata.get("failed_batches") or 0)
            pass_failures += int(metadata.get("failed_batches") or 0)
            model = _text(metadata.get("model")) or model
            for row in translated:
                code = _text(row.get("code"))
                term = term_by_code.get(code)
                if not term or row.get("status") != "machine" or not _text(row.get("working_name")):
                    continue
                translations[code] = {**row, "kind": term["kind"], "official_name": term["official_name"]}
                translated_this_pass += 1
            write_jsonl(output_path, (translations[term["code"]] for term in terms))
        pass_summaries.append({
            "batch_size": current_batch_size,
            "input_items": len(missing),
            "translated_items": translated_this_pass,
            "failed_batches": pass_failures,
        })
        remaining = sum(1 for row in translations.values() if row.get("status") != "machine")
        if not remaining or current_batch_size <= min_size:
            break
        current_batch_size = max(min_size, current_batch_size // 2)

    rows = [translations[term["code"]] for term in terms]
    translated_count = sum(1 for row in rows if row.get("status") == "machine" and _text(row.get("working_name")))
    metadata = {
        "language": "zh-CN",
        "status": "complete" if translated_count == len(terms) else "partial",
        "model": model,
        "request_count": request_count,
        "failed_batches": failed_batches,
        "input_items": len(terms),
        "translated_items": translated_count,
        "missing_items": len(terms) - translated_count,
        "attribute_items": sum(1 for term in terms if term["kind"] == "attribute"),
        "attribute_value_items": sum(1 for term in terms if term["kind"] == "attribute_value"),
        "passes": pass_summaries,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["profile_translation"] = metadata
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if audit_path.is_file():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        audit["profile_translation_missing_count"] = metadata["missing_items"]
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"root": str(version_root), "output": str(output_path), "profile_translation": metadata}


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate GPC Attribute and Attribute Value names")
    parser.add_argument("--version", default="2026-05")
    parser.add_argument("--batch-size", type=int, default=1500)
    parser.add_argument("--min-batch-size", type=int, default=125)
    args = parser.parse_args()
    try:
        result = translate_profile_terms(args.version, batch_size=args.batch_size, min_batch_size=args.min_batch_size)
    except Exception as exc:
        print(f"GPC 属性术语翻译失败：{exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["profile_translation"]["missing_items"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
