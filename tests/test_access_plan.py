"""Access Plan — effective-surface build, classification matrix, and CLI gate."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from datacharter.cli import main as cli_main
from datacharter.contracts import load_charter
from datacharter.contracts.accessplan import (
    NARROWED,
    WIDENED,
    diff_surfaces,
    effective_surface,
    surface_hash,
)

BASE = """\
version: 1
sources:
  store:
    type: sqlite
    path: store.db
    tables: [customers, orders]
    pii:
      customers: [email]
policies:
  store.customers:
    - aggregates only
    - groups of at least 10
"""


def _charter(tmp_path: Path, text: str, name: str = "charter.yaml"):
    (tmp_path / name).write_text(text)
    return load_charter(tmp_path, name, lenient_secrets=True)


def _surface(tmp_path: Path, text: str, name: str) -> dict:
    return effective_surface(_charter(tmp_path, text, name))


def _diff(tmp_path: Path, old_text: str, new_text: str):
    old = _surface(tmp_path, old_text, "old.yaml")
    new = _surface(tmp_path, new_text, "new.yaml")
    return diff_surfaces(old, new)


# --- surface build ----------------------------------------------------------


def test_surface_captures_declared_governance(tmp_path):
    s = _surface(tmp_path, BASE, "charter.yaml")
    store = s["sources"]["store"]
    assert set(store["tables"]) == {"customers", "orders"}
    assert store["tables"]["customers"]["pii"] == ["email"]
    assert s["policies"]["store.customers"]["min_group_size"] == 10
    assert s["policies"]["store.customers"]["aggregate_only"] is True


def test_surface_hash_is_key_order_independent(tmp_path):
    reordered = """\
version: 1
sources:
  store:
    tables: [orders, customers]
    pii:
      customers: [email]
    path: store.db
    type: sqlite
policies:
  store.customers:
    - groups of at least 10
    - aggregates only
"""
    assert surface_hash(_surface(tmp_path, BASE, "a.yaml")) == surface_hash(
        _surface(tmp_path, reordered, "b.yaml")
    )


def test_env_refs_load_without_env_set(tmp_path, monkeypatch):
    monkeypatch.delenv("DB_PASS", raising=False)
    text = """\
version: 1
sources:
  pg:
    type: postgres
    credentials:
      password: ${DB_PASS}
    tables: [t]
"""
    s = _surface(tmp_path, text, "charter.yaml")  # must not raise
    assert "pg" in s["sources"]


# --- classification matrix --------------------------------------------------


def test_table_granted_is_widened(tmp_path):
    new = BASE.replace("tables: [customers, orders]", "tables: [customers, orders, payments]")
    changes = _diff(tmp_path, BASE, new)
    assert any(c.kind == WIDENED and "payments" in c.detail for c in changes)


def test_pii_unmasked_is_widened(tmp_path):
    new = BASE.replace("customers: [email]", "customers: []")
    changes = _diff(tmp_path, BASE, new)
    assert any(c.kind == WIDENED and "email" in c.detail for c in changes)


def test_pii_added_is_narrowed(tmp_path):
    new = BASE.replace("customers: [email]", "customers: [email, phone]")
    changes = _diff(tmp_path, BASE, new)
    assert any(c.kind == NARROWED and "phone" in c.detail for c in changes)


def test_min_group_lowered_is_widened(tmp_path):
    new = BASE.replace("groups of at least 10", "groups of at least 5")
    changes = _diff(tmp_path, BASE, new)
    assert any(c.kind == WIDENED and "min group size" in c.detail for c in changes)


def test_min_group_raised_is_narrowed(tmp_path):
    new = BASE.replace("groups of at least 10", "groups of at least 20")
    changes = _diff(tmp_path, BASE, new)
    assert any(c.kind == NARROWED and "min group size" in c.detail for c in changes)


def test_column_override_unmask_is_widened(tmp_path):
    new = BASE.replace(
        "    pii:\n      customers: [email]",
        "    pii:\n      customers: [email]\n    agent_access:\n      columns:\n"
        "        customers.email: true",
    )
    changes = _diff(tmp_path, BASE, new)
    assert any(c.kind == WIDENED and "email" in c.detail for c in changes)


def test_policy_removed_is_widened(tmp_path):
    new = "\n".join(BASE.splitlines()[:6]) + "\n"  # drop the whole policies block
    changes = _diff(tmp_path, BASE, new)
    assert any(c.kind == WIDENED and "policy removed" in c.detail for c in changes)


def test_row_filter_removed_is_widened(tmp_path):
    old = """\
