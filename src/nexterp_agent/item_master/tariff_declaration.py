"""Extract 2026 customs declaration profiles from the official catalog PDF.

The tax tariff is the legal hierarchy source.  This module is a second,
read-only source that attaches declaration/classification evidence to an
eight-digit tariff line.  It deliberately keeps source text and page numbers
so later material intake decisions can be audited without writing ERPNext.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import threading
import time
from typing import Any, Iterable
from uuid import uuid4


DECLARATION_SOURCE_VERSION = "中华人民共和国海关进出口商品涉税规范申报目录（2026年版）"
DECLARATION_EXPECTED_PAGES = 642
DECLARATION_SOURCE_URL = (
    "https://www.shuzih.com/pub/d935f7769d411942e69e4393ff1cccd4/"
    "862de1ed96a64830adfd3067d751dcb9.pdf"
)

DECLARATION_STAGES = (
    "queued",
    "inspecting",
    "extracting",
    "normalizing",
    "validating",
    "writing",
    "completed",
)
DECLARATION_STAGE_LABELS = {
    "queued": "排队",
    "inspecting": "检查 PDF",
    "extracting": "提取申报表",
    "normalizing": "整理属性",
    "validating": "核验税号",
    "writing": "写入证据包",
    "completed": "完成",
}
DECLARATION_STAGE_END = {
    "queued": 0.03,
    "inspecting": 0.12,
    "extracting": 0.72,
    "normalizing": 0.86,
    "validating": 0.95,
    "writing": 0.99,
    "completed": 1.0,
}

_CODE_LINE_RE = re.compile(
    r"^\s*(?P<code>\d{2}\.\d{2}|\d{4}\.\d{4}|\d{8,10})\s*(?P<rest>.*)$"
)
_PAGE_RE = re.compile(r"^\s*第\s*\d+\s*页\s*$")
_ATTRIBUTE_MARK_RE = re.compile(r"(?<![\d.])(\d{1,2})[\.．](?!\d)\s*")
_DASH_RE = re.compile(r"^[\-—–－]+")
_SPACE_RE = re.compile(r"\s+")
_PRICE_MARKERS = (
    "品牌",
    "型号",
    "GTIN",
    "CAS",
    "包装规格",
    "签约日期",
    "计价日期",
    "滞期费",
    "出口享惠情况",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_declaration_text(value: str) -> str:
    text = _SPACE_RE.sub(" ", str(value or "").replace("\u3000", " ")).strip()
    # The PDF wraps Chinese words at the column edge (for example
    # ``天然砂 除外``).  Remove only spaces between CJK characters; spaces in
    # measurements and Latin product names remain meaningful.
    return re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", text)


def normalize_declaration_code(value: str) -> str:
    return str(value or "").replace(".", "").strip()


def _split_attributes(value: str) -> list[str]:
    text = normalize_declaration_text(value)
    if not text:
        return []
    matches = list(_ATTRIBUTE_MARK_RE.finditer(text))
    if not matches:
        return []
    result: list[str] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        part = normalize_declaration_text(text[start:end]).strip("；;，, ")
        if part:
            result.append(part)
    return result


def _attribute_prefix(value: str) -> str:
    text = normalize_declaration_text(value)
    match = _ATTRIBUTE_MARK_RE.search(text)
    return normalize_declaration_text(text[: match.start()]).strip("；;，, ") if match else ""


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        item = normalize_declaration_text(value)
        if item and item not in result:
            result.append(item)
    return result


def _classification_attributes(attributes: Iterable[str]) -> list[str]:
    """Return a conservative derived subset for material classification.

    The catalog prints the complete declaration-element list rather than a
    machine-readable role column.  Commercial/price identifiers stay in the
    full declaration list; the rest are useful classification evidence.  The
    raw list is always retained, so this heuristic never loses source data.
    """

    return [
        value for value in _dedupe(attributes)
        if not any(marker in value for marker in _PRICE_MARKERS)
    ]


def _normalize_chapters(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raw = value.replace("，", ",").split(",")
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raw = [value]
    chapters: list[str] = []
    for item in raw:
        chapter = str(item or "").strip()
        if chapter.isdigit() and len(chapter) <= 2:
            chapter = chapter.zfill(2)
        if len(chapter) == 2 and chapter.isdigit() and chapter not in chapters:
            chapters.append(chapter)
    return tuple(chapters)


@dataclass(frozen=True)
class TariffDeclarationProfile:
    code: str
    name: str
    heading_code: str
    subheading_code: str
    heading_name: str
    hierarchy_path: tuple[str, ...] = ()
    declaration_attributes: tuple[str, ...] = ()
    classification_attributes: tuple[str, ...] = ()
    page: int = 0
    source_text: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "heading_code": self.heading_code,
            "subheading_code": self.subheading_code,
            "heading_name": self.heading_name,
            "hierarchy_path": list(self.hierarchy_path),
            "declaration_attributes": list(self.declaration_attributes),
            "classification_attributes": list(self.classification_attributes),
            "page": self.page,
            "source_text": self.source_text,
        }


@dataclass
class _Context:
    name: str
    attributes: list[str] = field(default_factory=list)


@dataclass
class DeclarationParserState:
    heading_code: str = ""
    heading_name: str = ""
    heading_name_parts: list[str] = field(default_factory=list)
    heading_attributes: list[str] = field(default_factory=list)
    heading_open: bool = False
    heading_attributes_open: bool = False
    contexts: dict[int, _Context] = field(default_factory=dict)
    pending_kind: str = ""
    pending_code: str = ""
    pending_name_parts: list[str] = field(default_factory=list)
    pending_attribute_parts: list[str] = field(default_factory=list)
    pending_attributes_open: bool = False
    pending_page: int = 0
    pending_source_lines: list[str] = field(default_factory=list)
    context_attributes_open: int | None = None


def _code_kind(code: str) -> str:
    length = len(normalize_declaration_code(code))
    if length == 4:
        return "heading"
    if length == 8:
        return "tariff_line"
    return "other"


def _dash_depth(text: str) -> int:
    match = _DASH_RE.match(str(text or ""))
    return len(match.group(0)) if match else 0


def _strip_dashes(text: str) -> str:
    return normalize_declaration_text(_DASH_RE.sub("", str(text or ""), count=1))


def _split_label_and_attributes(rest: str) -> tuple[str, list[str]]:
    text = normalize_declaration_text(rest)
    match = _ATTRIBUTE_MARK_RE.search(text)
    if not match:
        return _strip_dashes(text), []
    return _strip_dashes(text[: match.start()]), _split_attributes(text[match.start() :])


def _flush_pending(state: DeclarationParserState) -> TariffDeclarationProfile | None:
    if state.pending_kind != "tariff_line" or not state.pending_code:
        state.pending_kind = ""
        state.pending_code = ""
        state.pending_name_parts.clear()
        state.pending_attribute_parts.clear()
        state.pending_attributes_open = False
        state.pending_source_lines.clear()
        return None
    code = normalize_declaration_code(state.pending_code)
    name = normalize_declaration_text(" ".join(state.pending_name_parts))
    if len(code) != 8 or not name:
        state.pending_kind = ""
        state.pending_code = ""
        state.pending_name_parts.clear()
        state.pending_attribute_parts.clear()
        state.pending_source_lines.clear()
        return None
    context_parts = [state.contexts[key].name for key in sorted(state.contexts)]
    inherited = list(state.heading_attributes)
    for key in sorted(state.contexts):
        inherited.extend(state.contexts[key].attributes)
    attributes = _dedupe([*inherited, *state.pending_attribute_parts])
    heading_code = code[:4]
    subheading_code = code[:6]
    profile = TariffDeclarationProfile(
        code=code,
        name=name,
        heading_code=heading_code,
        subheading_code=subheading_code,
        heading_name=state.heading_name,
        hierarchy_path=tuple(context_parts),
        declaration_attributes=tuple(attributes),
        classification_attributes=tuple(_classification_attributes(attributes)),
        page=state.pending_page,
        source_text=normalize_declaration_text(" ".join(state.pending_source_lines)),
    )
    state.pending_kind = ""
    state.pending_code = ""
    state.pending_name_parts.clear()
    state.pending_attribute_parts.clear()
    state.pending_attributes_open = False
    state.pending_source_lines.clear()
    return profile


def parse_declaration_page_text(
    text: str,
    *,
    page: int = 0,
    state: DeclarationParserState | None = None,
    finalize: bool = True,
) -> list[TariffDeclarationProfile]:
    """Parse one native-text catalog page, carrying rows across page breaks."""

    state = state or DeclarationParserState()
    profiles: list[TariffDeclarationProfile] = []
    lines = [normalize_declaration_text(line) for line in str(text or "").splitlines()]
    for line in lines:
        if not line or _PAGE_RE.fullmatch(line):
            continue
        code_match = _CODE_LINE_RE.match(line)
        if code_match:
            profile = _flush_pending(state)
            if profile:
                profiles.append(profile)
            code = normalize_declaration_code(code_match.group("code"))
            rest = code_match.group("rest")
            kind = _code_kind(code)
            label, attributes = _split_label_and_attributes(rest)
            if kind == "heading":
                state.heading_code = code
                state.heading_name = label
                state.heading_name_parts = [label] if label else []
                state.heading_attributes = list(attributes)
                state.contexts.clear()
                state.heading_open = True
                state.heading_attributes_open = bool(attributes)
                state.context_attributes_open = None
                state.pending_kind = ""
                state.pending_source_lines.clear()
            elif kind == "tariff_line":
                state.heading_open = False
                state.heading_attributes_open = False
                state.context_attributes_open = None
                state.pending_kind = kind
                state.pending_code = code
                state.pending_name_parts = [label] if label else []
                state.pending_attribute_parts = list(attributes)
                state.pending_attributes_open = bool(attributes)
                state.pending_page = page
                state.pending_source_lines = [line]
            continue

        depth = _dash_depth(line)
        if depth:
            label, attributes = _split_label_and_attributes(line)
            if not label:
                continue
            profile = _flush_pending(state)
            if profile:
                profiles.append(profile)
            if state.heading_code:
                state.heading_open = False
                state.heading_attributes_open = False
                state.context_attributes_open = depth if attributes else None
                state.contexts = {
                    key: value for key, value in state.contexts.items() if key < depth
                }
                state.contexts[depth] = _Context(label, attributes)
            continue

        attributes = _split_attributes(line)
        if attributes:
            prefix = _attribute_prefix(line)
            if state.pending_kind == "tariff_line":
                if prefix:
                    if state.pending_attributes_open and state.pending_attribute_parts:
                        state.pending_attribute_parts[-1] = normalize_declaration_text(
                            f"{state.pending_attribute_parts[-1]} {prefix}"
                        )
                    elif not state.pending_attributes_open:
                        state.pending_name_parts.append(_strip_dashes(prefix))
                state.pending_attribute_parts.extend(attributes)
                state.pending_attributes_open = True
                state.pending_source_lines.append(line)
            elif state.heading_code and state.heading_open:
                if prefix:
                    if state.heading_attributes_open and state.heading_attributes:
                        state.heading_attributes[-1] = normalize_declaration_text(
                            f"{state.heading_attributes[-1]} {prefix}"
                        )
                    elif not state.heading_attributes_open:
                        state.heading_name_parts.append(_strip_dashes(prefix))
                        state.heading_name = normalize_declaration_text(" ".join(state.heading_name_parts))
                state.heading_attributes.extend(attributes)
                state.heading_attributes_open = True
            elif state.context_attributes_open is not None:
                context = state.contexts[state.context_attributes_open]
                if prefix and context.attributes:
                    context.attributes[-1] = normalize_declaration_text(
                        f"{context.attributes[-1]} {prefix}"
                    )
                state.contexts[state.context_attributes_open].attributes.extend(attributes)
            continue

        if state.pending_kind == "tariff_line":
            if state.pending_attributes_open and state.pending_attribute_parts:
                state.pending_attribute_parts[-1] = normalize_declaration_text(
                    f"{state.pending_attribute_parts[-1]} {line}"
                )
            else:
                state.pending_name_parts.append(line)
            state.pending_source_lines.append(line)
        elif state.heading_open:
            if state.heading_attributes_open and state.heading_attributes:
                state.heading_attributes[-1] = normalize_declaration_text(
                    f"{state.heading_attributes[-1]} {line}"
                )
            else:
                state.heading_name_parts.append(line)
                state.heading_name = normalize_declaration_text(" ".join(state.heading_name_parts))
        elif state.context_attributes_open is not None:
            context = state.contexts.get(state.context_attributes_open)
            if context and context.attributes:
                context.attributes[-1] = normalize_declaration_text(
                    f"{context.attributes[-1]} {line}"
                )
    if finalize:
        profile = _flush_pending(state)
        if profile:
            profiles.append(profile)
    return profiles


def validate_declaration_profiles(profiles: Iterable[TariffDeclarationProfile]) -> list[str]:
    rows = list(profiles)
    issues: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if len(row.code) != 8 or not row.code.isdigit():
            issues.append(f"invalid_code:{row.code}")
        if row.code in seen:
            issues.append(f"duplicate_code:{row.code}")
        seen.add(row.code)
        if row.heading_code != row.code[:4] or row.subheading_code != row.code[:6]:
            issues.append(f"parent_prefix:{row.code}")
        if not row.name:
            issues.append(f"missing_name:{row.code}")
    return issues


def load_declaration_profiles(path: str | Path) -> list[TariffDeclarationProfile]:
    profiles: list[TariffDeclarationProfile] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            profiles.append(
                TariffDeclarationProfile(
                    code=str(payload["code"]),
                    name=str(payload["name"]),
                    heading_code=str(payload["heading_code"]),
                    subheading_code=str(payload["subheading_code"]),
                    heading_name=str(payload.get("heading_name") or ""),
                    hierarchy_path=tuple(payload.get("hierarchy_path") or ()),
                    declaration_attributes=tuple(payload.get("declaration_attributes") or ()),
                    classification_attributes=tuple(payload.get("classification_attributes") or ()),
                    page=int(payload.get("page") or 0),
                    source_text=str(payload.get("source_text") or ""),
                )
            )
    return profiles


class _Cancelled(Exception):
    pass


class TariffDeclarationJobManager:
    """Progress-aware, read-only PDF extraction manager for the workbench."""

    def __init__(self, runtime_root: str | Path, *, page_reader_factory: Any = None):
        self.runtime_root = Path(runtime_root)
        self.page_reader_factory = page_reader_factory
        self._jobs: dict[str, dict[str, Any]] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._lock = threading.RLock()

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        mode = str(payload.get("mode") or "demo")
        if mode not in {"demo", "full", "slice"}:
            raise ValueError("mode 只能是 demo、slice 或 full")
        if mode in {"full", "slice"} and not bool(payload.get("confirmed")):
            raise ValueError("全量或局部模式需要明确确认")
        requested_source = str(payload.get("source_file") or "").strip()
        source_file = Path(requested_source).expanduser().resolve() if requested_source else (
            self.runtime_root / "source" / "customs-declaration-catalog-2026.pdf"
        ).resolve()
        chapters = _normalize_chapters(payload.get("chapters"))
        if mode in {"full", "slice"}:
            try:
                source_file.relative_to(self.runtime_root.resolve())
            except ValueError as exc:
                raise ValueError("source_file 必须位于申报目录 runtime 目录内") from exc
            if not source_file.is_file():
                raise ValueError("source_file 不存在或不是文件")
        with self._lock:
            active = next((job for job in self._jobs.values() if job["status"] in {"queued", "running"}), None)
            if active:
                raise ValueError(f"已有任务正在运行：{active['job_id']}")
            job_id = uuid4().hex
            job = {
                "job_id": job_id,
                "mode": mode,
                "chapters": list(chapters),
                "status": "queued",
                "stage": "queued",
                "stage_label": DECLARATION_STAGE_LABELS["queued"],
                "overall_progress": 0.0,
                "stage_progress": 0.0,
                "message": "任务已创建，等待后台线程启动",
                "source_version": DECLARATION_SOURCE_VERSION,
                "source_file": str(source_file) if source_file else None,
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
                "started_at": None,
                "elapsed_seconds": 0.0,
                "eta_seconds": None,
                "page_count": DECLARATION_EXPECTED_PAGES if mode == "demo" else None,
                "source_bytes": source_file.stat().st_size if source_file.is_file() else 0,
                "pages_processed": 0,
                "profiles_found": 0,
                "codes_found": 0,
                "issues_found": 0,
                "pages_per_second": 0.0,
                "recent_profiles": [],
                "recent_logs": ["任务已排队"],
                "output_files": [],
                "sha256": None,
                "error": None,
                "_created_epoch": time.time(),
            }
            self._jobs[job_id] = job
            event = threading.Event()
            self._cancel_events[job_id] = event
        thread = threading.Thread(
            target=self._run,
            args=(job_id, mode, source_file, chapters, event),
            name=f"tariff-declaration-{job_id[:8]}",
            daemon=True,
        )
        thread.start()
        return self.snapshot(job_id)

    def snapshot(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(str(job_id or ""))
            if not job:
                raise ValueError("任务不存在或已过期")
            result = {key: value for key, value in job.items() if not key.startswith("_")}
            result["can_cancel"] = result["status"] in {"queued", "running"}
            return json.loads(json.dumps(result, ensure_ascii=False))

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            if job_id not in self._jobs:
                raise ValueError("任务不存在或已过期")
            job = self._jobs[job_id]
            if job["status"] in {"queued", "running"}:
                self._cancel_events[job_id].set()
                job["message"] = "已请求停止，正在安全收尾"
                job["updated_at"] = _utc_now()
        return self.snapshot(job_id)

    def _update(self, job_id: str, *, stage: str | None = None, **changes: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if stage:
                job["stage"] = stage
                job["stage_label"] = DECLARATION_STAGE_LABELS[stage]
                job["overall_progress"] = max(float(job.get("overall_progress") or 0), DECLARATION_STAGE_END[stage])
            job.update(changes)
            started = job.get("_started_epoch")
            if started:
                elapsed = max(0.0, time.time() - started)
                job["elapsed_seconds"] = round(elapsed, 1)
                progress = float(job.get("overall_progress") or 0)
                if 0.03 < progress < 1:
                    job["eta_seconds"] = round(elapsed * (1 - progress) / progress, 1)
            job["updated_at"] = _utc_now()

    def _log(self, job_id: str, message: str) -> None:
        with self._lock:
            logs = self._jobs[job_id]["recent_logs"]
            logs.append(str(message))
            del logs[:-8]
        self._update(job_id, message=message)

    def _check_cancel(self, event: threading.Event) -> None:
        if event.is_set():
            raise _Cancelled()

    def _run(self, job_id: str, mode: str, source_file: Path, chapters: tuple[str, ...], event: threading.Event) -> None:
        self._update(job_id, status="running", stage="queued", started_at=_utc_now())
        with self._lock:
            self._jobs[job_id]["_started_epoch"] = time.time()
        try:
            if mode == "demo":
                self._run_demo(job_id, event)
            else:
                self._run_full(job_id, source_file, chapters, event)
        except _Cancelled:
            self._update(job_id, status="cancelled", eta_seconds=None, message="任务已停止；未写入 ERPNext")
            self._log(job_id, "收到停止请求；安全停止")
        except Exception as exc:  # pragma: no cover - API boundary
            self._update(job_id, status="failed", message=str(exc), error=str(exc), eta_seconds=None)
            self._log(job_id, f"任务失败：{exc}")

    def _run_demo(self, job_id: str, event: threading.Event) -> None:
        sample = TariffDeclarationProfile(
            code="25059000",
            name="其他",
            heading_code="2505",
            subheading_code="250590",
            heading_name="各种天然砂，不论是否着色，但第二十六章的含金属矿砂除外",
            declaration_attributes=("来源（如海砂、湖砂或河砂等）",),
            classification_attributes=("来源（如海砂、湖砂或河砂等）",),
            page=101,
            source_text="25.05 ... 2505.9000 -其他",
        )
        for stage, start, end, count, message in (
            ("inspecting", 0.03, 0.12, 6, "读取 PDF 元数据（演示）"),
            ("extracting", 0.12, 0.72, 20, "按页识别税号和申报要素（演示）"),
            ("normalizing", 0.72, 0.86, 8, "继承父级属性并整理字段（演示）"),
            ("validating", 0.86, 0.95, 6, "校验八位税号和重复项（演示）"),
            ("writing", 0.95, 0.99, 4, "生成属性证据包（演示）"),
        ):
            self._update(job_id, stage=stage, message=message)
            for index in range(count):
                self._check_cancel(event)
                self._update(job_id, stage_progress=round((index + 1) / count * 100, 1), overall_progress=round(start + (index + 1) / count * (end - start), 4))
                time.sleep(0.02)
        output_dir = self.runtime_root / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        profile_path = output_dir / "tariff-declaration-profiles.jsonl"
        profile_path.write_text(json.dumps(sample.as_dict(), ensure_ascii=False) + "\n", encoding="utf-8")
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(json.dumps({"mode": "demo", "source_version": DECLARATION_SOURCE_VERSION, "profiles": 1, "erpnext_written": False}, ensure_ascii=False, indent=2), encoding="utf-8")
        self._finish(job_id, [sample], [], profile_path, manifest_path)

    def _run_full(self, job_id: str, source_file: Path, chapters: tuple[str, ...], event: threading.Event) -> None:
        self._update(job_id, stage="inspecting", stage_progress=0, message="检查 PDF 页数和文本层")
        digest = hashlib.sha256()
        with source_file.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        self._update(job_id, sha256=digest.hexdigest())
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("全量模式需要安装 pypdf：python -m pip install pypdf") from exc
        reader = PdfReader(str(source_file), strict=False)
        page_count = len(reader.pages)
        self._update(job_id, page_count=page_count, stage_progress=100, message=f"已确认 {page_count} 页")
        self._update(job_id, stage="extracting", stage_progress=0, message="逐页提取税号与申报要素")
        state = DeclarationParserState()
        profiles: list[TariffDeclarationProfile] = []
        started = time.time()
        for page_number, page in enumerate(reader.pages, start=1):
            self._check_cancel(event)
            page_profiles = parse_declaration_page_text(page.extract_text() or "", page=page_number, state=state, finalize=False)
            profiles.extend(page_profiles)
            self._update(
                job_id,
                pages_processed=page_number,
                stage_progress=round(page_number / max(1, page_count) * 100, 1),
                overall_progress=round(0.12 + page_number / max(1, page_count) * 0.60, 4),
                profiles_found=len(profiles),
                codes_found=len({row.code for row in profiles}),
                pages_per_second=round(page_number / max(0.001, time.time() - started), 2),
                recent_profiles=[row.as_dict() for row in profiles[-6:]],
                message=f"已处理第 {page_number}/{page_count} 页，发现 {len(profiles)} 条税号属性记录",
            )
        profiles.extend(parse_declaration_page_text("", page=page_count, state=state, finalize=True))
        self._update(job_id, stage="normalizing", stage_progress=0, message="整理继承属性和字段角色")
        profiles = _deduplicate_profiles(profiles)
        all_profiles_count = len(profiles)
        if chapters:
            profiles = [profile for profile in profiles if profile.code[:2] in chapters]
            self._log(job_id, f"局部模式：保留第 {', '.join(chapters)} 章，共 {len(profiles)} 条记录（全量解析 {all_profiles_count} 条）")
        self._update(job_id, stage_progress=100, overall_progress=0.86, profiles_found=len(profiles), codes_found=len(profiles))
        self._update(job_id, stage="validating", stage_progress=0, message="校验八位税号、父级前缀和重复项")
        issues = validate_declaration_profiles(profiles)
        self._update(job_id, stage_progress=100, overall_progress=0.95, issues_found=len(issues))
        self._write_outputs(job_id, source_file, profiles, issues, all_profiles_count=all_profiles_count)

    def _finish(self, job_id: str, profiles: list[TariffDeclarationProfile], issues: list[str], profile_path: Path, manifest_path: Path) -> None:
        self._update(job_id, status="completed", stage="completed", stage_progress=100, overall_progress=1.0, eta_seconds=0, profiles_found=len(profiles), codes_found=len(profiles), issues_found=len(issues), recent_profiles=[row.as_dict() for row in profiles[-6:]], output_files=[str(profile_path), str(manifest_path)], message="属性证据包已生成；未写入 ERPNext")

    def _write_outputs(
        self,
        job_id: str,
        source_file: Path,
        profiles: list[TariffDeclarationProfile],
        issues: list[str],
        *,
        all_profiles_count: int | None = None,
    ) -> None:
        output_dir = self.runtime_root / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        profile_path = output_dir / "tariff-declaration-profiles.jsonl"
        with profile_path.open("w", encoding="utf-8") as handle:
            for row in profiles:
                handle.write(json.dumps(row.as_dict(), ensure_ascii=False) + "\n")
        manifest_path = output_dir / "manifest.json"
        job = self._jobs[job_id]
        manifest_path.write_text(json.dumps({"source_url": DECLARATION_SOURCE_URL, "source_version": DECLARATION_SOURCE_VERSION, "source_file": str(source_file), "pages": job.get("page_count"), "mode": job.get("mode"), "chapters": job.get("chapters") or [], "profiles": len(profiles), "profiles_before_chapter_filter": all_profiles_count if all_profiles_count is not None else len(profiles), "issues": issues, "erpnext_written": False, "generated_at": _utc_now()}, ensure_ascii=False, indent=2), encoding="utf-8")
        self._finish(job_id, profiles, issues, profile_path, manifest_path)


def _deduplicate_profiles(profiles: Iterable[TariffDeclarationProfile]) -> list[TariffDeclarationProfile]:
    result: list[TariffDeclarationProfile] = []
    positions: dict[str, int] = {}
    for profile in profiles:
        existing_index = positions.get(profile.code)
        if existing_index is None:
            positions[profile.code] = len(result)
            result.append(profile)
            continue
        existing = result[existing_index]
        result[existing_index] = TariffDeclarationProfile(
            code=existing.code,
            name=existing.name or profile.name,
            heading_code=existing.heading_code,
            subheading_code=existing.subheading_code,
            heading_name=existing.heading_name or profile.heading_name,
            hierarchy_path=existing.hierarchy_path or profile.hierarchy_path,
            declaration_attributes=tuple(_dedupe([*existing.declaration_attributes, *profile.declaration_attributes])),
            classification_attributes=tuple(_classification_attributes([*existing.declaration_attributes, *profile.declaration_attributes])),
            page=existing.page or profile.page,
            source_text=existing.source_text or profile.source_text,
        )
    return result


__all__ = [
    "DECLARATION_EXPECTED_PAGES",
    "DECLARATION_SOURCE_URL",
    "DECLARATION_SOURCE_VERSION",
    "DECLARATION_STAGE_LABELS",
    "DECLARATION_STAGES",
    "DeclarationParserState",
    "TariffDeclarationJobManager",
    "TariffDeclarationProfile",
    "load_declaration_profiles",
    "normalize_declaration_code",
    "normalize_declaration_text",
    "parse_declaration_page_text",
    "validate_declaration_profiles",
]
