from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from contract_agent.parser.parsed.markdown_table_row_parser import split_pipe_row


_PAGE_NUMBER_PATTERNS = [
    re.compile(r"^第\s*[\d一二三四五六七八九十百千]+\s*页(?:\s*[，,]?\s*共\s*\d+\s*页)?$"),
    re.compile(r"^共\s*\d+\s*页\s*第\s*\d+\s*页$"),
    re.compile(r"^page\s+\d+\s+of\s+\d+$", re.IGNORECASE),
    re.compile(r"^\d+\s*/\s*\d+$"),
]
_NUMERIC_PAGE_FOOTER_PATTERN = re.compile(r"^[-–—]?\s*(\d{1,4})\s*[-–—]?$")
_PAGE_SEPARATOR_PATTERN = re.compile(r"^[-_=]{3,}$")
_KNOWN_FOOTER_VALUES = {
    "confidential",
}
_MAX_TABLE_GAP_NOISE_LINES = 3
_MAX_TABLE_GAP_NOISE_CHARS = 16
_STRUCTURAL_SHORT_TEXT = {
    "note",
    "notes",
    "remark",
    "remarks",
    "subtotal",
    "total",
    "说明",
    "备注",
    "注",
    "附件",
    "附表",
    "合计",
    "小计",
    "甲方",
    "乙方",
    "丙方",
    "出租方",
    "承租方",
}


@dataclass(frozen=True)
class CleanedMarkdown:
    markdown_content: str
    removed_lines: int = 0
    merged_tables: int = 0


@dataclass(frozen=True)
class _TableGap:
    next_index: int
    removed_noise_lines: int = 0

    @property
    def has_noise(self) -> bool:
        return self.removed_noise_lines > 0


class MarkdownCleaner:
    def clean(
        self,
        markdown: str,
        conversion_metadata: dict[str, Any] | None = None,
    ) -> CleanedMarkdown:
        lines = markdown.splitlines()
        filtered_lines, removed_lines = self.remove_page_furniture(lines)
        merged_lines, merged_tables, removed_table_noise_lines = _merge_split_tables(
            filtered_lines,
            table_layouts=_table_layouts(conversion_metadata),
        )
        removed_lines += removed_table_noise_lines
        if removed_lines == 0 and merged_tables == 0:
            return CleanedMarkdown(markdown_content=markdown)
        return CleanedMarkdown(
            markdown_content="\n".join(merged_lines).strip(),
            removed_lines=removed_lines,
            merged_tables=merged_tables,
        )

    def remove_page_furniture(self, lines: list[str]) -> tuple[list[str], int]:
        page_number_indexes = {
            index for index, line in enumerate(lines) if self.is_page_number(line)
        }
        page_number_indexes.update(_numeric_page_footer_indexes(lines))
        duplicate_furniture_indexes = _duplicate_furniture_indexes(lines, page_number_indexes)

        cleaned: list[str] = []
        removed = 0
        for index, line in enumerate(lines):
            if (
                index in page_number_indexes
                or index in duplicate_furniture_indexes
                or self.is_footer(line)
                or self.is_page_separator(line)
            ):
                removed += 1
                continue
            cleaned.append(line.rstrip())
        return cleaned, removed

    def remove_page_number(self, lines: list[str]) -> tuple[list[str], int]:
        return self._remove_matching(lines, self.is_page_number)

    def remove_header(self, lines: list[str]) -> tuple[list[str], int]:
        page_number_indexes = {
            index for index, line in enumerate(lines) if self.is_page_number(line)
        }
        duplicate_header_indexes = _duplicate_furniture_indexes(lines, page_number_indexes)
        return self._remove_indexes(lines, duplicate_header_indexes)

    def remove_footer(self, lines: list[str]) -> tuple[list[str], int]:
        return self._remove_matching(lines, self.is_footer)

    def is_page_number(self, line: str) -> bool:
        return _is_page_number(line)

    def is_footer(self, line: str) -> bool:
        return _is_known_footer(line)

    def is_page_separator(self, line: str) -> bool:
        return _is_page_separator(line)

    def _remove_matching(
        self,
        lines: list[str],
        predicate: object,
    ) -> tuple[list[str], int]:
        cleaned: list[str] = []
        removed = 0
        for line in lines:
            if callable(predicate) and predicate(line):
                removed += 1
                continue
            cleaned.append(line)
        return cleaned, removed

    def _remove_indexes(self, lines: list[str], indexes: set[int]) -> tuple[list[str], int]:
        cleaned = [line for index, line in enumerate(lines) if index not in indexes]
        return cleaned, len(lines) - len(cleaned)


