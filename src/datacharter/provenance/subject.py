"""Subject-access receipts (DSAR): a signed, per-person record of exactly what an
AI agent can see about one individual through the governed surface.

GDPR Art. 15 and the EU AI Act's transparency duties give a person the right to
know what an automated system holds about them. Because DataCharter sits on the
rows flowing to the agent, it can answer precisely — run a masked lookup for the
subject across every governed relation that carries the key column, and seal the
result with the workspace's provenance key. What the receipt shows is what the
agent sees: PII columns come back masked.
"""

from __future__ import annotations

from datacharter.provenance import keys, receipt

__all__ = ["SCHEMA", "build_subject_access", "find_relations_with_column"]

SCHEMA = "datacharter/subject-access/v1"


def _sql_literal(value: str) -> str:
    """Single-quote a string literal for inline SQL, escaping embedded quotes.
    The subject value is untrusted, so it never reaches SQL unescaped."""
    return "'" + value.replace("'", "''") + "'"


def find_relations_with_column(catalog_rows, idx: dict, column: str) -> list[tuple[str, list[str]]]:
    """From a `SHOW ALL TABLES` result, the (relation, columns) pairs that carry
    the subject key column. `local`/`temp`/`system` scratch schemas are skipped, and
    the `memory` flat `source__table` aliases are skipped when a real `db.table`
    exists — otherwise a subject would be counted once per alias, inflating the DSAR."""
    out: list[tuple[str, list[str]]] = []
    col = column.lower()
    for row in catalog_rows:
        db = row[idx["database"]]
        if db in ("system", "temp", "local"):
            continue
        name = row[idx["name"]]
        # `memory` `source__table` views duplicate a `source`.`table` registered
        # under its own schema — count the canonical one, not both.
        if db == "memory" and "__" in name:
            continue
        cols = list(row[idx["column_names"]])
        if col in {c.lower() for c in cols}:
            relation = name if db == "memory" else f"{db}.{name}"
            out.append((relation, cols))
    return out


def build_subject_access(
    *, workspace: str, subject_column: str, subject_value: str, surface_hash: str,
    records: list[dict], signer: keys.Signer, issued_at: str | None = None,
) -> dict:
    """Assemble and sign the DSAR receipt. `records` are per-relation
    `{relation, matched_rows, columns, masked_columns, rows}` (rows already masked)."""
    body = {
        "schema": SCHEMA,
        "issued_at": issued_at or receipt._now_iso(),
        "workspace": workspace,
        "subject": {"column": subject_column, "value": subject_value},
        "surface_hash": surface_hash,
        "records": records,
        "total_matched_rows": sum(r["matched_rows"] for r in records),
    }
    return receipt.sign(body, signer)


def subject_query(relation: str, column: str, value: str) -> str:
    """The masked lookup SQL for one relation. Value is escaped as a literal."""
    return f"SELECT * FROM {relation} WHERE {column} = {_sql_literal(value)}"
