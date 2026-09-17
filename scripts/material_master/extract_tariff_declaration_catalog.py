"""Extract the 2026 customs declaration catalog into an auditable JSONL package.

This command is deliberately offline: download and licence checks happen outside
the parser.  The workbench uses the same parser through TariffDeclarationJobManager.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from nexterp_agent.item_master.tariff_declaration import (  # noqa: E402
    DECLARATION_SOURCE_VERSION,
    DeclarationParserState,
    _deduplicate_profiles,
    parse_declaration_page_text,
    validate_declaration_profiles,
    TariffDeclarationProfile,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _chapters(value: str) -> tuple[str, ...]:
    result: list[str] = []
    for item in str(value or "").replace("，", ",").split(","):
        chapter = item.strip()
        if chapter.isdigit() and len(chapter) <= 2:
            chapter = chapter.zfill(2)
        if len(chapter) == 2 and chapter.isdigit() and chapter not in result:
            result.append(chapter)
    return tuple(result)


def extract(source: Path, output: Path, *, chapters: tuple[str, ...] = ()) -> dict[str, object]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("需要安装 pypdf：python -m pip install pypdf") from exc

    reader = PdfReader(str(source), strict=False)
    state = DeclarationParserState()
    profiles: list[TariffDeclarationProfile] = []
    for page_number, page in enumerate(reader.pages, start=1):
        profiles.extend(parse_declaration_page_text(page.extract_text() or "", page=page_number, state=state, finalize=False))
        if page_number == 1 or page_number % 25 == 0 or page_number == len(reader.pages):
            print(f"页 {page_number}/{len(reader.pages)} · 已识别 {len(profiles)} 条", flush=True)
    profiles.extend(parse_declaration_page_text("", page=len(reader.pages), state=state, finalize=True))
    profiles = _deduplicate_profiles(profiles)
    before_filter = len(profiles)
    if chapters:
        profiles = [row for row in profiles if row.code[:2] in chapters]
    issues = validate_declaration_profiles(profiles)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in profiles:
            handle.write(json.dumps(row.as_dict(), ensure_ascii=False) + "\n")
    manifest = {
        "source_version": DECLARATION_SOURCE_VERSION,
        "source_file": str(source.resolve()),
        "source_sha256": _sha256(source),
        "pages": len(reader.pages),
        "chapters": list(chapters),
        "profiles": len(profiles),
        "profiles_before_chapter_filter": before_filter,
        "issues": issues,
        "erpnext_written": False,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    manifest_path = output.with_name("manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), **manifest}, ensure_ascii=False, indent=2))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="提取海关涉税规范申报目录 2026")
    parser.add_argument("--input", required=True, type=Path, help="本地 PDF 路径")
    parser.add_argument("--output", required=True, type=Path, help="输出 JSONL 路径")
    parser.add_argument("--chapters", default="", help="仅保留章节，例如 25,73,84,85")
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"输入文件不存在：{args.input}")
    extract(args.input, args.output, chapters=_chapters(args.chapters))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
