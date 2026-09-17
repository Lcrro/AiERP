#!/usr/bin/env python3
"""Import the official GS1 GPC reference package into the local runtime.

This command intentionally produces a read-only, internal reference package.
It never writes ERPNext data and never places the source archive in Git.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
from typing import Any, Iterable
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = ROOT / ".runtime" / "gpc-reference"
DEFAULT_URL = "https://ref.gs1.org/standards/gpc/{version}/"
ALLOWED_HOSTS = {"ref.gs1.org", "www.gs1.org", "gs1.org"}
VERSION_RE = re.compile(r"^\d{4}-\d{2}$")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _unwrap_translation_values(payload: Any) -> Any:
    """Normalize common JSON envelopes emitted by long translation calls."""

    if isinstance(payload, str):
        try:
            return _unwrap_translation_values(json.loads(payload))
        except json.JSONDecodeError:
            return {}
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return {}
    for key in ("translations", "translation", "code", "items", "data", "result"):
        if key in payload:
            candidate = _unwrap_translation_values(payload[key])
            if isinstance(candidate, (dict, list)):
                return candidate
    return payload


def _local_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_official_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError("GPC 来源 URL 必须是 GS1 官方 HTTPS 地址")
    return url


def download_package(url: str, *, timeout: int = 120) -> bytes:
    validate_official_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "Nexterp-GPC-Reference-Importer/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
    if not data or not data.startswith(b"PK"):
        raise ValueError("官方 GPC 下载响应不是 ZIP 包")
    return data


def safe_extract(zip_path: Path, destination: Path) -> list[str]:
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    extracted: list[str] = []
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            if not name or name.endswith("/"):
                continue
            # Refuse Unix symlinks as well as textual traversal.  Otherwise a
            # seemingly safe member could redirect the subsequent write.
            unix_mode = (info.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                raise ValueError(f"ZIP 不允许符号链接：{name}")
            candidate = (destination / name).resolve()
            try:
                candidate.relative_to(destination)
            except ValueError as exc:
                raise ValueError(f"ZIP 路径越界：{name}") from exc
            candidate.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, candidate.open("wb") as target:
                shutil.copyfileobj(source, target)
            extracted.append(name)
    return extracted


def _find_package_file(extracted_root: Path, suffix: str, marker: str) -> Path:
    candidates = sorted(
        path for path in extracted_root.rglob(f"*{suffix}") if path.is_file() and marker.casefold() in path.name.casefold()
    )
    if not candidates:
        raise FileNotFoundError(f"GPC 包缺少 {marker} {suffix} 文件")
    return candidates[0]


def parse_gpc_xml(xml_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Counter[str]]:
    """Parse the Combined Published Schema XML into four tree levels/profiles."""

    tree = ET.parse(xml_path)
    root = tree.getroot()
    nodes: list[dict[str, Any]] = []
    profiles: list[dict[str, Any]] = []
    stats: Counter[str] = Counter()
    seen: set[str] = set()
    attribute_codes: set[str] = set()
    attribute_value_codes: set[str] = set()

    def add_node(element: ET.Element, kind: str, level: int, parent_code: str | None) -> str:
        code = _text(element.attrib.get("code"))
        if not code:
            raise ValueError(f"GPC {kind} 缺少编码")
        if code in seen:
            raise ValueError(f"GPC 存在重复编码：{code}")
        seen.add(code)
        official_name = _text(element.attrib.get("text"))
        node = {
            "code": code,
            "official_name": official_name,
            "name": official_name,
            "kind": kind,
            "level": level,
            "parent_code": parent_code,
            "source": "GS1 GPC 2026-05",
        }
        nodes.append(node)
        stats[kind] += 1
        return code

    def children(element: ET.Element, tag: str) -> Iterable[ET.Element]:
        return (child for child in list(element) if _local_name(child.tag) == tag and child.attrib.get("active", "true").lower() == "true")

    for segment in children(root, "segment"):
        segment_code = add_node(segment, "segment", 0, None)
        for family in children(segment, "family"):
            family_code = add_node(family, "family", 1, segment_code)
            for class_element in children(family, "class"):
                class_code = add_node(class_element, "class", 2, family_code)
                for brick in children(class_element, "brick"):
                    brick_code = add_node(brick, "brick", 3, class_code)
                    attributes: list[dict[str, Any]] = []
                    for attribute in children(brick, "attType"):
                        values = []
                        for value in children(attribute, "attValue"):
                            values.append({
                                "code": _text(value.attrib.get("code")),
                                "name": _text(value.attrib.get("text")),
                                "definition": _text(value.attrib.get("definition")),
                            })
                        attributes.append({
                            "code": _text(attribute.attrib.get("code")),
                            "name": _text(attribute.attrib.get("text")),
                            "definition": _text(attribute.attrib.get("definition")),
                            "values": values,
                        })
                        attribute_codes.add(_text(attribute.attrib.get("code")))
                        attribute_value_codes.update(_text(value.get("code")) for value in values if _text(value.get("code")))
                    profiles.append({
                        "code": brick_code,
                        "kind": "brick",
                        "official_name": _text(brick.attrib.get("text")),
                        "definition": _text(brick.attrib.get("definition")),
                        "includes": _text(brick.attrib.get("definition")),
                        "excludes": _text(brick.attrib.get("definitionExcludes")),
                        "attributes": attributes,
                    })
    if not nodes:
        raise ValueError("GPC XML 未发现有效目录节点")
    stats["attribute"] = len(attribute_codes)
    stats["attribute_value"] = len(attribute_value_codes)
    return nodes, profiles, stats


def _excel_unique_counts(xlsx_path: Path) -> dict[str, int]:
    """Read the single-sheet official Excel package with stdlib streaming XML."""

    columns = {
        "SegmentCode": "segment",
        "FamilyCode": "family",
        "ClassCode": "class",
        "BrickCode": "brick",
        "AttributeCode": "attribute",
        "AttributeValueCode": "attribute_value",
    }
    values: dict[str, set[str]] = {name: set() for name in columns.values()}
    with zipfile.ZipFile(xlsx_path) as archive:
        with archive.open("xl/worksheets/sheet1.xml") as handle:
            header: list[str] = []
            for event, element in ET.iterparse(handle, events=("end",)):
                if _local_name(element.tag) != "row":
                    continue
                cells = []
                for cell in list(element):
                    if _local_name(cell.tag) != "c":
                        continue
                    value = next((child.text or "" for child in list(cell) if _local_name(child.tag) == "v"), "")
                    cells.append(value.strip())
                if not header:
                    header = cells
                else:
                    for idx, title in enumerate(header):
                        target = columns.get(title)
                        if target and idx < len(cells) and cells[idx]:
                            values[target].add(cells[idx])
                element.clear()
    return {key: len(value) for key, value in values.items()}


def build_translations(nodes: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create hash-bound translation placeholders.

    The importer deliberately does not make a hidden network call.  When the
    existing DeepSeek batch runner is configured, a later translation batch can
    replace these rows while retaining the source hash and model metadata.
    """

    return [
        {
            "code": node["code"],
            "working_name": "",
            "status": "missing",
            "model": "",
            "source_hash": _sha256_bytes(_text(node.get("official_name")).encode("utf-8")),
        }
        for node in nodes
    ]


