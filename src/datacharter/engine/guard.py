"""Read-only statement guard (DESIGN D4): parser-enforced, not regex.

The engine surface is reachable from the browser, so the guard is a real
security boundary. It uses DuckDB's own parser (`extract_statements`) to count
and type statements — defeating comment/quote/dollar-quote tricks that a
lexical filter misses — and a parse-tree walk to block filesystem/remote
functions. Only three shapes pass: a single SELECT (no fs/remote functions),
EXPLAIN of such a SELECT, and CREATE/DROP against the local catalog.
"""

from __future__ import annotations

import json
import re

import duckdb

__all__ = ["ensure_allowed", "QueryNotAllowed"]


class QueryNotAllowed(Exception):
    """Raised when a statement falls outside the read-only allowlist."""


# Functions that reach the filesystem or a remote host. Sources are queried
# through their registered views/catalogs (built by the engine, not user SQL),
# so these never belong in a user query — blocking them closes arbitrary file
# read and SSRF via ad-hoc readers.
_FORBIDDEN_FUNCTIONS = frozenset(
    {
        "read_csv", "read_csv_auto", "read_parquet", "parquet_scan",
        "parquet_metadata", "parquet_schema", "parquet_file_metadata",
        "parquet_kv_metadata", "read_json", "read_json_auto", "read_json_objects",
        "read_json_objects_auto", "read_ndjson", "read_ndjson_auto",
        "read_ndjson_objects", "read_text", "read_blob", "read_xlsx", "glob",
        "sniff_csv", "iceberg_scan", "iceberg_metadata", "iceberg_snapshots",
        "delta_scan", "postgres_scan", "postgres_scan_pushdown", "postgres_query",
        "postgres_execute", "mysql_scan", "mysql_query", "mysql_execute",
        "sqlite_scan", "sqlite_query",
        # PRAGMA table-function variants that disclose host paths/config.
        "pragma_database_list", "pragma_database_size",
    }
)

# CREATE/DROP is the one write path, and only against the local catalog (D8).
# Anchored at the statement start so the target — not some FROM clause — decides.
_LOCAL_DDL_TARGET = re.compile(
    r"^\s*(?:create\s+(?:or\s+replace\s+)?(?:temp(?:orary)?\s+)?table"
    r"|drop\s+table(?:\s+if\s+exists)?)\s+local\s*\.",
    re.IGNORECASE | re.DOTALL,
)
_LEADING_COMMENTS = re.compile(r"^(?:\s*--[^\n]*\n|\s*/\*.*?\*/)*\s*", re.DOTALL)
_EXPLAIN_PREFIX = re.compile(r"^\s*explain\s+(?:analyze\s+)?", re.IGNORECASE)
# DuckDB expands PIVOT/UNPIVOT into [CREATE temp, SELECT]. A statement the user
# typed as a read (starts with SELECT/WITH/(/PIVOT/UNPIVOT) that expands this way
# is a read — the CREATE targets an internal temp and it cannot write.
_PIVOT_LEADING = re.compile(r"^\s*(?:select|with|\(|pivot|unpivot)\b", re.IGNORECASE | re.DOTALL)
_PIVOT_TOKEN = re.compile(r"\b(?:un)?pivot\b", re.IGNORECASE)
# DuckDB rewrites `PRAGMA ...` to a SELECT statement type, so it slips past the
# type allowlist — yet PRAGMAs can disclose host config (database_list leaks file
# paths) or toggle settings. The agent surface has no need for any PRAGMA.
_PRAGMA_LEADING = re.compile(r"^\s*pragma\b", re.IGNORECASE)


def ensure_allowed(sql: str) -> str:
    """Validate one read-only (or local-DDL) statement; return it stripped.

    Raises QueryNotAllowed for anything else. Uses an ephemeral in-memory
    connection purely to parse — nothing from `sql` is executed.
    """
    con = duckdb.connect()
    try:
        return _check(con, sql)
    finally:
        con.close()


def _statement_type(con: duckdb.DuckDBPyConnection, sql: str) -> str:
    """The single statement's type, e.g. 'SELECT'. Raises if not exactly one."""
    try:
        statements = con.extract_statements(sql)
    except Exception:
        raise QueryNotAllowed("Could not parse SQL; check for syntax errors.") from None
    if not statements:
        raise QueryNotAllowed("Empty statement.")
    if len(statements) > 1:
        raise QueryNotAllowed("One statement at a time.")
    return str(statements[0].type).rsplit(".", 1)[-1].upper()


def _is_pivot_expansion(statements: list, sql: str) -> bool:
    """True if `sql` is a PIVOT/UNPIVOT read that DuckDB expanded into
    [CREATE temp, SELECT] — the only case where one typed read yields two
    statements. A user-typed CREATE (which starts with CREATE) never matches."""
    types = [str(s.type).rsplit(".", 1)[-1].upper() for s in statements]
    if types != ["CREATE", "SELECT"]:
        return False
    stripped = _LEADING_COMMENTS.sub("", sql)
    return bool(_PIVOT_LEADING.match(stripped) and _PIVOT_TOKEN.search(stripped))


