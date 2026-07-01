from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from contract_agent.parser.parsed.markdown_cleaner import _is_page_separator


@dataclass(frozen=True)
class MarkdownPageEvidence:
    line_page_numbers: list[int | None]
    marker_count: int = 0
    max_page_no: int = 0
    sources: list[str] = field(default_factory=list)
    table_page_numbers: dict[int, int] = field(default_factory=dict)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "marker_count": self.marker_count,
            "max_page_no": self.max_page_no,
            "sources": list(self.sources),
            "table_page_numbers": {
                str(index): page_no for index, page_no in self.table_page_numbers.items()
            },
        }


@dataclass(frozen=True)
class _ExplicitPageMarker:
    index: int
    page_no: int
    total_pages: int | None = None


_CHINESE_PAGE_NUMBER_CHARS = "0-9零一二两三四五六七八九十百"
_ENGLISH_PAGE_RE = re.compile(r"^page\s+(\d{1,4})(?:\s+of\s+(\d{1,4}))?$", re.IGNORECASE)
_PAGE_FRACTION_RE = re.compile(r"^(\d{1,4})\s*/\s*(\d{1,4})$")
_CHINESE_PAGE_RE = re.compile(
    rf"^第\s*([{_CHINESE_PAGE_NUMBER_CHARS}]+)\s*页"
    rf"(?:\s*[，,、]?\s*共\s*([{_CHINESE_PAGE_NUMBER_CHARS}]+)\s*页)?$"
)
_CHINESE_TOTAL_FIRST_RE = re.compile(
    rf"^共\s*([{_CHINESE_PAGE_NUMBER_CHARS}]+)\s*页\s*[，,、]?\s*"
    rf"第\s*([{_CHINESE_PAGE_NUMBER_CHARS}]+)\s*页$"
)
_NUMERIC_FOOTER_RE = re.compile(r"^[\-\s]*(\d{1,4})[\-\s]*$")
_CHINESE_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def resolve_page_evidence(
    lines: list[str],
    conversion_metadata: dict[str, Any] | None = None,
) -> MarkdownPageEvidence:
    explicit_markers = _explicit_page_markers(lines)
    if explicit_markers:
        return _resolve_from_explicit_markers(lines, explicit_markers)

    numeric_markers = _numeric_footer_markers(lines)
    if numeric_markers:
        return _resolve_from_numeric_footers(lines, numeric_markers)

    table_page_numbers = _metadata_table_page_numbers(conversion_metadata)
    return MarkdownPageEvidence(
        line_page_numbers=[None for _ in lines],
        marker_count=len(table_page_numbers),
        max_page_no=max(table_page_numbers.values(), default=0),
        sources=["conversion_metadata"] if table_page_numbers else [],
        table_page_numbers=table_page_numbers,
    )


def page_numbers_for_cleaned_lines(
    original_lines: list[str],
    cleaned_lines: list[str],
    evidence: MarkdownPageEvidence,
) -> list[int | None]:
    page_numbers: list[int | None] = []
    original_index = 0
    for cleaned_line in cleaned_lines:
        target = cleaned_line.rstrip()
        while original_index < len(original_lines):
            if original_lines[original_index].rstrip() == target:
                page_numbers.append(_page_at(evidence, original_index))
                original_index += 1
                break
            original_index += 1
        else:
            page_numbers.append(None)
    return page_numbers


def _resolve_from_explicit_markers(
    lines: list[str],
    markers: list[_ExplicitPageMarker],
) -> MarkdownPageEvidence:
    if not _valid_explicit_markers(markers):
        return _empty_page_evidence(lines)

    if _uses_footer_style_markers(lines, markers):
        pages = _page_numbers_from_explicit_footers(lines, markers)
    else:
        pages = _page_numbers_from_explicit_headers(lines, markers)

    return MarkdownPageEvidence(
        line_page_numbers=pages,
        marker_count=len(markers),
        max_page_no=max(marker.page_no for marker in markers),
        sources=["page_marker"],
    )