def translate_with_deepseek(nodes: Iterable[dict[str, Any]], *, batch_size: int | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Translate names through the existing DeepSeek JSON batch helper.

    Translation is explicitly best-effort: a missing key, timeout, malformed
    response, or individual batch failure leaves that batch in the normal
    ``中文待补`` fallback state and never blocks catalog import.
    """

    rows = list(nodes)
    # A names-only request is intentionally compact enough for the approved
    # one-shot workflow.  Callers can pass a smaller batch size when their
    # selected DeepSeek deployment has a lower context/output limit.
    resolved_batch_size = max(1, int(batch_size or len(rows) or 1))
    translations = {row["code"]: item for row, item in zip(rows, build_translations(rows))}
    metadata: dict[str, Any] = {
        "language": "zh-CN",
        "mode": "deepseek_one_shot" if resolved_batch_size >= len(rows) else "deepseek_batch",
        "status": "pending",
        "model": "",
        "failed_batches": 0,
        "request_count": 0,
        "input_items": len(rows),
    }
    try:
        # The normal workbench loads the project .env before constructing its
        # DeepSeek client.  Keep this standalone importer consistent, while
        # never printing or returning the secret itself.  Environment values
        # already supplied by the caller win over the local file.
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
        from nexterp_agent.agent_runtime.deepseek_material_request import call_deepseek_json, load_deepseek_settings

        settings = load_deepseek_settings()
        metadata["model"] = settings.model
    except Exception as exc:
        metadata.update({"status": "fallback", "error": str(exc)})
        return list(translations.values()), metadata

    for start in range(0, len(rows), resolved_batch_size):
        batch = rows[start : start + resolved_batch_size]
        messages = [
            {"role": "system", "content": "你是GPC术语翻译器。只返回 JSON 对象，键为code，值为简洁、忠实的简体中文工作译名。不得改写编码，不得解释。"},
            {"role": "user", "content": json.dumps({"items": [{"code": row["code"], "english": row["official_name"]} for row in batch]}, ensure_ascii=False)},
        ]
        messages[0]["content"] = (
            "你是 GS1 GPC 术语翻译器。只返回 JSON 对象，键为 code，值为简洁、忠实的简体中文工作译名。"
            "必须原样保留编码，不解释。context 仅用于消歧。统一使用：UNCLASSIFIED=未分类，"
            "UNIDENTIFIED=未识别，NOT APPLICABLE=不适用，OTHER=其他，YES=是，NO=否。"
        )
        messages[1]["content"] = json.dumps(
            {
                "items": [
                    {
                        "code": row["code"],
                        "english": row["official_name"],
                        **({"kind": row["kind"]} if row.get("kind") else {}),
                        **({"context": row["context"]} if row.get("context") else {}),
                    }
                    for row in batch
                ]
            },
            ensure_ascii=False,
        )
        try:
            metadata["request_count"] = int(metadata["request_count"]) + 1
            # GPC name translation does not need chain-of-thought.  Use the
            # V4 long-context budget explicitly and allow the large JSON
            # response enough wall-clock time to finish.
            payload = call_deepseek_json(
                messages,
                settings=settings,
                # A bounded per-batch budget avoids asking the service to
                # reserve the full 384K output window for a small response.
                # GPC names are short; 64 tokens per item leaves ample room
                # for JSON punctuation and occasional longer names.
                max_tokens=min(384_000, max(8_192, len(batch) * 64)),
                thinking={"type": "disabled"},
                timeout_seconds=max(int(getattr(settings, "timeout_seconds", 120)), 900),
                max_retries=0,
                allow_json_array=True,
            )
            # DeepSeek may honor the prompt literally and wrap the mapping
            # under ``code`` ("key is code"), or return a JSON string,
            # translations/data envelope, or an item list.  Normalize these
            # shapes without weakening exact code binding below.
            values = _unwrap_translation_values(payload)
            if isinstance(values, list):
                values = {
                    _text(item.get("code")): _text(item.get("working_name") or item.get("name"))
                    for item in values if isinstance(item, dict) and item.get("code")
                }
            if not isinstance(values, dict):
                raise ValueError("翻译响应不是 JSON 对象")
            for row in batch:
                translated = _text(values.get(row["code"]))
                if translated:
                    translations[row["code"]].update({"working_name": translated, "status": "machine", "model": settings.model})
        except Exception as exc:
            metadata["failed_batches"] = int(metadata["failed_batches"]) + 1
            metadata["error_type"] = type(exc).__name__
            metadata["error"] = str(exc)[:240]
    metadata["translated_items"] = sum(1 for row in translations.values() if row.get("status") == "machine")
    metadata["missing_items"] = len(rows) - int(metadata["translated_items"])
    metadata["status"] = "complete" if not metadata["failed_batches"] and not metadata["missing_items"] else "partial"
    return list(translations.values()), metadata


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def import_gpc(
    version: str,
    *,
    source_url: str | None = None,
    translate: bool = False,
    translate_batch_size: int | None = None,
) -> dict[str, Any]:
    if not VERSION_RE.fullmatch(version):
        raise ValueError("GPC 版本必须是 YYYY-MM")
    source_url = source_url or DEFAULT_URL.format(version=version)
    validate_official_url(source_url)
    data = download_package(source_url)
    root = (RUNTIME_ROOT / version).resolve()
    root.parent.mkdir(parents=True, exist_ok=True)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    raw_zip = root / "source-package.zip"
    raw_zip.write_bytes(data)
    package_dir = root / "package"
    safe_extract(raw_zip, package_dir)
    # The package itself carries the release marker.  Do not silently import a
    # different release into a requested version directory.
    if version not in " ".join(path.name for path in package_dir.rglob("*")):
        raise ValueError(f"GPC 官方包未确认版本 {version}")
    xml_path = _find_package_file(package_dir, ".xml", version)
    xlsx_path = _find_package_file(package_dir, ".xlsx", version)
    nodes, profiles, stats = parse_gpc_xml(xml_path)
    translation_meta = {"language": "zh-CN", "mode": "placeholder", "status": "pending", "model": ""}
    translations = build_translations(nodes)
    if translate:
        translations, translation_meta = translate_with_deepseek(nodes, batch_size=translate_batch_size)
    node_count = write_jsonl(root / "nodes.jsonl", nodes)
    profile_count = write_jsonl(root / "brick-profiles.jsonl", profiles)
    translation_count = write_jsonl(root / "translations.zh-CN.jsonl", translations)
    excel_counts = _excel_unique_counts(xlsx_path)
    node_counts = {kind: stats.get(kind, 0) for kind in ("segment", "family", "class", "brick", "attribute", "attribute_value")}
    cross_check = {key: {"xml": node_counts[key], "excel": excel_counts.get(key, 0), "match": node_counts[key] == excel_counts.get(key, 0)} for key in node_counts}
    generated_at = datetime.now(timezone.utc).isoformat()
    audit = {
        "version": version,
        "source_url": source_url,
        "source_sha256": _sha256_bytes(data),
        "generated_at": generated_at,
        "nodes": node_counts,
        "parent_missing_count": 0,
        "duplicate_code_count": 0,
        "orphan_brick_count": 0,
        "cycle_count": 0,
        "excel_cross_check": cross_check,
        "excel_cross_check_passed": all(item["match"] for item in cross_check.values()),
        "translation_fallback_count": sum(1 for row in translations if row.get("status") == "missing"),
    }
    (root / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "catalog": "gpc",
        "version": version,
        "source": "GS1 GPC",
        "source_url": source_url,
        "source_sha256": _sha256_bytes(data),
        "generated_at": generated_at,
        "primary_input": xml_path.name,
        "cross_check_input": xlsx_path.name,
        "nodes": node_count,
        "profiles": profile_count,
        "translations": translation_count,
        "counts": node_counts,
        "levels": ["segment", "family", "class", "brick"],
        "hierarchy_complete": True,
        "parent_missing_count": 0,
        "duplicate_code_count": 0,
        "orphan_brick_count": 0,
        "attribute_count": stats.get("attribute", 0),
        "attribute_value_count": stats.get("attribute_value", 0),
        "translation": translation_meta,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"root": str(root), "manifest": manifest, "audit": audit}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import official GS1 GPC reference data")
    parser.add_argument("--version", required=True, help="Exact GPC release, for example 2026-05")
    parser.add_argument("--source-url", default="", help="Optional GS1 official package URL")
    parser.add_argument("--translate", action="store_true", help="名称-only 一次性调用现有 DeepSeek JSON 接口；失败或截断时回退英文")
    parser.add_argument("--translate-batch-size", type=int, default=0, help="可选的翻译分批大小；默认把所有名称放在一次请求")
    args = parser.parse_args(argv)
    try:
        result = import_gpc(
            args.version,
            source_url=args.source_url or None,
            translate=args.translate,
            translate_batch_size=args.translate_batch_size or None,
        )
    except Exception as exc:  # CLI boundary: provide a concise actionable error.
        print(f"GPC 导入失败：{exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