def _check(con: duckdb.DuckDBPyConnection, sql: str) -> str:
    try:
        statements = con.extract_statements(sql)
    except Exception:
        raise QueryNotAllowed("Could not parse SQL; check for syntax errors.") from None
    if not statements:
        raise QueryNotAllowed("Empty statement.")
    if _PRAGMA_LEADING.match(_LEADING_COMMENTS.sub("", sql)):
        raise QueryNotAllowed(
            "PRAGMA is not allowed; it can disclose host configuration or change "
            "engine settings. The engine is read-only for queries only."
        )
    if _is_pivot_expansion(statements, sql):
        # Token-scan (not just the tree) so a forbidden function inside the pivot
        # is caught even when the pivot serializes to an incomplete tree.
        found = _forbidden_functions(con, sql) | _token_scan(sql)
        if found:
            raise QueryNotAllowed(
                f"Filesystem/remote function(s) not allowed in a query: {', '.join(sorted(found))}."
            )
        return sql.strip()
    if len(statements) > 1:
        raise QueryNotAllowed("One statement at a time.")
    stype = str(statements[0].type).rsplit(".", 1)[-1].upper()
    if stype == "SELECT":
        _reject_forbidden(con, sql)
        return sql.strip()
    if stype == "EXPLAIN":
        inner = _EXPLAIN_PREFIX.sub("", sql, count=1).strip()
        if _statement_type(con, inner) != "SELECT":
            raise QueryNotAllowed("EXPLAIN is only allowed on a query.")
        _reject_forbidden(con, inner)
        return sql.strip()
    if stype in ("CREATE", "DROP"):
        if not _LOCAL_DDL_TARGET.match(_LEADING_COMMENTS.sub("", sql)):
            raise QueryNotAllowed(
                "The engine is read-only; only local.* table DDL is an allowed write path."
            )
        _reject_forbidden(con, sql)
        return sql.strip()
    raise QueryNotAllowed(
        f"Statement type '{stype}' is not allowed. The engine is read-only; "
        "only queries, EXPLAIN, and local.* table DDL are accepted."
    )


def _reject_forbidden(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    found = _forbidden_functions(con, sql)
    if found:
        raise QueryNotAllowed(
            f"Filesystem/remote function(s) not allowed in a query: "
            f"{', '.join(sorted(found))}. Query your data through its defined source."
        )
    files = _file_tables(con, sql)
    if files:
        # DuckDB's replacement scan reads a file NAMED AS A TABLE
        # (`FROM '/etc/passwd'`, `FROM 'data/*.csv'`) with no function node, so
        # the function denylist misses it — arbitrary file read / SSRF. A real
        # source is a registered relation (a bare identifier), never a path.
        raise QueryNotAllowed(
            f"Reading a file path directly is not allowed: {', '.join(sorted(files))}. "
            f"Query your data through its defined source."
        )


# A table name that is really a file path or URL: a path/glob character, a URL
# scheme, or a data-file extension. Registered relations are bare identifiers.
_FILE_TABLE = re.compile(
    r"[/\\*?]|://|\.(?:csv|tsv|txt|parquet|parq|json|jsonl|ndjson|xlsx|xls|"
    r"arrow|feather|orc|avro|db|sqlite|duckdb|gz|zst|bz2|blob)\b",
    re.IGNORECASE,
)


def _file_tables(con: duckdb.DuckDBPyConnection, sql: str) -> set[str]:
    """BASE_TABLE names that are file paths / URLs (replacement scans)."""
    try:
        tree = json.loads(con.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0])
    except Exception:
        return set()
    if isinstance(tree, dict) and tree.get("error"):
        return set()
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "BASE_TABLE":
                name = node.get("table_name")
                # Only a lone table_name can be a replacement scan; a genuine
                # catalog.schema.table reference has separate qualifier parts.
                if (
                    isinstance(name, str)
                    and not node.get("catalog_name")
                    and not node.get("schema_name")
                    and _FILE_TABLE.search(name)
                ):
                    found.add(name)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(tree)
    return found


def _token_scan(sql: str) -> set[str]:
    """Conservative fallback when the tree is unavailable (e.g. CREATE-AS-SELECT)."""
    low = sql.lower()
    return {fn for fn in _FORBIDDEN_FUNCTIONS if re.search(rf"\b{fn}\s*\(", low)}


def _forbidden_functions(con: duckdb.DuckDBPyConnection, sql: str) -> set[str]:
    """Denylisted function names present in the statement, via the parse tree."""
    try:
        tree = json.loads(con.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0])
    except Exception:
        return _token_scan(sql)
    # Non-SELECT forms return an error object, not a tree — scan the text instead.
    if isinstance(tree, dict) and tree.get("error"):
        return _token_scan(sql)
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            name = node.get("function_name")
            if isinstance(name, str) and name.lower() in _FORBIDDEN_FUNCTIONS:
                found.add(name.lower())
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(tree)
    return found
