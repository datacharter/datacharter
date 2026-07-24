"""Credential scrubbing — engine-wide invariant: no secret ever leaves in an error."""

from __future__ import annotations

from collections.abc import Iterable

__all__ = ["scrub"]

MASK = "***"

# Values shorter than this are too generic to scrub without mangling messages.
_MIN_SECRET_LEN = 3


def scrub(text: str, secrets: Iterable[str]) -> str:
    """Replace every occurrence of each secret value in text with a mask."""
    for value in sorted({s for s in secrets if len(s) >= _MIN_SECRET_LEN}, key=len, reverse=True):
        text = text.replace(value, MASK)
    return text
