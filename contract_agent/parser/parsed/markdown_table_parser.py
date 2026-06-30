from __future__ import annotations

from contract_agent.parser.parsed.markdown_table_row_parser import split_pipe_row


def is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    if not _is_pipe_row(lines[index]) or not _is_separator_row(lines[index + 1]):
        return False
    return _column_count(lines[index]) == _column_count(lines[index + 1])


def collect_table_lines(lines: list[str], start: int) -> tuple[list[str], int]:
    index = start
    table_lines: list[str] = []
    expected_columns = _column_count(lines[start])
    while (
        index < len(lines)
        and _is_pipe_row(lines[index])
        and _column_count(lines[index]) == expected_columns
    ):
        table_lines.append(lines[index])
        index += 1
    return table_lines, index


def parse_table_rows(table_markdown: str) -> list[list[str]]:
    lines = [line.strip() for line in table_markdown.splitlines() if line.strip()]
    if len(lines) < 2 or not is_table_start(lines, 0):
        return []
    rows: list[list[str]] = []
    expected_columns = _column_count(lines[0])
    for index, line in enumerate(lines):
        if not _is_pipe_row(line) or _column_count(line) != expected_columns:
            break
        if index == 1 and _is_separator_row(line):
            continue
        row = _split_pipe_row(line)
        rows.append(row)
    return rows


def table_text(rows: list[list[str]]) -> str:
    return "\n".join(" | ".join(row) for row in rows)


def _is_pipe_row(line: str) -> bool:
    stripped = line.strip()
    return len(_split_pipe_row(stripped)) >= 2


def _is_separator_row(line: str) -> bool:
    cells = _split_pipe_row(line)
    if not cells:
        return False
    return all(_is_separator_cell(cell) for cell in cells)


def _is_separator_cell(cell: str) -> bool:
    stripped = cell.replace(":", "").strip()
    return len(stripped) >= 3 and set(stripped) <= {"-"}


def _column_count(line: str) -> int:
    return len(_split_pipe_row(line))


def _split_pipe_row(line: str) -> list[str]:
    return split_pipe_row(line)
