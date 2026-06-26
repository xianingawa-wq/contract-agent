from __future__ import annotations


def is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    return _is_pipe_row(lines[index]) and _is_separator_row(lines[index + 1])


def collect_table_lines(lines: list[str], start: int) -> tuple[list[str], int]:
    index = start
    table_lines: list[str] = []
    while index < len(lines) and _is_pipe_row(lines[index]):
        table_lines.append(lines[index])
        index += 1
    return table_lines, index


def parse_table_rows(table_markdown: str) -> list[list[str]]:
    lines = [line.strip() for line in table_markdown.splitlines() if line.strip()]
    if len(lines) < 2:
        return []
    rows: list[list[str]] = []
    for index, line in enumerate(lines):
        if index == 1 and _is_separator_row(line):
            continue
        row = _split_pipe_row(line)
        rows.append(row)
    return rows


def table_text(rows: list[list[str]]) -> str:
    return "\n".join(" | ".join(cell for cell in row if cell) for row in rows)


def _is_pipe_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _is_separator_row(line: str) -> bool:
    cells = _split_pipe_row(line)
    if not cells:
        return False
    return all(cell and set(cell.replace(":", "").strip()) <= {"-"} for cell in cells)


def _split_pipe_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.replace("\\|", "|").strip() for cell in stripped.split("|")]