def clean_markdown(
    markdown: str,
    conversion_metadata: dict[str, Any] | None = None,
) -> CleanedMarkdown:
    return MarkdownCleaner().clean(markdown, conversion_metadata=conversion_metadata)


def _duplicate_furniture_indexes(lines: list[str], page_number_indexes: set[int]) -> set[int]:
    candidates: dict[str, list[int]] = {}
    for index in page_number_indexes:
        for neighbor in (_previous_non_empty(lines, index), _next_non_empty(lines, index)):
            if neighbor is None:
                continue
            value = _normalized_furniture_line(lines[neighbor])
            if (
                not value
                or _is_page_number(lines[neighbor])
                or _is_known_footer(lines[neighbor])
                or _looks_like_body_title(lines[neighbor])
            ):
                continue
            candidates.setdefault(value, []).append(neighbor)

    duplicate_indexes: set[int] = set()
    for indexes in candidates.values():
        unique_indexes = sorted(set(indexes))
        if len(unique_indexes) <= 1:
            continue
        duplicate_indexes.update(unique_indexes[1:])
    return duplicate_indexes


def _previous_non_empty(lines: list[str], index: int) -> int | None:
    cursor = index - 1
    while cursor >= 0:
        if lines[cursor].strip():
            return cursor
        cursor -= 1
    return None


def _next_non_empty(lines: list[str], index: int) -> int | None:
    cursor = index + 1
    while cursor < len(lines):
        if lines[cursor].strip():
            return cursor
        cursor += 1
    return None


def _normalized_furniture_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip()).lower()


