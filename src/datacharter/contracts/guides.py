"""Workspace guides: free-form markdown context for agents, versioned with the contract.

Guides live in `guides/*.md` at the workspace root. They are trusted contract
content (authored by the workspace owner, like `row_filters` predicates) and are
served only to the agent surface: the built-in agent's system prompt, the Claude
Code driver, and the MCP server's `initialize.instructions`.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = ["load_guides", "GUIDES_DIR", "MAX_GUIDE_CHARS"]

GUIDES_DIR = "guides"
#: Cap the concatenated guide text so a sprawling guides/ dir can't blow the context.
MAX_GUIDE_CHARS = 8000
_TRUNCATION_MARKER = "\n\n[guides truncated]"


def load_guides(workspace: Path | str, max_chars: int = MAX_GUIDE_CHARS) -> str:
    """Concatenate `guides/*.md` (sorted by filename) with per-file headers."""
    root = Path(workspace) / GUIDES_DIR
    if not root.is_dir():
        return ""
    parts: list[str] = []
    for f in sorted(root.glob("*.md")):
        try:
            raw = f.read_text()
        except OSError:
            continue
        # HTML comments are author-facing (the init scaffold is one big comment);
        # they never reach the model.
        text = re.sub(r"<!--.*?-->", "", raw, flags=re.S).strip()
        if text:
            parts.append(f"## Guide: {f.stem}\n{text}")
    joined = "\n\n".join(parts)
    if len(joined) > max_chars:
        joined = joined[:max_chars].rstrip() + _TRUNCATION_MARKER
    return joined