def _resolve_from_numeric_footers(
    lines: list[str],
    markers: list[tuple[int, int]],
) -> MarkdownPageEvidence:
    pages: list[int | None] = [None for _ in lines]
    segment_start = 0
    for marker_index, page_no in markers:
        segment_end = marker_index
        while segment_end + 1 < len(lines) and _is_numeric_footer_trailing_furniture(
            lines[segment_end + 1]
        ):
            segment_end += 1
        for index in range(segment_start, segment_end + 1):
            pages[index] = page_no
        segment_start = segment_end + 1
    return MarkdownPageEvidence(
        line_page_numbers=pages,
        marker_count=len(markers),
        max_page_no=max(page_no for _, page_no in markers),
        sources=["numeric_footer"],
    )


def _explicit_page_markers(lines: list[str]) -> list[_ExplicitPageMarker]:
    markers: list[_ExplicitPageMarker] = []
    for index, line in enumerate(lines):
        marker = _explicit_page_marker(index, line)
        if marker is not None:
            markers.append(marker)
    return markers


def _explicit_page_no(line: str) -> int | None:
    marker = _explicit_page_marker(0, line)
    return marker.page_no if marker is not None else None


def _explicit_page_marker(index: int, line: str) -> _ExplicitPageMarker | None:
    stripped = line.strip()
    match = _ENGLISH_PAGE_RE.match(stripped) or _PAGE_FRACTION_RE.match(stripped)
    if match is not None:
        return _marker_from_values(index, match.group(1), match.group(2))

    match = _CHINESE_PAGE_RE.match(stripped)
    if match is not None:
        return _marker_from_values(index, match.group(1), match.group(2))

    match = _CHINESE_TOTAL_FIRST_RE.match(stripped)
    if match is not None:
        return _marker_from_values(index, match.group(2), match.group(1))

    return None


def _marker_from_values(
    index: int,
    page_value: str,
    total_value: str | None,
) -> _ExplicitPageMarker | None:
    page_no = _positive_page_no(page_value)
    if page_no is None:
        return None
    total_pages = _positive_page_no(total_value) if total_value is not None else None
    if total_value is not None and total_pages is None:
        return None
    return _ExplicitPageMarker(index=index, page_no=page_no, total_pages=total_pages)


def _valid_explicit_markers(markers: list[_ExplicitPageMarker]) -> bool:
    previous_page = 0
    totals = {marker.total_pages for marker in markers if marker.total_pages is not None}
    if len(totals) > 1:
        return False
    total_pages = next(iter(totals), None)
    for marker in markers:
        if marker.page_no < previous_page:
            return False
        if total_pages is not None and marker.page_no > total_pages:
            return False
        previous_page = marker.page_no
    return True


def _uses_footer_style_markers(lines: list[str], markers: list[_ExplicitPageMarker]) -> bool:
    segment_start = 0
    for marker in markers:
        if _has_body_content(lines, segment_start, marker.index) and (
            marker.index == markers[0].index
            or _marker_followed_by_footer_boundary(lines, marker.index)
        ):
            return True
        segment_start = marker.index + 1
    return False


def _page_numbers_from_explicit_headers(
    lines: list[str],
    markers: list[_ExplicitPageMarker],
) -> list[int | None]:
    pages: list[int | None] = []
    marker_by_index = {marker.index: marker.page_no for marker in markers}
    current_page: int | None = None
    for index in range(len(lines)):
        if index in marker_by_index:
            current_page = marker_by_index[index]
        pages.append(current_page)
    return pages


def _page_numbers_from_explicit_footers(
    lines: list[str],
    markers: list[_ExplicitPageMarker],
) -> list[int | None]:
    pages: list[int | None] = [None for _ in lines]
    segment_start = 0
    for marker in markers:
        segment_end = marker.index
        while segment_end + 1 < len(lines) and _is_numeric_footer_trailing_furniture(
            lines[segment_end + 1]
        ):
            segment_end += 1
        for index in range(segment_start, segment_end + 1):
            pages[index] = marker.page_no
        segment_start = segment_end + 1
    return pages


def _marker_followed_by_footer_boundary(lines: list[str], index: int) -> bool:
    next_line = _nearest_non_empty_line(lines, index, step=1)
    return next_line is None or _is_page_separator(next_line)


