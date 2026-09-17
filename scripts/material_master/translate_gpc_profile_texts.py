#!/usr/bin/env python3
"""Translate GPC Brick definition/include/exclude text into Chinese work text."""

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

from import_gpc_reference import _unwrap_translation_values, write_jsonl  # noqa: E402


RUNTIME_ROOT = ROOT / ".runtime" / "gpc-reference"
VERSION_RE = re.compile(r"^\d{4}-\d{2}$")
PROFILE_FIELDS = ("definition", "includes", "excludes")
HAN_RE = re.compile(r"[\u3400-\u9fff]")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _source_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def extract_profile_texts(profiles: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate profile prose by exact official-text SHA-256."""

    rows: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        brick_code = _text(profile.get("code"))
        brick_name = _text(profile.get("official_name"))
        for field in PROFILE_FIELDS:
            official_text = _text(profile.get(field))
            if not official_text:
                continue
            source_hash = _source_hash(official_text)
            row = rows.setdefault(
                source_hash,
                {
                    "id": f"T{source_hash[:24]}",
                    "source_hash": source_hash,
                    "official_text": official_text,
                    "contexts": [],
                    "usage_count": 0,
                },
            )
            if row["official_text"] != official_text:
                raise ValueError(f"GPC 详情文本哈希冲突：{source_hash}")
            row["usage_count"] += 1
            if len(row["contexts"]) < 4:
                context = {"brick_code": brick_code, "brick_name": brick_name, "field": field}
                if context not in row["contexts"]:
                    row["contexts"].append(context)
    return [rows[key] for key in sorted(rows)]


def placeholder(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "source_hash": row["source_hash"],
        "official_text": row["official_text"],
        "working_text": "",
        "status": "missing",
        "model": "",
        "usage_count": row["usage_count"],
    }


def valid_translation(row: dict[str, Any], source: dict[str, Any]) -> bool:
    """Reject missing, stale, meta, or severely truncated Chinese output."""

    working_text = _text(row.get("working_text"))
    official_text = source["official_text"]
    if (
        row.get("source_hash") != source["source_hash"]
        or _text(row.get("official_text")) != official_text
        or not working_text
        or not HAN_RE.search(working_text)
    ):
        return False
    if len(official_text) >= 50 and len(working_text) / len(official_text) < 0.14:
        return False
    lowered = working_text.casefold()
    return not any(token in lowered for token in ("无法翻译", "无法提供翻译", "以下是翻译", "翻译如下", "```"))


def pack_batches(rows: list[dict[str, Any]], max_characters: int) -> list[list[dict[str, Any]]]:
    """Pack complete texts without splitting an official source paragraph."""

    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_size = 0
    budget = max(1, int(max_characters))
    for row in rows:
        size = len(row["official_text"]) + sum(len(_text(item.get("brick_name"))) for item in row["contexts"]) + 100
        if current and current_size + size > budget:
            batches.append(current)
            current = []
            current_size = 0
        current.append(row)
        current_size += size
    if current:
        batches.append(current)
    return batches


def translate_batch(batch: list[dict[str, Any]]) -> tuple[dict[str, str], str]:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    from nexterp_agent.agent_runtime.deepseek_material_request import call_deepseek_json, load_deepseek_settings

    settings = load_deepseek_settings()
    messages = [
        {
            "role": "system",
            "content": (
                "你是 GS1 GPC 分类说明翻译器。把每条 official_text 忠实翻译成简体中文。"
                "只返回 JSON 对象，键必须是原 id，值必须是完整中文译文；不得遗漏、合并、解释或改写 id。"
                "严格保留否定、条件、范围、包含与排除关系，不添加原文没有的产品、标准或判断。"
                "GS1、GPC、GTIN、技术缩写、标准号和必要的拉丁学名应保留；产品名称使用中国工业和商业常用译法。"
                "contexts 只用于确定语境，不需要翻译或输出。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "items": [
                        {"id": row["id"], "official_text": row["official_text"], "contexts": row["contexts"]}
                        for row in batch
                    ]
                },
                ensure_ascii=False,
            ),
        },
    ]
    source_characters = sum(len(row["official_text"]) for row in batch)
    payload = call_deepseek_json(
        messages,
        settings=settings,
        max_tokens=min(384_000, max(16_384, int(source_characters * 1.4))),
        thinking={"type": "disabled"},
        timeout_seconds=max(int(getattr(settings, "timeout_seconds", 120)), 900),
        max_retries=0,
        allow_json_array=True,
    )
    values = _unwrap_translation_values(payload)
    if isinstance(values, list):
        values = {
            _text(item.get("id") or item.get("code")): _text(item.get("working_text") or item.get("translation") or item.get("text"))
            for item in values
            if isinstance(item, dict)
        }
    if not isinstance(values, dict):
        raise ValueError("GPC 详情翻译响应不是 JSON 对象")
    translated = {row["id"]: _text(values.get(row["id"])) for row in batch}
    return {key: value for key, value in translated.items() if value}, settings.model


def translate_profile_texts(
    version: str,
    *,
    max_batch_characters: int = 100_000,
    min_batch_characters: int = 12_500,
) -> dict[str, Any]:
    if not VERSION_RE.fullmatch(version):
        raise ValueError("GPC 版本必须是 YYYY-MM")
    version_root = (RUNTIME_ROOT / version).resolve()
    if version_root.parent != RUNTIME_ROOT.resolve():
        raise ValueError("GPC 运行期路径越界")
    profiles_path = version_root / "brick-profiles.jsonl"
    manifest_path = version_root / "manifest.json"
    audit_path = version_root / "audit.json"
    output_path = version_root / "profile-text-translations.zh-CN.jsonl"
    if not profiles_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(f"GPC {version} 尚未导入")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    previous_meta = manifest.get("profile_text_translation") or {}
    texts = extract_profile_texts(load_jsonl(profiles_path))
    by_id = {row["id"]: row for row in texts}
    translations = {row["id"]: placeholder(row) for row in texts}
    if output_path.is_file():
        for existing in load_jsonl(output_path):
            row_id = _text(existing.get("id"))
            source = by_id.get(row_id)
            if source and valid_translation(existing, source):
                translations[row_id] = existing

    request_count = 0
    failed_batches = 0
    model = ""
    budget = max(1, int(max_batch_characters))
    minimum = max(1, int(min_batch_characters))
    passes: list[dict[str, Any]] = []
    while True:
        missing = [row for row in texts if translations[row["id"]].get("status") != "machine"]
        if not missing:
            break
        pass_translated = 0
        pass_failures = 0
        batches = pack_batches(missing, budget)
        for batch in batches:
            try:
                request_count += 1
                values, model = translate_batch(batch)
                for row in batch:
                    working_text = values.get(row["id"], "")
                    candidate = {
                        **placeholder(row),
                        "working_text": working_text,
                        "status": "machine",
                        "model": model,
                    }
                    if not valid_translation(candidate, row):
                        continue
                    translations[row["id"]] = candidate
                    pass_translated += 1
            except Exception:
                failed_batches += 1
                pass_failures += 1
            write_jsonl(output_path, (translations[row["id"]] for row in texts))
        passes.append(
            {
                "max_batch_characters": budget,
                "input_items": len(missing),
                "batch_count": len(batches),
                "translated_items": pass_translated,
                "failed_batches": pass_failures,
            }
        )
        remaining = sum(1 for row in translations.values() if row.get("status") != "machine")
        if not remaining or budget <= minimum:
            break
        budget = max(minimum, budget // 2)

    output_rows = [translations[row["id"]] for row in texts]
    translated_count = sum(1 for row in output_rows if row.get("status") == "machine" and _text(row.get("working_text")))
    metadata = {
        "language": "zh-CN",
        "status": "complete" if translated_count == len(texts) else "partial",
        "model": model or _text(previous_meta.get("model")),
        "request_count": int(previous_meta.get("request_count") or 0) + request_count,
        "failed_batches": int(previous_meta.get("failed_batches") or 0) + failed_batches,
        "input_items": len(texts),
        "translated_items": translated_count,
        "missing_items": len(texts) - translated_count,
        "source_field_instances": sum(row["usage_count"] for row in texts),
        "deduplicated_instances": sum(row["usage_count"] for row in texts) - len(texts),
        "passes": list(previous_meta.get("passes") or []) + passes,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest["profile_text_translation"] = metadata
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if audit_path.is_file():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        audit["profile_text_translation_missing_count"] = metadata["missing_items"]
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"root": str(version_root), "output": str(output_path), "profile_text_translation": metadata}


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate GPC Brick definition/include/exclude text")
    parser.add_argument("--version", default="2026-05")
    parser.add_argument("--max-batch-characters", type=int, default=100_000)
    parser.add_argument("--min-batch-characters", type=int, default=12_500)
    args = parser.parse_args()
    try:
        result = translate_profile_texts(
            args.version,
            max_batch_characters=args.max_batch_characters,
            min_batch_characters=args.min_batch_characters,
        )
    except Exception as exc:
        print(f"GPC 详情文本翻译失败：{exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["profile_text_translation"]["missing_items"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