version: 1
sources:
  store:
    type: sqlite
    path: store.db
    tables: [customers]
    row_filters:
      customers: "region = 'US'"
"""
    new = """\
version: 1
sources:
  store:
    type: sqlite
    path: store.db
    tables: [customers]
"""
    changes = _diff(tmp_path, old, new)
    assert any(c.kind == WIDENED and "row filter removed" in c.detail for c in changes)


def test_row_filter_changed_fails_closed_widened(tmp_path):
    old = """\
version: 1
sources:
  store:
    type: sqlite
    path: store.db
    tables: [customers]
    row_filters:
      customers: "region = 'US'"
"""
    new = old.replace("region = 'US'", "region in ('US','CA')")
    changes = _diff(tmp_path, old, new)
    assert any(c.kind == WIDENED and "row filter changed" in c.detail for c in changes)


def test_identical_charter_is_empty(tmp_path):
    assert _diff(tmp_path, BASE, BASE) == []


def test_cosmetic_context_edit_is_no_change(tmp_path):
    new = BASE.replace(
        "    tables: [customers, orders]",
        "    tables: [customers, orders]\n    context:\n      customers: \"the buyers\"",
    )
    # context is not part of the access surface — a context-only edit is clean.
    assert _diff(tmp_path, BASE, new) == []


# --- CLI --------------------------------------------------------------------


def test_cli_fail_on_widened_exit_code(tmp_path, capsys):
    (tmp_path / "old.yaml").write_text(BASE)
    (tmp_path / "new.yaml").write_text(
        BASE.replace("tables: [customers, orders]", "tables: [customers, orders, payments]")
    )
    rc = cli_main([
        "access", "diff", str(tmp_path),
        "--old", str(tmp_path / "old.yaml"),
        "--new", str(tmp_path / "new.yaml"),
        "--fail-on", "widened",
    ])
    assert rc == 2
    assert "widen" in capsys.readouterr().err


def test_cli_narrowed_only_exits_zero(tmp_path):
    (tmp_path / "old.yaml").write_text(BASE)
    (tmp_path / "new.yaml").write_text(
        BASE.replace("groups of at least 10", "groups of at least 20")
    )
    rc = cli_main([
        "access", "diff", str(tmp_path),
        "--old", str(tmp_path / "old.yaml"), "--new", str(tmp_path / "new.yaml"),
        "--fail-on", "widened",
    ])
    assert rc == 0


def test_cli_json_shape(tmp_path, capsys):
    (tmp_path / "old.yaml").write_text(BASE)
    (tmp_path / "new.yaml").write_text(BASE.replace("customers: [email]", "customers: []"))
    rc = cli_main([
        "access", "diff", str(tmp_path),
        "--old", str(tmp_path / "old.yaml"), "--new", str(tmp_path / "new.yaml"), "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert {"old_hash", "new_hash", "summary", "changes"} <= set(payload)
    assert payload["summary"]["widened"] >= 1
    assert all({"kind", "path", "detail"} <= set(c) for c in payload["changes"])


def test_cli_non_git_without_old_errors(tmp_path, capsys):
    (tmp_path / "charter.yaml").write_text(BASE)
    rc = cli_main(["access", "diff", str(tmp_path)])
    assert rc == 1
    assert "not inside a git repository" in capsys.readouterr().err


def test_cli_against_git_head(tmp_path, capsys):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init")
    git("config", "user.email", "t@t.co")
    git("config", "user.name", "t")
    (tmp_path / "charter.yaml").write_text(BASE)
    git("add", "-A")
    git("commit", "-m", "init")
    # widen: drop a policy
    (tmp_path / "charter.yaml").write_text("\n".join(BASE.splitlines()[:6]) + "\n")
    rc = cli_main(["access", "diff", str(tmp_path), "--fail-on", "widened"])
    assert rc == 2
    assert "WIDENED" in capsys.readouterr().out


def test_cli_new_charter_absent_at_head_treats_old_empty(tmp_path, capsys):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init")
    git("config", "user.email", "t@t.co")
    git("config", "user.name", "t")
    git("commit", "--allow-empty", "-m", "empty")
    (tmp_path / "charter.yaml").write_text(BASE)
    rc = cli_main(["access", "diff", str(tmp_path)])  # no --fail-on → exit 0
    assert rc == 0
    assert "added" in capsys.readouterr().out
