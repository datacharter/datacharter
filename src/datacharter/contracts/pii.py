"""Name-based PII column classifier for auto-charter scanning.

A deliberately conservative heuristic: it flags columns whose names contain a
common direct-identifier token. It is a *starting point* a human reviews — it
will miss domain-specific PII and may over-flag (e.g. a "phone" that isn't a
number). Sample-value inspection is a later refinement. The token "name" alone
is intentionally excluded (too many false positives like product_name).
"""

from __future__ import annotations

import re

__all__ = ["classify_pii", "detect_value_pii", "detect_pii", "PII_TOKENS"]

# High-precision value patterns only — distinctive enough that matching most of a
# column's sampled values is strong evidence, without the false positives a loose
# "phone"/"card number" pattern would draw from plain numeric IDs.
_VALUE_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$"),
    "ssn": re.compile(r"^\d{3}-\d{2}-\d{4}$"),
    "ipv4": re.compile(r"^\d{1,3}(\.\d{1,3}){3}$"),
}

PII_TOKENS: tuple[str, ...] = (
    "email",
    "e_mail",
    "phone",
    "mobile",
    "telephone",
    "fax",
    "ssn",
    "social_security",
    "first_name",
    "last_name",
    "full_name",
    "surname",
    "given_name",
    "middle_name",
    "maiden_name",
    "fname",
    "lname",
    "address",
    "street",
    "postal",
    "zipcode",
    "zip_code",
    "birth",
    "dob",
    "date_of_birth",
    "credit_card",
    "card_number",
    "ccn",
    "passport",
    "license",
    "licence",
    "national_id",
    "ip_address",
    "ip_addr",
)


def classify_pii(columns: list[str]) -> list[str]:
    """Return the columns whose names look like direct PII (order preserved)."""
    return [col for col in columns if any(tok in col.lower() for tok in PII_TOKENS)]


_PHONE_SEP = re.compile(r"[-()+.\s]")
_PHONE_CHARS = set("0123456789-()+. ")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _looks_like_card(s: str) -> bool:
    compact = re.sub(r"[ -]", "", s)
    return compact.isdigit() and 13 <= len(compact) <= 19 and _luhn_ok(compact)


def _looks_like_phone(s: str) -> bool:
    # Require phone formatting (a separator) so bare numeric IDs aren't flagged.
    if not _PHONE_SEP.search(s) or set(s) - _PHONE_CHARS:
        return False
    return 7 <= sum(c.isdigit() for c in s) <= 15


def detect_value_pii(values: list, *, threshold: float = 0.6) -> str | None:
    """Return a PII type if most non-null sampled values match its pattern.

    Catches PII whose column name gives nothing away (e.g. a `contact` column
    full of email addresses). Requires a few samples and a strong majority match
    to avoid false positives.
    """
    samples = [str(v) for v in values if v is not None]
    if len(samples) < 3:
        return None
    n = len(samples)
    for kind, pattern in _VALUE_PATTERNS.items():
        if sum(1 for s in samples if pattern.match(s)) / n >= threshold:
            return kind
    if sum(1 for s in samples if _looks_like_card(s)) / n >= threshold:
        return "credit_card"
    if sum(1 for s in samples if _looks_like_phone(s)) / n >= threshold:
        return "phone"
    return None


async def detect_pii(engine) -> dict[str, list[str]]:
    """Suggest PII columns per relation: by name, then by sampled values."""
    tables = await engine.query("SHOW ALL TABLES", timeout_s=30)
    idx = {c: i for i, c in enumerate(tables.columns)}
    suggestions: dict[str, list[str]] = {}
    for row in tables.rows:
        db = row[idx["database"]]
        if db in ("system", "temp"):
            continue
        table = row[idx["name"]]
        relation = table if db == "memory" else f"{db}.{table}"
        columns = list(row[idx["column_names"]])
        flagged = set(classify_pii(columns))
        remaining = [c for c in columns if c not in flagged]
        if remaining and all(ch.isalnum() or ch in "._" for ch in relation):
            sample = await engine.query(f"SELECT * FROM {relation} LIMIT 25", timeout_s=30)
            pos = {c: i for i, c in enumerate(sample.columns)}
            for col in remaining:
                if col in pos and detect_value_pii([r[pos[col]] for r in sample.rows]):
                    flagged.add(col)
        if flagged:
            suggestions[relation] = [c for c in columns if c in flagged]
    return suggestions
