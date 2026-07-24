"""Name-based PII column classifier for auto-charter scanning.

A deliberately conservative heuristic: it flags columns whose names contain a
common direct-identifier token. It is a *starting point* a human reviews — it
will miss domain-specific PII and may over-flag (e.g. a "phone" that isn't a
number). Sample-value inspection is a later refinement. The token "name" alone
is intentionally excluded (too many false positives like product_name).
"""

from __future__ import annotations

import re

__all__ = ["classify_pii", "detect_value_pii", "PII_TOKENS"]

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


def detect_value_pii(values: list, *, threshold: float = 0.6) -> str | None:
    """Return a PII type if most non-null sampled values match its pattern.

    Catches PII whose column name gives nothing away (e.g. a `contact` column
    full of email addresses). Requires a few samples and a strong majority match
    to avoid false positives.
    """
    samples = [str(v) for v in values if v is not None]
    if len(samples) < 3:
        return None
    for kind, pattern in _VALUE_PATTERNS.items():
        if sum(1 for s in samples if pattern.match(s)) / len(samples) >= threshold:
            return kind
    return None