def _has_body_content(lines: list[str], start: int, end: int) -> bool:
    return any(
        line.strip() and not _is_page_separator(line) and _explicit_page_no(line) is None
        for line in lines[start:end]
    )


def _empty_page_evidence(lines: list[str]) -> MarkdownPageEvidence:
    return MarkdownPageEvidence(line_page_numbers=[None for _ in lines])


def _numeric_footer_markers(lines: list[str]) -> list[tuple[int, int]]:
    candidates: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        match = _NUMERIC_FOOTER_RE.match(line.strip())
        if match is None:
            continue
        page_no = _positive_page_no(match.group(1))
        if page_no is None:
            continue
        candidates.append((index, page_no))
    if len(candidates) < 2:
        return []

    runs: list[list[tuple[int, int]]] = []
    run: list[tuple[int, int]] = [candidates[0]]
    for candidate in candidates[1:]:
        previous_index, previous_page = run[-1]
        index, page_no = candidate
        if (
            page_no == previous_page + 1
            and _has_numeric_footer_boundary_context(lines, previous_index)
            and _has_numeric_footer_boundary_context(lines, index)
        ):
            run.append(candidate)
            continue
        if len(run) >= 2:
            runs.append(run)
        run = [candidate]
    if len(run) >= 2:
        runs.append(run)
    return [marker for run in runs for marker in run]


def _has_numeric_footer_boundary_context(lines: list[str], index: int) -> bool:
    previous_line = _nearest_non_empty_line(lines, index, step=-1)
    next_line = _nearest_non_empty_line(lines, index, step=1)
    return any(
        _is_page_separator(line) or _explicit_page_no(line) is not None
        for line in (previous_line, next_line)
        if line is not None
    )


def _nearest_non_empty_line(lines: list[str], index: int, *, step: int) -> str | None:
    cursor = index + step
    while 0 <= cursor < len(lines):
        if lines[cursor].strip():
            return lines[cursor].strip()
        cursor += step
    return None


def _is_numeric_footer_trailing_furniture(line: str) -> bool:
    stripped = line.strip()
    return not stripped or _is_page_separator(stripped)


def _positive_page_no(value: str) -> int | None:
    page_no = _int_value(value) if value.isdigit() else _chinese_number(value)
    if page_no is None or page_no <= 0:
        return None
    return page_no


def _chinese_number(value: str) -> int | None:
    if not value:
        return None
    if all(char in _CHINESE_DIGITS for char in value):
        result = 0
        for char in value:
            result = result * 10 + _CHINESE_DIGITS[char]
        return result
    if "百" in value:
        left, _, right = value.partition("百")
        hundred = _CHINESE_DIGITS.get(left, 1) if left else 1
        tail = _chinese_number(right) or 0
        return hundred * 100 + tail
    if "十" in value:
        left, _, right = value.partition("十")
        ten = _CHINESE_DIGITS.get(left, 1) if left else 1
        tail = _CHINESE_DIGITS.get(right, 0) if right else 0
        return ten * 10 + tail
    return _CHINESE_DIGITS.get(value)


def table_page_no(evidence: MarkdownPageEvidence, table_index: int) -> int | None:
    return evidence.table_page_numbers.get(table_index)


def _metadata_table_page_numbers(conversion_metadata: dict[str, Any] | None) -> dict[int, int]:
    if not conversion_metadata:
        return {}
    table_pages: dict[int, int] = {}
    raw_tables = conversion_metadata.get("docling_tables")
    if isinstance(raw_tables, list):
        for fallback_index, item in enumerate(raw_tables):
            if isinstance(item, dict):
                table_index = _int_value(item.get("index"))
                page_no = _int_value(item.get("page"))
                if table_index is None:
                    table_index = fallback_index
                if table_index >= 0 and page_no is not None and page_no > 0:
                    table_pages[table_index] = page_no
    return table_pages


def _page_at(evidence: MarkdownPageEvidence, index: int) -> int | None:
    if index >= len(evidence.line_page_numbers):
        return None
    return evidence.line_page_numbers[index]


def _int_value(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
