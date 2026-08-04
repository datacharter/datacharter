"""Governance must hold across every SQL SHAPE, not just `SELECT col` / `SELECT *`.

The prior remediation proved parity across entry *doors* but only ever with the
identity projection — so a computed expression (`lower(email)`), a whole-row
value (`to_json(c)`), a compat-alias relation (`crm__customers`), a mixed-case
name (`crm.Customers`), and a file-path table (`FROM '/etc/x'`) each bypassed a
guard. This suite crosses {source kind} × {SQL shape} and asserts the SECRET
STRING is ABSENT from every governed result.
"""

import asyncio
import json
import sqlite3

import keyring
import keyring.backend
import pytest

from datacharter.agent.factory import build_toolbox, detect_auto_pii
from datacharter.cli import _open_engine
from datacharter.cli import main as cli_main
from datacharter.contracts import load_charter

SECRET = "alice@acme.com"
SALARY = "100000"


class _MemKeyring(keyring.backend.KeyringBackend):
    priority = 1

    def __init__(self):
        self.store = {}

    def get_password(self, s, n):
        return self.store.get((s, n))

    def set_password(self, s, n, v):
        self.store[(s, n)] = v

    def delete_password(self, s, n):
        self.store.pop((s, n), None)


@pytest.fixture(autouse=True)
def mem_keyring():
    prev = keyring.get_keyring()
    keyring.set_keyring(_MemKeyring())
    yield
    keyring.set_keyring(prev)


def _run(ws, sql):
    charter = load_charter(ws)
    engine = _open_engine(ws, charter.sources)
    try:
        box = build_toolbox(engine, charter, auto_pii=asyncio.run(detect_auto_pii(engine)))
        return asyncio.run(box.run("query", json.dumps({"sql": sql})))
    finally:
        engine.close()


@pytest.fixture
def csv_ws(tmp_path):
    assert cli_main(["init", str(tmp_path)]) == 0
    (tmp_path / "customers.csv").write_text(
        "name,email\nalice,alice@acme.com\nbob,bob@acme.com\ncarol,carol@acme.com\n"
    )
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  crm:\n    type: csv\n    path: customers.csv\n"
        "    pii:\n      customers: [email]\n"
    )
    return tmp_path


@pytest.fixture
def sqlite_ws(tmp_path):
    assert cli_main(["init", str(tmp_path)]) == 0
    con = sqlite3.connect(str(tmp_path / "crm.db"))
    con.execute("CREATE TABLE customers (name TEXT, email TEXT, salary INT)")
    con.executemany(
        "INSERT INTO customers VALUES (?,?,?)",
        [("alice", "alice@acme.com", 100000), ("bob", "bob@acme.com", 90000)],
    )
    con.commit()
    con.close()
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  crm:\n    type: sqlite\n    path: crm.db\n"
        "    tables: [customers]\n    pii:\n      customers: [email]\n"
        "    agent_access:\n      columns:\n        customers.salary: false\n"
    )
    return tmp_path


# F-A / B-1: a masked column reached through ANY expression must stay masked.
EXPR_SHAPES = [
    "SELECT email FROM crm",
    "SELECT lower(email) FROM crm",
    "SELECT upper(email) AS x FROM crm",
    "SELECT email || '!' FROM crm",
    "SELECT CAST(email AS VARCHAR) FROM crm",
    "SELECT CASE WHEN true THEN email ELSE 'x' END FROM crm",
    "SELECT string_agg(email, '|') FROM crm",
    "SELECT list(email) FROM crm",
    "SELECT to_json(c) AS j FROM crm c",
    "SELECT c::VARCHAR FROM crm c",
    "SELECT * FROM crm",
]


@pytest.mark.parametrize("sql", EXPR_SHAPES)
def test_csv_masked_pii_never_leaks_through_any_expression(csv_ws, sql):
    assert SECRET not in _run(csv_ws, sql), sql


# F-B: the compat alias must be governed identically to the native relation.
def test_attach_compat_alias_is_governed(sqlite_ws):
    for rel in ("crm.customers", "crm__customers"):
        out = _run(sqlite_ws, f"SELECT name, email, salary FROM {rel}")
        assert SECRET not in out, rel        # PII masked
        assert SALARY not in out, rel        # agent_access override honored


def test_compat_alias_hidden_from_list_tables(sqlite_ws):
    charter = load_charter(sqlite_ws)
    engine = _open_engine(sqlite_ws, charter.sources)
    try:
        box = build_toolbox(engine, charter, auto_pii=asyncio.run(detect_auto_pii(engine)))
        listed = json.loads(asyncio.run(box.run("list_tables", "{}")))
        rels = {t["relation"] for t in listed}
        assert "crm.customers" in rels
        assert "crm__customers" not in rels
    finally:
        engine.close()


# B-4: identifier case must not turn masking or overrides off.
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT email FROM crm.Customers",
        "SELECT EMAIL FROM crm.CUSTOMERS",
        "SELECT salary FROM crm.Customers",
    ],
)
def test_attach_mixed_case_still_governed(sqlite_ws, sql):
    out = _run(sqlite_ws, sql)
    assert SECRET not in out, sql
    assert SALARY not in out, sql


# B-2: a file path named as a table (replacement scan) must be refused.
def test_file_path_table_is_refused(csv_ws, tmp_path):
    secret_file = tmp_path / "stolen.json"
    secret_file.write_text('{"token":"sk-live-STOLEN"}\n')
    for sql in (
        f"SELECT * FROM '{secret_file}'",
        f"SELECT * FROM \"{secret_file}\"",
        f"WITH t AS (SELECT * FROM '{secret_file}') SELECT * FROM t",
    ):
        out = _run(csv_ws, sql)
        assert "STOLEN" not in out, sql
        assert "not allowed" in out or "Error" in out, sql
