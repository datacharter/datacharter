"""Workspace guides: free-form markdown context for agents, versioned with the contract.

Guides live in `guides/*.md` at the workspace root. They are trusted contract
content (authored by the workspace owner, like `row_filters` predicates) and are
served only to the agent surface: the built-in agent's system prompt, the Claude
Code driver, and the MCP server's `initialize.instructions`.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = [
    "load_guides", "GUIDES_DIR", "MAX_GUIDE_CHARS",
    "find_pii_in_text", "scan_guides_for_pii",
]

# High-precision in-text PII patterns. Guides flow to agents, so a literal value
# here is a leak that column-level masking never sees. Kept conservative (each
# requires distinctive structure) so `datacharter scan` doesn't cry wolf.
_INTEXT_PII: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d{4}[ -]){3}\d{4}\b"),
    "phone": re.compile(r"\b(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b"),
    "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}


def find_pii_in_text(text: str) -> list[str]:
    """Literal PII-looking values in a string, as ``"kind: value"`` entries."""
    hits: list[str] = []
    for kind, pattern in _INTEXT_PII.items():
        for m in pattern.findall(text):
            value = m if isinstance(m, str) else m[0]
            hits.append(f"{kind}: {value}")
    return hits


def scan_guides_for_pii(workspace: Path | str) -> dict[str, list[str]]:
    """Per-guide literal PII, scanning the comment-stripped text agents actually see."""
    root = Path(workspace) / GUIDES_DIR
    if not root.is_dir():
        return {}
    out: dict[str, list[str]] = {}
    for f in sorted(root.glob("*.md")):
        try:
            raw = f.read_text()
        except OSError:
            continue
        text = re.sub(r"<!--.*?-->", "", raw, flags=re.S)
        hits = find_pii_in_text(text)
        if hits:
            out[f.stem] = hits
    return out

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