def _is_page_number(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return any(pattern.match(stripped) for pattern in _PAGE_NUMBER_PATTERNS)


def _numeric_page_footer_indexes(lines: list[str]) -> set[int]:
    candidates: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        match = _NUMERIC_PAGE_FOOTER_PATTERN.match(line.strip())
        if match is None:
            continue
        page_no = int(match.group(1))
        if page_no <= 0:
            continue
        candidates.append((index, page_no))

    if len(candidates) < 2:
        return set()

    result: set[int] = set()
    run: list[tuple[int, int]] = [candidates[0]]
    for candidate in candidates[1:]:
        previous_index, previous_page_no = run[-1]
        index, page_no = candidate
        if (
            page_no == previous_page_no + 1
            and _looks_like_page_break_gap(lines, previous_index, index)
            and _has_numeric_footer_boundary_context(lines, previous_index)
            and _has_numeric_footer_boundary_context(lines, index)
        ):
            run.append(candidate)
            continue
        if len(run) >= 2:
            result.update(item_index for item_index, _ in run)
        run = [candidate]
    if len(run) >= 2:
        result.update(item_index for item_index, _ in run)
    return result


def _looks_like_page_break_gap(lines: list[str], previous_index: int, index: int) -> bool:
    between = [line.strip() for line in lines[previous_index + 1 : index] if line.strip()]
    if not between:
        return False
    has_content = any(
        not _is_page_separator(line) and not _is_known_footer(line) for line in between
    )
    return has_content


def _has_numeric_footer_boundary_context(lines: list[str], index: int) -> bool:
    previous_line = _nearest_non_empty_line(lines, index, step=-1)
    next_line = _nearest_non_empty_line(lines, index, step=1)
    return any(
        _is_page_separator(line) or _is_known_footer(line) or _is_page_number(line)
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


def _is_known_footer(line: str) -> bool:
    return _normalized_furniture_line(line) in _KNOWN_FOOTER_VALUES


def _is_page_separator(line: str) -> bool:
    return bool(_PAGE_SEPARATOR_PATTERN.match(line.strip()))


def _merge_split_tables(
    lines: list[str],
    *,
    table_layouts: list[dict[str, Any]],
) -> tuple[list[str], int, int]:
    merged: list[str] = []
    merged_tables = 0
    removed_noise_lines = 0
    index = 0
    table_index = 0
    while index < len(lines):
        if not _is_table_start(lines, index):
            merged.append(lines[index])
            index += 1
            continue

        table_lines, next_index = _collect_pipe_lines(lines, index)
        table_columns = _column_count(table_lines[0])
        current_table_index = table_index
        table_index += 1
        index = next_index

        while True:
            gap = _table_continuation_gap(lines, index)
            if gap.next_index >= len(lines) or not _is_pipe_row(lines[gap.next_index]):
                break

            continuation, continuation_end = _collect_pipe_lines(lines, gap.next_index)
            next_table_index = table_index if _is_table_start(continuation, 0) else None
            has_layout_evidence = _has_cross_page_table_layout_evidence(
                table_layouts,
                current_table_index,
                next_table_index,
            )
            if gap.has_noise and not has_layout_evidence:
                break
            can_merge_noise_gap = (
                gap.has_noise
                and has_layout_evidence
                and _can_merge_after_table_noise_gap(
                    continuation,
                    table_columns,
                )
            )
            append_lines = _continuation_rows(
                table_lines,
                continuation,
                table_columns,
                can_merge_table_start=has_layout_evidence or can_merge_noise_gap,
                preserve_malformed_header=can_merge_noise_gap,
            )
            if not append_lines:
                break
            table_lines.extend(append_lines)
            merged_tables += 1
            removed_noise_lines += gap.removed_noise_lines
            if next_table_index is not None:
                table_index += 1
            index = continuation_end

        merged.extend(table_lines)
        continue

    return merged, merged_tables, removed_noise_lines


def _table_continuation_gap(lines: list[str], index: int) -> _TableGap:
    cursor = index
    noise_lines = 0
    while cursor < len(lines):
        stripped = lines[cursor].strip()
        if not stripped:
            cursor += 1
            continue
        if not _is_table_gap_noise_line(stripped):
            break
        noise_lines += 1
        if noise_lines > _MAX_TABLE_GAP_NOISE_LINES:
            return _TableGap(next_index=index)
        cursor += 1
    return _TableGap(next_index=cursor, removed_noise_lines=noise_lines)


def _is_table_gap_noise_line(stripped: str) -> bool:
    normalized = _normalized_furniture_line(stripped)
    if (
        not normalized
        or _is_pipe_row(stripped)
        or stripped.startswith("#")
        or normalized in _STRUCTURAL_SHORT_TEXT
        or _looks_like_meaningful_short_label(stripped)
        or len(stripped) > _MAX_TABLE_GAP_NOISE_CHARS
        or re.search(r"\s", stripped)
        or re.search(r"[。；，、：:;,.!?！？]", stripped)
        or re.match(r"^\d+[\).、]", stripped)
        or re.match(r"^[一二三四五六七八九十]+[、.]", stripped)
        or re.match(r"^第.+[条章节]$", stripped)
    ):
        return False
    return True


def _collect_pipe_lines(lines: list[str], start: int) -> tuple[list[str], int]:
    index = start
    table_lines: list[str] = []
    while index < len(lines) and _is_pipe_row(lines[index]):
        table_lines.append(lines[index])
        index += 1
    return table_lines, index


def _continuation_rows(
    table_lines: list[str],
    continuation: list[str],
    table_columns: int,
    *,
    can_merge_table_start: bool,
    preserve_malformed_header: bool,
) -> list[str]:
    if not continuation:
        return []
    if not can_merge_table_start and any(
        _column_count(line) != table_columns for line in continuation
    ):
        return []
    if _is_table_start(continuation, 0):
        if not can_merge_table_start:
            return []
        if not _is_compatible_continuation_table(table_lines, continuation, table_columns):
            return []
        if _split_pipe_row(continuation[0]) == _split_pipe_row(table_lines[0]):
            return continuation[2:]
        if preserve_malformed_header:
            return [continuation[0], *continuation[2:]]
        return continuation[2:]
    return continuation


def _can_merge_after_table_noise_gap(
    continuation: list[str],
    table_columns: int,
) -> bool:
    if not continuation:
        return False
    if _is_table_start(continuation, 0):
        return _looks_like_malformed_continuation_table(continuation, table_columns)
    return all(_column_count(line) == table_columns for line in continuation)


def _looks_like_malformed_continuation_table(
    continuation: list[str],
    table_columns: int,
) -> bool:
    if len(continuation) < 2 or not _is_table_start(continuation, 0):
        return False
    first_row = _split_pipe_row(continuation[0])
    if len(first_row) != table_columns:
        return False
    empty_cells = sum(1 for cell in first_row if not cell)
    return empty_cells > 0


def _is_compatible_continuation_table(
    table_lines: list[str],
    continuation: list[str],
    table_columns: int,
) -> bool:
    if len(continuation) < 2:
        return False
    continuation_header = _split_pipe_row(continuation[0])
    if len(continuation_header) != table_columns:
        return False
    current_header = _split_pipe_row(table_lines[0])
    if continuation_header == current_header:
        return True
    return any(not cell for cell in continuation_header)


def _looks_like_meaningful_short_label(stripped: str) -> bool:
    if len(stripped) <= 1:
        return False
    return bool(re.search(r"[a-z][A-Z]|\d|[_-]", stripped)) or (
        stripped[:1].isupper() and any(char.islower() for char in stripped[1:])
    )


def _looks_like_body_title(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _is_page_separator(stripped) or _is_page_number(stripped):
        return False
    if re.match(r"^#{1,6}\s+", stripped):
        return True
    if re.match(r"^\d+[\).、]\s*\S+", stripped):
        return True
    if re.match(r"^第.+[条章节]\b", stripped):
        return True
    if (
        re.search(r"[a-z]", stripped)
        and stripped[:1].isupper()
        and not re.search(r"[.!?。；;，,：:]", stripped)
        and len(stripped) <= 80
    ):
        return True
    return False


def _has_cross_page_table_layout_evidence(
    table_layouts: list[dict[str, Any]],
    current_table_index: int,
    next_table_index: int | None,
) -> bool:
    if next_table_index is None:
        return False
    current = _layout_by_index(table_layouts, current_table_index)
    next_table = _layout_by_index(table_layouts, next_table_index)
    if current is None or next_table is None:
        return False
    current_page = _int_value(current.get("page"))
    next_page = _int_value(next_table.get("page"))
    if current_page is None or next_page != current_page + 1:
        return False
    current_bottom = _bbox_value(current, "bottom")
    next_top = _bbox_value(next_table, "top")
    if current_bottom is None or next_top is None:
        return False
    return current_bottom >= 0.90 and next_top <= 0.10


def _layout_by_index(
    table_layouts: list[dict[str, Any]],
    table_index: int,
) -> dict[str, Any] | None:
    for layout in table_layouts:
        if _int_value(layout.get("index")) == table_index:
            return layout
    return None


def _bbox_value(layout: dict[str, Any], name: str) -> float | None:
    bbox = layout.get("bbox")
    if not isinstance(bbox, dict):
        return None
    raw = bbox.get(name)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _int_value(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _table_layouts(conversion_metadata: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not conversion_metadata:
        return []
    raw_tables = conversion_metadata.get("docling_tables")
    if not isinstance(raw_tables, list):
        return []
    return [item for item in raw_tables if isinstance(item, dict)]


def _is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    if not _is_pipe_row(lines[index]) or not _is_separator_row(lines[index + 1]):
        return False
    return _column_count(lines[index]) == _column_count(lines[index + 1])


def _is_pipe_row(line: str) -> bool:
    stripped = line.strip()
    return len(_split_pipe_row(stripped)) >= 2


def _is_separator_row(line: str) -> bool:
    cells = _split_pipe_row(line)
    return bool(cells) and all(_is_separator_cell(cell) for cell in cells)


def _is_separator_cell(cell: str) -> bool:
    stripped = cell.replace(":", "").strip()
    return len(stripped) >= 3 and set(stripped) <= {"-"}


def _column_count(line: str) -> int:
    return len(_split_pipe_row(line))


def _split_pipe_row(line: str) -> list[str]:
    return split_pipe_row(line)
