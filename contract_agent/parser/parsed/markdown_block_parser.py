from __future__ import annotations

import re


def block_type_and_text(markdown: str) -> tuple[str, str, int | None]:
    heading = re.match(r"^(#{1,6})\s+(.*)$", markdown.strip())
    if heading:
        level = len(heading.group(1))
        return ("title" if level == 1 else "clause_header", heading.group(2).strip(), level)
    stripped = markdown.strip()
    if stripped.startswith("- "):
        return "list_item", stripped[2:].strip(), None
    return "paragraph", normalize_text(stripped), None


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
