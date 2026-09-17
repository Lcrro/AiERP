"""Progress-aware extraction of the public 2026 Chinese import/export tariff.

The extractor is deliberately isolated from ERPNext.  It downloads a frozen,
allow-listed public source, produces an auditable JSONL candidate tree and
reports progress through a small in-process job manager used by the workbench.
The browser can therefore be validated in demo mode without downloading the
70 MB source document.
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
from typing import Any, Callable, Iterable
from urllib.parse import urlparse
from uuid import uuid4

import requests


TARIFF_SOURCE_URL = (
    "https://gss.mof.gov.cn/gzdt/zhengcefabu/202512/"
    "P020251231607833453633.pdf"
)
TARIFF_SOURCE_VERSION = "中华人民共和国进出口税则（2026）"
TARIFF_EXPECTED_PAGES = 1492
TARIFF_EXPECTED_BYTES = 70_026_277
TARIFF_ALLOWED_HOSTS = frozenset({"gss.mof.gov.cn"})

STAGES = (
    "queued",
    "downloading",
    "inspecting",
    "extracting",
    "normalizing",
    "validating",
    "writing",
    "completed",
)
STAGE_LABELS = {
    "queued": "排队",
    "downloading": "下载源文件",
    "inspecting": "检查 PDF",
    "extracting": "提取目录",
    "normalizing": "整理多层类目",
    "validating": "校验编码与层级",
    "writing": "写入候选发布包",
    "completed": "完成",
}
STAGE_END = {
    "queued": 0.03,
    "downloading": 0.13,
    "inspecting": 0.20,
    "extracting": 0.72,
    "normalizing": 0.84,
    "validating": 0.94,
    "writing": 0.99,
    "completed": 1.0,
}


@dataclass(frozen=True)
class TariffNode:
    """A normalized candidate classification node extracted from one page."""

    code: str
    name: str
    level: int
    parent_code: str | None = None
    page: int = 0
    kind: str = "heading"

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "level": self.level,
            "parent_code": self.parent_code,
            "page": self.page,
            "kind": self.kind,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_source_url(value: str) -> str:
    """Only allow the known Ministry of Finance source in full mode."""

    url = str(value or TARIFF_SOURCE_URL).strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in TARIFF_ALLOWED_HOSTS:
        raise ValueError("全量模式只允许使用财政部公开的 2026 税则 PDF")
    return url


_CODE_RE = re.compile(r"(?<!\d)(\d{4}(?:\.\d{2}){0,2}|\d{8})(?!\d)")
_WORD_CODE_RE = re.compile(
    r"^(?:\d{2}\.\d{2}|\d{4}\.\d{4}|\d{4}\.\d{2}\.\d{2}|\d{8})$"
)
_LEADING_NUMBER_RE = re.compile(r"^\s*\d{1,5}\s+")
_SPACE_RE = re.compile(r"\s+")
_SCOPE_ORDINAL_RE = re.compile(r"^第([一二三四五六七八九十]+)(类|章)$")
_SCOPE_TITLE_STOP_MARKERS = ("注释：", "注释:", "子目注释：", "子目注释:", "本国子目注释：", "本国子目注释:")


@dataclass
class TariffHierarchyState:
    """Coordinate-parser state that carries dash hierarchy across pages."""

    active_heading_code: str = ""
    marker_context: dict[int, str] = field(default_factory=dict)
    pending_hierarchy_context: list[tuple[int, str]] = field(default_factory=list)


def normalize_name(value: str) -> str:
    return _SPACE_RE.sub(" ", str(value or "").replace("\u3000", " ")).strip(" -—\t")


def normalize_code(value: str) -> str:
    return str(value or "").replace(".", "").strip()


def _chinese_ordinal_number(value: str) -> int:
    digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    text = str(value or "").strip()
    if text == "十":
        return 10
    if "十" in text:
        tens, ones = text.split("十", 1)
        return (digits.get(tens, 1) * 10) + digits.get(ones, 0)
    return digits.get(text, 0)


def _hierarchy_marker_depth(value: str) -> int:
    match = re.match(r"^\s*((?:[-—–]\s*)+)", str(value or ""))
    if not match:
        return 0
    return sum(character in {"-", "—", "–"} for character in match.group(1))


def _clean_scope_title(value: str) -> str:
    title = normalize_name(value)
    for marker in _SCOPE_TITLE_STOP_MARKERS:
        if marker in title:
            title = title.split(marker, 1)[0].strip()
    return title


def _code_level(code: str) -> int:
    digits = normalize_code(code)
    if len(digits) >= 8:
        return 4
    if len(digits) >= 6:
        return 3
    if len(digits) >= 4:
        return 2
    return 1


def parse_tariff_page_text(text: str, page: int = 0) -> list[TariffNode]:
    """Extract code/name rows from a native-text tariff page.

    The official document uses a stable first-column code and name layout. PDF
    text extraction can wrap a name onto the next line, so the parser keeps the
    most recent code and joins short continuation lines. It intentionally does
    not treat rates, legal notes or page headers as material nodes.
    """

    nodes: list[TariffNode] = []
    pending: TariffNode | None = None
    for raw_line in str(text or "").splitlines():
        line = normalize_name(raw_line)
        if not line or "税则号列" in line or "货品名称" in line:
            continue
        match = _CODE_RE.search(line)
        if match:
            code = normalize_code(match.group(1))
            before = line[: match.start()]
            after = line[match.end() :]
            name = normalize_name(after)
            # A sequence number is often rendered immediately before the code.
            before = _LEADING_NUMBER_RE.sub("", before)
            if not name:
                continue
            if pending is not None:
                nodes.append(pending)
            kind = "sku" if len(code) >= 8 else "heading"
            pending = TariffNode(
                code=code,
                name=name,
                level=_code_level(code),
                page=page,
                kind=kind,
            )
            continue
        if pending is not None and not re.search(r"\d+%|\d+\.\d+", line):
            # Wrapped names are generally indented and do not begin with a
            # legal-note marker. Keep the conservative length bound so a page
            # footer cannot become part of a material name.
            if len(line) <= 160 and not line.startswith(("注：", "注:", "说明", "本目录")):
                pending = TariffNode(
                    code=pending.code,
                    name=normalize_name(f"{pending.name} {line}"),
                    level=pending.level,
                    parent_code=pending.parent_code,
                    page=pending.page,
                    kind=pending.kind,
                )
    if pending is not None:
        nodes.append(pending)
    return nodes


def _word_code(value: str) -> str | None:
    """Accept only values rendered in the tax-code column."""

    candidate = str(value or "").strip()
    if not _WORD_CODE_RE.fullmatch(candidate):
        return None
    digits = normalize_code(candidate)
    if len(digits) not in {4, 6, 8}:
        return None
    # HS chapters are 01-97. This rejects years and quantities that happen to
    # be four digits while retaining headings such as 82.02.
    if int(digits[:2]) < 1 or int(digits[:2]) > 97:
        return None
    return digits


def _scope_line_groups(words: Iterable[Any]) -> list[list[tuple[float, float, float, str]]]:
    rows: list[list[tuple[float, float, float, str]]] = []
    for raw in sorted(
        (
            (float(item[0]), float(item[1]), float(item[2]), str(item[4]))
            for item in words
            if isinstance(item, (tuple, list)) and len(item) >= 5
        ),
        key=lambda item: (item[1], item[0]),
    ):
        _x0, y0, _x1, _value = raw
        if y0 < 50 or y0 > 780:
            continue
        if not rows or abs(rows[-1][0][1] - y0) > 2.2:
            rows.append([raw])
        else:
            rows[-1].append(raw)
    return rows


def parse_tariff_scope_nodes(words: Iterable[Any], page: int = 0) -> list[TariffNode]:
    """Extract centered official section/chapter titles outside the tariff table."""

    lines = _scope_line_groups(words)
    nodes: list[TariffNode] = []
    for index, line in enumerate(lines):
        ordered = sorted(line, key=lambda item: item[0])
        compact = "".join(item[3] for item in ordered).replace(" ", "")
        match = _SCOPE_ORDINAL_RE.fullmatch(compact)
        if not match:
            continue
        x0 = min(item[0] for item in ordered)
        x1 = max(item[2] for item in ordered)
        # The table of contents uses left-aligned ordinals. Official scope
        # titles are centered, so this rejects TOC and legal-note references.
        if x0 <= 200 or x1 >= 400:
            continue
        ordinal_y = ordered[0][1]
        title_parts: list[str] = []
        for following in lines[index + 1 :]:
            following_y = following[0][1]
            text = normalize_name(" ".join(item[3] for item in sorted(following, key=lambda item: item[0])))
            compact_text = text.replace(" ", "")
            if following_y - ordinal_y > 50 or _SCOPE_ORDINAL_RE.fullmatch(compact_text):
                break
            if any(compact_text.startswith(marker.replace(" ", "")) for marker in _SCOPE_TITLE_STOP_MARKERS):
                break
            title_parts.append(text)
        title = _clean_scope_title(" ".join(title_parts))
        number = _chinese_ordinal_number(match.group(1))
        if not number or not title:
            continue
        is_section = match.group(2) == "类"
        nodes.append(TariffNode(
            code=f"S{number:02d}" if is_section else f"{number:02d}",
            name=title,
            level=0 if is_section else 1,
            page=page,
            kind="section" if is_section else "chapter",
        ))
    return nodes


def _word_line_groups(words: Iterable[Any]) -> list[list[tuple[float, float, str]]]:
    rows: list[list[tuple[float, float, str]]] = []
    for raw in sorted(
        (
            (float(item[0]), float(item[1]), str(item[4]))
            for item in words
            if isinstance(item, (tuple, list)) and len(item) >= 5
        ),
        key=lambda item: (item[1], item[0]),
    ):
        x0, y0, value = raw
        if y0 < 85 or y0 > 760:
            continue
        if not rows or abs(rows[-1][0][1] - y0) > 2.2:
            rows.append([raw])
        else:
            rows[-1].append(raw)
    return rows


def _set_marker_context(state: TariffHierarchyState, depth: int, name: str) -> None:
    if depth <= 0 or not name:
        return
    state.marker_context[depth] = name
    for existing_depth in tuple(state.marker_context):
        if existing_depth > depth:
            del state.marker_context[existing_depth]


def _subheading_name(
    state: TariffHierarchyState,
    *,
    row_name: str,
    marker_depth: int,
) -> str:
    if marker_depth >= 3:
        base = state.marker_context.get(2) or row_name
    elif marker_depth == 2:
        base = row_name
    else:
        base = state.marker_context.get(2) or row_name
    group = state.marker_context.get(1)
    parts = [part for part in (group, base) if part]
    unique_parts: list[str] = []
    for part in parts:
        if part not in unique_parts:
            unique_parts.append(part)
    return " / ".join(unique_parts)


def parse_tariff_page_words(
    words: Iterable[Any],
    page: int = 0,
    *,
    include_hierarchy: bool = False,
    hierarchy_state: TariffHierarchyState | None = None,
) -> list[TariffNode]:
    """Parse the fixed first three PDF columns using word coordinates.

    The official table places the tax code around x=61..97 and the name around
    x=100..224 points. Rates begin around x=242. Restricting extraction to
    these columns prevents tariff numbers embedded in legal notes from becoming
    false material nodes.
    """

    word_list = list(words)
    lines = _word_line_groups(word_list)
    code_rows: list[tuple[int, str, str, int]] = []
    for index, line in enumerate(lines):
        code = next(
            # Actual table codes start around x=61.6. Notes use an indented
            # x=92+ position, so the narrower band is important for avoiding
            # false nodes such as “税目 08.01” in chapter commentary.
            (_word_code(value) for x0, _y0, value in line if 55 <= x0 < 82 and _word_code(value)),
            None,
        )
        if not code:
            continue
        name_words = [value for x0, _y0, value in line if 98 <= x0 < 238]
        raw_name = " ".join(name_words).strip()
        marker_depth = _hierarchy_marker_depth(raw_name)
        name = normalize_name(raw_name)
        if name:
            code_rows.append((index, code, name, marker_depth))

    nodes = parse_tariff_scope_nodes(word_list, page) if include_hierarchy else []
    state = hierarchy_state or TariffHierarchyState()
    pending_context_text = ""
    pending_hierarchy_context = list(state.pending_hierarchy_context)
    state.pending_hierarchy_context.clear()
    for row_index, (line_index, code, name, marker_depth) in enumerate(code_rows):
        if len(code) == 4 and state.active_heading_code != code:
            state.active_heading_code = code
            state.marker_context.clear()
            pending_context_text = ""
            pending_hierarchy_context.clear()
        for context_depth, context_name in pending_hierarchy_context:
            _set_marker_context(state, context_depth, context_name)

        next_line = code_rows[row_index + 1][0] if row_index + 1 < len(code_rows) else len(lines)
        continuation: list[str] = []
        next_context: list[tuple[int, str]] = []
        next_context_text_parts: list[str] = []
        for continuation_line in lines[line_index + 1 : next_line]:
            # Rate footnotes can overlap the name-column x range near a page
            # boundary. Match their semantics rather than x/y coordinates:
            # legitimate wrapped names and `ex` supplemental rows may also
            # begin in the left margin or reach the bottom of a page.
            full_line_text = normalize_name(
                " ".join(value for _x0, _y0, value in continuation_line)
            )
            if any(
                marker in full_line_text
                for marker in (
                    "最惠国税率",
                    "普通税率",
                    "协定税率",
                    "关税配额税率",
                    "对配额外进口",
                    "进口棉花完税价格",
                    "暂定从价税率",
                    "对上式计算结果",
                    "为关税完税价格",
                    "Ri=",
                    "位小数。其中Ri",
                    "单位为元/千克",
                    "仅关税配额",
                )
            ):
                continue
            words_in_name_column = [
                value for x0, _y0, value in continuation_line if 98 <= x0 < 238
            ]
            raw_continuation = " ".join(words_in_name_column).strip()
            if not raw_continuation:
                continue
            # A leading hyphen is the PDF's hierarchy marker. Such a line is
            # the context for the next coded row (e.g. “其他螺钉及螺栓”), not a
            # wrapped continuation of the preceding SKU name.
            context_depth = _hierarchy_marker_depth(raw_continuation)
            if context_depth:
                next_context.append((context_depth, normalize_name(raw_continuation)))
                next_context_text_parts.append(raw_continuation)
            elif next_context:
                previous_depth, previous_name = next_context[-1]
                next_context[-1] = (
                    previous_depth,
                    normalize_name(f"{previous_name} {raw_continuation}"),
                )
                next_context_text_parts[-1] = (
                    f"{next_context_text_parts[-1]} {raw_continuation}"
                )
            else:
                continuation.append(raw_continuation)
        leaf_context_parts = [pending_context_text] if pending_context_text else []
        # Dash depths 1-2 describe the six-digit HS subheading. Deeper,
        # uncoded groups describe domestic eight-digit rows and must be
        # flattened into each leaf name, including siblings on the next page.
        if len(code) == 8:
            for context_depth in sorted(state.marker_context):
                context_name = state.marker_context[context_depth]
                already_included = any(
                    context_name == part or context_name in part
                    for part in leaf_context_parts
                )
                if 3 <= context_depth < marker_depth and not already_included:
                    leaf_context_parts.append(context_name)
        name_parts = [*leaf_context_parts, name, *continuation]
        full_name = normalize_name(" ".join(part for part in name_parts if part))

        # Replace the previous row at the same dash depth before deriving a
        # synthetic six-digit label. A sibling is not an ancestor.
        _set_marker_context(state, marker_depth, name)
        if include_hierarchy and len(code) == 8:
            nodes.append(
                TariffNode(
                    code=code[:6],
                    name=_subheading_name(
                        state,
                        row_name=name,
                        marker_depth=marker_depth,
                    ),
                    level=3,
                    page=page,
                    kind="subheading",
                )
            )
        nodes.append(
            TariffNode(
                code=code,
                name=full_name,
                level=_code_level(code),
                page=page,
                kind=(
                    "sku"
                    if len(code) == 8
                    else "subheading"
                    if include_hierarchy and len(code) == 6
                    else "heading"
                ),
            )
        )
        pending_context_text = normalize_name(" ".join(next_context_text_parts))
        pending_hierarchy_context = next_context
    # Parent labels can end one page while their coded children begin on the
    # next. Carry hierarchy only; the official eight-digit row name stays
    # unchanged and does not inherit display text from the previous page.
    state.pending_hierarchy_context = list(pending_hierarchy_context)
    return nodes


def _hierarchy_name_score(node: TariffNode) -> tuple[int, int, int]:
    normalized = normalize_name(node.name)
    generic = normalized in {"其他", "未列名", "其他未列名"}
    return (0 if generic else 1, normalized.count("/"), len(normalized))


def _common_hierarchy_name(nodes: list[TariffNode]) -> str:
    paths = [
        [normalize_name(part) for part in node.name.split("/") if normalize_name(part)]
        for node in nodes
    ]
    common: list[str] = []
    for components in zip(*paths):
        if len(set(components)) != 1:
            break
        common.append(components[0])
    return " / ".join(common)


def collapse_hierarchy_nodes(nodes: Iterable[TariffNode]) -> list[TariffNode]:
    """Deduplicate synthetic hierarchy nodes while preserving source order."""

    result: list[TariffNode] = []
    positions: dict[tuple[str, str], int] = {}
    candidates: dict[tuple[str, str], list[TariffNode]] = {}
    deduplicated_kinds = {"section", "chapter", "subheading"}
    for node in nodes:
        if node.kind not in deduplicated_kinds:
            result.append(node)
            continue
        key = (node.kind, node.code)
        candidates.setdefault(key, []).append(node)
        existing_index = positions.get(key)
        if existing_index is None:
            positions[key] = len(result)
            result.append(node)
            continue
        if _hierarchy_name_score(node) > _hierarchy_name_score(result[existing_index]):
            result[existing_index] = node
    for key, grouped_nodes in candidates.items():
        if key[0] != "subheading" or len(grouped_nodes) < 2:
            continue
        common_name = _common_hierarchy_name(grouped_nodes)
        if not common_name:
            continue
        existing_index = positions[key]
        existing = result[existing_index]
        result[existing_index] = TariffNode(
            code=existing.code,
            name=common_name,
            level=existing.level,
            parent_code=existing.parent_code,
            page=existing.page,
            kind=existing.kind,
        )
    # When a four-digit heading has only one HS6 child and that child is the
    # conventional xx00 code, the HS6 scope is identical to the heading.
    # Inferring its label from domestic eight-digit rows can otherwise pick a
    # single subdivision such as "纯氯化钠" for the whole salt heading.
    heading_names = {
        node.code: node.name for node in result if node.kind == "heading"
    }
    subheading_positions: dict[str, list[int]] = {}
    for index, node in enumerate(result):
        if node.kind == "subheading":
            subheading_positions.setdefault(node.code[:4], []).append(index)
    for heading_code, positions_for_heading in subheading_positions.items():
        if (
            len(positions_for_heading) != 1
            or heading_code not in heading_names
        ):
            continue
        index = positions_for_heading[0]
        existing = result[index]
        if existing.code != f"{heading_code}00":
            continue
        result[index] = TariffNode(
            code=existing.code,
            name=heading_names[heading_code],
            level=existing.level,
            parent_code=existing.parent_code,
            page=existing.page,
            kind=existing.kind,
        )
    return result


def attach_parent_codes(nodes: Iterable[TariffNode]) -> list[TariffNode]:
    """Link section, chapter, heading, subheading and leaf tariff nodes."""

    source = list(nodes)
    known = {node.code for node in source}
    result: list[TariffNode] = []
    active_section: str | None = None
    for node in source:
        parent: str | None = None
        if node.kind == "section":
            active_section = node.code
        elif node.kind == "chapter":
            parent = active_section
        else:
            digits = normalize_code(node.code)
            for length in (6, 4, 2):
                if length >= len(digits):
                    continue
                candidate = digits[:length]
                if candidate in known:
                    parent = candidate
                    break
        result.append(
            TariffNode(
                code=node.code,
                name=node.name,
                level=node.level,
                parent_code=parent,
                page=node.page,
                kind=node.kind,
            )
        )
    return result


def validate_nodes(nodes: Iterable[TariffNode]) -> list[str]:
    source = list(nodes)
    issues: list[str] = []
    seen: set[str] = set()
    known = {node.code: node for node in source}
    hierarchy_present = any(node.kind in {"section", "chapter"} for node in source)
    expected_levels = {
        "section": 0,
        "chapter": 1,
        "heading": 2,
        "subheading": 3,
        "sku": 4,
    }
    for node in source:
        if not node.code or not node.name:
            issues.append("存在缺少编码或名称的目录节点")
        if node.code in seen:
            issues.append(f"重复编码：{node.code}")
        seen.add(node.code)
        valid_section_code = node.kind == "section" and bool(re.fullmatch(r"S\d{2}", node.code))
        valid_numeric_code = node.code.isdigit() and len(node.code) in {2, 4, 6, 8, 10}
        if not valid_section_code and not valid_numeric_code:
            issues.append(f"编码长度异常：{node.code}")
        expected_level = expected_levels.get(node.kind)
        if expected_level is None or node.level != expected_level:
            issues.append(f"层级类型异常：{node.code} ({node.kind}/{node.level})")
        if hierarchy_present and node.kind != "section":
            if not node.parent_code or node.parent_code not in known:
                issues.append(f"缺少父级：{node.code}")
            elif known[node.parent_code].level != node.level - 1:
                issues.append(f"父级层级异常：{node.code} -> {node.parent_code}")
    return issues


class _MuPdfPage:
    def __init__(self, page: Any) -> None:
        self._page = page

    def extract_words(self) -> list[tuple[Any, ...]]:
        return self._page.get_text("words")

    def extract_text(self) -> str:
        return self._page.get_text("text")


class _MuPdfReader:
    """Coordinate-aware reader backed by PyMuPDF."""

    def __init__(self, path: Path) -> None:
        try:
            import pymupdf
        except ImportError:
            import fitz as pymupdf  # type: ignore[no-redef]
        self._document = pymupdf.open(str(path))
        self.pages = [_MuPdfPage(self._document[index]) for index in range(len(self._document))]
        self.backend = "pymupdf-coordinate-columns"

    def close(self) -> None:
        self._document.close()


class TariffExtractionJobManager:
    """Thread-safe, single-active-job manager for the visual progress page."""

    def __init__(
        self,
        runtime_root: Path | None = None,
        *,
        downloader: Callable[..., Any] | None = None,
        page_reader_factory: Callable[[Path], Any] | None = None,
    ) -> None:
        self.runtime_root = Path(runtime_root or Path(".runtime") / "tariff-extraction")
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.downloader = downloader
        self.page_reader_factory = page_reader_factory
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._cancel_events: dict[str, threading.Event] = {}

    def start(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        mode = str(payload.get("mode") or "demo").strip().lower()
        if mode not in {"demo", "full"}:
            raise ValueError("mode 只能是 demo 或 full")
        if mode == "full" and not bool(payload.get("confirmed")):
            raise ValueError("全量模式需要明确确认后才会下载并解析 PDF")
        source_url = validate_source_url(payload.get("source_url") or TARIFF_SOURCE_URL)
        source_file = self._validated_source_file(payload.get("source_file"))
        with self._lock:
            active = next(
                (
                    job
                    for job in self._jobs.values()
                    if job["status"] in {"queued", "running"}
                ),
                None,
            )
            if active:
                raise ValueError(f"已有任务正在运行：{active['job_id']}")
            job_id = uuid4().hex
            now = time.time()
            job = {
                "job_id": job_id,
                "status": "queued",
                "stage": "queued",
                "stage_label": STAGE_LABELS["queued"],
                "overall_progress": 0.0,
                "stage_progress": 0.0,
                "message": "任务已创建，等待后台线程启动",
                "mode": mode,
                "source_url": source_url,
                "source_version": TARIFF_SOURCE_VERSION,
                "created_at": _utc_now(),
                "started_at": None,
                "updated_at": _utc_now(),
                "elapsed_seconds": 0.0,
                "eta_seconds": None,
                "page_count": TARIFF_EXPECTED_PAGES if mode == "demo" else None,
                "pages_processed": 0,
                "downloaded_bytes": 0,
                "total_bytes": TARIFF_EXPECTED_BYTES if mode == "demo" else None,
                "nodes_found": 0,
                "leaf_codes_found": 0,
                "issues_found": 0,
                "pages_per_second": 0.0,
                "recent_nodes": [],
                "recent_logs": ["任务已排队"],
                "output_files": [],
                "sha256": None,
                "error": None,
                "_created_epoch": now,
            }
            self._jobs[job_id] = job
            cancel_event = threading.Event()
            self._cancel_events[job_id] = cancel_event
        thread = threading.Thread(
            target=self._run,
            args=(job_id, mode, source_url, source_file, cancel_event),
            name=f"tariff-extraction-{job_id[:8]}",
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
            if job["status"] not in {"queued", "running"}:
                return self.snapshot(job_id)
            self._cancel_events[job_id].set()
            job["message"] = "已请求停止，正在安全收尾"
            job["recent_logs"].append("收到停止请求；不会写入 ERPNext")
            job["updated_at"] = _utc_now()
        return self.snapshot(job_id)

    def _update(self, job_id: str, *, stage: str | None = None, **changes: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if stage:
                job["stage"] = stage
                job["stage_label"] = STAGE_LABELS.get(stage, stage)
            job.update(changes)
            if stage:
                job["overall_progress"] = max(
                    float(job.get("overall_progress") or 0),
                    STAGE_END.get(stage, 0.0),
                )
            started = job.get("_started_epoch")
            if started:
                elapsed = max(0.0, time.time() - started)
                job["elapsed_seconds"] = round(elapsed, 1)
                progress = float(job.get("overall_progress") or 0)
                if progress > 0.03 and progress < 1:
                    job["eta_seconds"] = round(elapsed * (1 - progress) / progress, 1)
            job["updated_at"] = _utc_now()

    def _log(self, job_id: str, message: str) -> None:
        with self._lock:
            logs = self._jobs[job_id]["recent_logs"]
            logs.append(str(message))
            del logs[:-8]
        self._update(job_id, message=message)

    def _run(
        self,
        job_id: str,
        mode: str,
        source_url: str,
        source_file: Path | None,
        cancel_event: threading.Event,
    ) -> None:
        self._update(job_id, status="running", stage="queued", started_at=_utc_now())
        with self._lock:
            self._jobs[job_id]["_started_epoch"] = time.time()
        try:
            if mode == "demo":
                self._run_demo(job_id, cancel_event)
            else:
                self._run_full(job_id, source_url, source_file, cancel_event)
        except _Cancelled:
            self._update(
                job_id,
                status="cancelled",
                eta_seconds=None,
                message="任务已停止；未写入 ERPNext",
            )
            self._log(job_id, "任务安全停止")
        except Exception as exc:  # pragma: no cover - exercised through API boundary
            self._update(
                job_id,
                status="failed",
                message=str(exc),
                error=str(exc),
                eta_seconds=None,
            )
            self._log(job_id, f"任务失败：{exc}")

    def _check_cancel(self, event: threading.Event) -> None:
        if event.is_set():
            raise _Cancelled()

    def _run_demo(self, job_id: str, cancel_event: threading.Event) -> None:
        samples = [
            ("73181510", "抗拉强度在 800 MPa 及以上的其他螺钉及螺栓", 4, "sku"),
            ("73181600", "螺母", 4, "sku"),
            ("73182200", "其他垫圈", 4, "sku"),
            ("73181000", "铁或钢制无螺纹制品", 3, "heading"),
        ]
        self._log(job_id, "演示模式：使用固定样本，不下载源文件")
        for stage, message, count in (
            ("inspecting", "读取 PDF 元数据（演示）", 8),
            ("extracting", "按页提取税则号列与货品名称（演示）", 24),
            ("normalizing", "整理章节、品目、子目和 8 位税号（演示）", 12),
            ("validating", "检查编码长度、重复项和层级关系（演示）", 10),
            ("writing", "生成 JSONL 候选包与校验报告（演示）", 6),
        ):
            self._update(job_id, stage=stage, message=message)
            for index in range(count):
                self._check_cancel(cancel_event)
                progress = (index + 1) / count
                overall = (STAGE_END[stage] - STAGE_END.get(stage, 0) + STAGE_END[stage])
                if stage == "inspecting":
                    overall = 0.13 + progress * 0.07
                elif stage == "extracting":
                    overall = 0.20 + progress * 0.52
                elif stage == "normalizing":
                    overall = 0.72 + progress * 0.12
                elif stage == "validating":
                    overall = 0.84 + progress * 0.10
                elif stage == "writing":
                    overall = 0.94 + progress * 0.05
                changes: dict[str, Any] = {
                    "stage_progress": round(progress * 100, 1),
                    "overall_progress": round(overall, 4),
                }
                if stage == "extracting":
                    changes["pages_processed"] = min(
                        TARIFF_EXPECTED_PAGES,
                        int((index + 1) * TARIFF_EXPECTED_PAGES / count),
                    )
                self._update(job_id, **changes)
                time.sleep(0.035)
        output_dir = self.runtime_root / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "manifest.json").write_text(
            json.dumps({"mode": "demo", "source_version": TARIFF_SOURCE_VERSION}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._finish_nodes(job_id, [TariffNode(code, name, level, page=42, kind=kind) for code, name, level, kind in samples])
        self._update(
            job_id,
            status="completed",
            stage="completed",
            stage_progress=100,
            overall_progress=1.0,
            eta_seconds=0,
            message="演示候选发布包已生成；未下载文件，也未写入 ERPNext",
            output_files=[str(output_dir / "manifest.json")],
        )

    def _run_full(
        self,
        job_id: str,
        source_url: str,
        source_file: Path | None,
        cancel_event: threading.Event,
    ) -> None:
        pdf_path = (
            self._reuse_source_file(job_id, source_file)
            if source_file is not None
            else self._download(job_id, source_url, cancel_event)
        )
        self._check_cancel(cancel_event)
        self._update(job_id, stage="inspecting", stage_progress=0, message="检查 PDF 页数、加密状态和文本层")
        reader = self._make_reader(pdf_path)
        parser_backend = getattr(reader, "backend", "pypdf-text-fallback")
        page_count = len(reader.pages)
        self._update(job_id, page_count=page_count, stage_progress=100, message=f"已确认 {page_count} 页")
        self._update(job_id, stage="extracting", stage_progress=0, message="逐页提取税则号列与货品名称")
        nodes: list[TariffNode] = []
        hierarchy_state = TariffHierarchyState()
        started = time.time()
        for page_number, page in enumerate(reader.pages, start=1):
            self._check_cancel(cancel_event)
            words = page.extract_words() if hasattr(page, "extract_words") else None
            page_nodes = (
                parse_tariff_page_words(
                    words,
                    page_number,
                    include_hierarchy=True,
                    hierarchy_state=hierarchy_state,
                )
                if words
                else parse_tariff_page_text(page.extract_text() or "", page_number)
            )
            nodes.extend(page_nodes)
            self._update(
                job_id,
                pages_processed=page_number,
                stage_progress=round(page_number / max(1, page_count) * 100, 1),
                overall_progress=round(0.20 + page_number / max(1, page_count) * 0.52, 4),
                nodes_found=len(nodes),
                leaf_codes_found=sum(node.kind == "sku" for node in nodes),
                pages_per_second=round(page_number / max(0.001, time.time() - started), 2),
                recent_nodes=[node.as_dict() for node in nodes[-8:]],
                message=f"已处理第 {page_number}/{page_count} 页，发现 {len(nodes)} 个候选节点",
            )
        if hasattr(reader, "close"):
            reader.close()
        self._update(job_id, stage="normalizing", stage_progress=0, message="整理类、章、4 位品目、6 位子目和 8 位税号")
        nodes = collapse_hierarchy_nodes(nodes)
        nodes = attach_parent_codes(nodes)
        self._update(job_id, stage_progress=100, overall_progress=0.84)
        self._update(job_id, stage="validating", stage_progress=0, message="校验编码重复项与层级关系")
        self._finish_nodes(job_id, nodes)
        self._update(job_id, stage_progress=100, overall_progress=0.94)
        self._update(job_id, stage="writing", stage_progress=0, message="写入候选发布包，不触碰 ERPNext")
        self._write_outputs(job_id, nodes, pdf_path, parser_backend=parser_backend)

    def _download(self, job_id: str, source_url: str, cancel_event: threading.Event) -> Path:
        self._update(job_id, stage="downloading", stage_progress=0, message="从财政部公开地址下载 2026 税则 PDF")
        output = self.runtime_root / job_id / "tariff-2026.pdf"
        output.parent.mkdir(parents=True, exist_ok=True)
        response = self.downloader(source_url) if self.downloader else requests.get(
            source_url, stream=True, timeout=(15, 120)
        )
        response.raise_for_status()
        total = int(response.headers.get("Content-Length") or 0) or None
        self._update(job_id, total_bytes=total)
        digest = hashlib.sha256()
        downloaded = 0
        with output.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                self._check_cancel(cancel_event)
                if not chunk:
                    continue
                handle.write(chunk)
                digest.update(chunk)
                downloaded += len(chunk)
                progress = downloaded / total * 100 if total else 0
                self._update(
                    job_id,
                    downloaded_bytes=downloaded,
                    stage_progress=round(progress, 1),
                    overall_progress=round(0.03 + min(1, progress / 100) * 0.10, 4),
                    message=f"已下载 {downloaded / 1024 / 1024:.1f} MB",
                )
        self._update(job_id, sha256=digest.hexdigest(), stage_progress=100, message="下载完成，准备检查 PDF")
        return output

    def _validated_source_file(self, value: Any) -> Path | None:
        if not value:
            return None
        candidate = Path(str(value)).expanduser().resolve()
        root = self.runtime_root.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("source_file 必须位于税则任务 runtime 目录内") from exc
        if not candidate.is_file():
            raise ValueError("source_file 不存在或不是文件")
        return candidate

    def _reuse_source_file(self, job_id: str, source_file: Path) -> Path:
        size = source_file.stat().st_size
        digest = hashlib.sha256()
        with source_file.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        self._update(
            job_id,
            stage="downloading",
            stage_progress=100,
            overall_progress=0.13,
            downloaded_bytes=size,
            total_bytes=size,
            sha256=digest.hexdigest(),
            message="复用已下载 PDF，跳过重复网络下载",
        )
        return source_file

    def _make_reader(self, path: Path) -> Any:
        if self.page_reader_factory:
            return self.page_reader_factory(path)
        try:
            return _MuPdfReader(path)
        except ImportError:
            pass
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - depends on local env
            raise RuntimeError("全量模式需要安装 pypdf：python -m pip install pypdf") from exc
        return PdfReader(str(path), strict=False)

    def _finish_nodes(self, job_id: str, nodes: list[TariffNode]) -> None:
        issues = validate_nodes(nodes)
        self._update(
            job_id,
            nodes_found=len(nodes),
            leaf_codes_found=sum(node.kind == "sku" for node in nodes),
            issues_found=len(issues),
            recent_nodes=[node.as_dict() for node in nodes[-8:]],
        )
        if issues:
            self._log(job_id, f"校验发现 {len(issues)} 个待复核项；候选包仍保持只读")

    def _write_outputs(
        self,
        job_id: str,
        nodes: list[TariffNode],
        pdf_path: Path,
        *,
        parser_backend: str = "unknown",
    ) -> None:
        output_dir = self.runtime_root / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        nodes_path = output_dir / "tariff-nodes.jsonl"
        with nodes_path.open("w", encoding="utf-8") as handle:
            for node in nodes:
                handle.write(json.dumps(node.as_dict(), ensure_ascii=False) + "\n")
        manifest_path = output_dir / "manifest.json"
        node_counts_by_kind: dict[str, int] = {}
        level_counts: dict[str, int] = {}
        for node in nodes:
            node_counts_by_kind[node.kind] = node_counts_by_kind.get(node.kind, 0) + 1
            level_key = str(node.level)
            level_counts[level_key] = level_counts.get(level_key, 0) + 1
        parent_missing_count = sum(
            node.kind != "section" and not node.parent_code for node in nodes
        )
        hierarchy_complete = (
            all(node_counts_by_kind.get(kind, 0) > 0 for kind in ("section", "chapter", "heading", "subheading", "sku"))
            and parent_missing_count == 0
        )
        manifest_path.write_text(
            json.dumps(
                {
                    "source_url": TARIFF_SOURCE_URL,
                    "source_version": TARIFF_SOURCE_VERSION,
                    "source_file": str(pdf_path),
                    "parser_backend": parser_backend,
                    "nodes": len(nodes),
                    "node_counts_by_kind": node_counts_by_kind,
                    "level_counts": level_counts,
                    "leaf_codes": node_counts_by_kind.get("sku", 0),
                    "parent_missing_count": parent_missing_count,
                    "hierarchy_complete": hierarchy_complete,
                    "generated_at": _utc_now(),
                    "erpnext_written": False,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self._update(
            job_id,
            status="completed",
            stage="completed",
            stage_progress=100,
            overall_progress=1.0,
            eta_seconds=0,
            message="候选发布包已生成；未写入 ERPNext",
            output_files=[str(nodes_path), str(manifest_path)],
        )


class _Cancelled(Exception):
    pass


__all__ = [
    "STAGES",
    "STAGE_LABELS",
    "TARIFF_EXPECTED_BYTES",
    "TARIFF_EXPECTED_PAGES",
    "TARIFF_SOURCE_URL",
    "TARIFF_SOURCE_VERSION",
    "TariffExtractionJobManager",
    "TariffHierarchyState",
    "TariffNode",
    "attach_parent_codes",
    "collapse_hierarchy_nodes",
    "normalize_code",
    "normalize_name",
    "parse_tariff_page_words",
    "parse_tariff_scope_nodes",
    "parse_tariff_page_text",
    "validate_nodes",
    "validate_source_url",
]
