from __future__ import annotations

import re
from dataclasses import dataclass

from contract_agent.parser.parsed.markdown_block_parser import block_type_and_text, normalize_text
from contract_agent.parser.parsed.markdown_table_parser import collect_table_lines, is_table_start


@dataclass(frozen=True)
class MarkdownLogicalBlock:
    block_type: str
    text: str
    markdown: str
    line_start: int
    line_end: int
    level: int | None = None


_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_BLOCKQUOTE_RE = re.compile(r"^ {0,3}>\s?(.*)$")
_LIST_ITEM_RE = re.compile(r"^ {0,3}(?:[-*+]\s+|\d+[\.)]\s+)(.*)$")


def collect_logical_blocks(lines: list[str]) -> list[MarkdownLogicalBlock]:
    blocks: list[MarkdownLogicalBlock] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        if _is_fence(line):
            block, index = _collect_fenced_code(lines, index)
            blocks.append(block)
            continue

        if is_table_start(lines, index):
            table_lines, next_index = collect_table_lines(lines, index)
            blocks.append(
                MarkdownLogicalBlock(
                    block_type="table",
                    text="",
                    markdown="\n".join(table_lines),
                    line_start=index,
                    line_end=next_index,
                )
            )
            index = next_index
            continue

        if _is_blockquote(line):
            block, index = _collect_blockquote(lines, index)
            blocks.append(block)
            continue

        block_type, text, level = block_type_and_text(line)
        if block_type in {"title", "clause_header"}:
            blocks.append(
                MarkdownLogicalBlock(
                    block_type=block_type,
                    text=text,
                    markdown=line.strip(),
                    line_start=index,
                    line_end=index + 1,
                    level=level,
                )
            )
            index += 1
            continue

        if block_type == "list_item":
            block, index = _collect_list_item(lines, index)
            blocks.append(block)
            continue

        block, index = _collect_paragraph(lines, index)
        blocks.append(block)
    return blocks


def _collect_fenced_code(lines: list[str], start: int) -> tuple[MarkdownLogicalBlock, int]:
    fence_match = _FENCE_RE.match(lines[start])
    fence = fence_match.group(1) if fence_match else lines[start].strip()[:3]
    closing_fence_re = re.compile(rf"^{re.escape(fence[0])}{{{len(fence)},}}\s*$")
    index = start + 1
    body: list[str] = []
    while index < len(lines):
        if closing_fence_re.match(lines[index].strip()):
            index += 1
            break
        body.append(lines[index])
        index += 1
    markdown = "\n".join(lines[start:index])
    return (
        MarkdownLogicalBlock(
            block_type="fenced_code",
            text="\n".join(body).strip("\n"),
            markdown=markdown,
            line_start=start,
            line_end=index,
        ),
        index,
    )


def _collect_blockquote(lines: list[str], start: int) -> tuple[MarkdownLogicalBlock, int]:
    index = start
    markdown_lines: list[str] = []
    text_lines: list[str] = []
    while index < len(lines) and _is_blockquote(lines[index]):
        markdown_lines.append(lines[index])
        match = _BLOCKQUOTE_RE.match(lines[index])
        text_lines.append(match.group(1).strip() if match else lines[index].strip())
        index += 1
    return (
        MarkdownLogicalBlock(
            block_type="blockquote",
            text=normalize_text(" ".join(text_lines)),
            markdown="\n".join(markdown_lines),
            line_start=start,
            line_end=index,
        ),
        index,
    )


def _collect_list_item(lines: list[str], start: int) -> tuple[MarkdownLogicalBlock, int]:
    markdown_lines = [lines[start]]
    match = _LIST_ITEM_RE.match(lines[start])
    text_parts = [match.group(1).strip() if match else lines[start].strip()]
    index = start + 1
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            break
        if _starts_new_block(lines, index):
            break
        markdown_lines.append(line)
        text_parts.append(line.strip())
        index += 1
    return (
        MarkdownLogicalBlock(
            block_type="list_item",
            text=normalize_text(" ".join(text_parts)),
            markdown="\n".join(markdown_lines),
            line_start=start,
            line_end=index,
        ),
        index,
    )


def _collect_paragraph(lines: list[str], start: int) -> tuple[MarkdownLogicalBlock, int]:
    markdown_lines: list[str] = []
    index = start
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            break
        if index != start and _starts_new_block(lines, index):
            break
        markdown_lines.append(line)
        index += 1
    markdown = "\n".join(markdown_lines)
    return (
        MarkdownLogicalBlock(
            block_type="paragraph",
            text=normalize_text(markdown),
            markdown=markdown,
            line_start=start,
            line_end=index,
        ),
        index,
    )


def _starts_new_block(lines: list[str], index: int) -> bool:
    line = lines[index]
    block_type, _, _ = block_type_and_text(line)
    return (
        _is_fence(line)
        or is_table_start(lines, index)
        or _is_blockquote(line)
        or block_type in {"title", "clause_header", "list_item"}
    )


def _is_fence(line: str) -> bool:
    return bool(_FENCE_RE.match(line))


def _is_blockquote(line: str) -> bool:
    return bool(_BLOCKQUOTE_RE.match(line))
