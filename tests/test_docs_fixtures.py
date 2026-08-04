"""Docs-as-fixtures: every fenced yaml/sql block in the docs must parse.

A charter example with a typo'd key teaches users a config that silently does
nothing (the exact F-1 failure class, but in prose). Blocks are collected from
README.md and docs/**/*.md; yaml blocks must be valid YAML, and any block that
looks like a charter (has `sources:`) must load through the real charter
loader. sql blocks must parse in DuckDB.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml as pyyaml

ROOT = Path(__file__).resolve().parent.parent

_FENCE = re.compile(r"```(yaml|sql)\n(.*?)```", re.DOTALL)


def _blocks(kind: str) -> list[tuple[str, str]]:
    out = []
    for md in [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]:
        if not md.exists() or "superpowers" in md.parts:
            continue  # internal design docs, not published
        for m in _FENCE.finditer(md.read_text()):
            if m.group(1) == kind:
                out.append((str(md.relative_to(ROOT)), m.group(2)))
    return out


_YAML_BLOCKS = _blocks("yaml")
_SQL_BLOCKS = _blocks("sql")


def test_docs_have_blocks_to_check():
    # If collection breaks (docs moved, regex rot), this suite must not
    # quietly become a no-op that "passes" on nothing.
    assert len(_YAML_BLOCKS) >= 10, [b[0] for b in _YAML_BLOCKS]
    assert len(_SQL_BLOCKS) >= 2, [b[0] for b in _SQL_BLOCKS]


@pytest.mark.parametrize(
    "src,text", _YAML_BLOCKS, ids=[f"{s}#{i}" for i, (s, _) in enumerate(_YAML_BLOCKS)]
)
def test_yaml_block_parses(src, text, tmp_path):
    data = pyyaml.safe_load(text)
    # Full charter examples must survive the real loader (typo'd keys refuse).
    # `<placeholder>` skeletons parse as YAML but aren't meant to load.
    if isinstance(data, dict) and "sources" in data and "version" in data and "<" not in text:
        from datacharter.contracts.loader import CharterError, load_charter

        # Loader resolves ${VAR} credentials; docs use placeholder names — give
        # them values so validation reaches the structural checks.
        env_vars = set(re.findall(r"\$\{([A-Z0-9_]+)\}", text))
        if env_vars:
            (tmp_path / ".env").write_text("".join(f"{v}=x\n" for v in env_vars))
        for rel in set(re.findall(r"path:\s*([\w./-]+)", text)):
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()
        (tmp_path / "charter.yaml").write_text(text)
        try:
            load_charter(tmp_path)
        except CharterError as exc:
            msg = str(exc)
            # Unresolved example credentials are fine; structural errors are not.
            if "credentials" not in msg and "secret" not in msg.lower():
                raise AssertionError(f"{src}: charter example rejected: {msg}") from None


@pytest.mark.parametrize(
    "src,text", _SQL_BLOCKS, ids=[f"{s}#{i}" for i, (s, _) in enumerate(_SQL_BLOCKS)]
)
def test_sql_block_parses(src, text):
    import duckdb

    con = duckdb.connect()
    try:
        for stmt in [s.strip() for s in text.split(";") if s.strip()]:
            if stmt.startswith("--") and "\n" not in stmt:
                continue
            try:
                con.execute(f"SELECT json_serialize_sql($sql$ {stmt} $sql$)")
            except Exception as exc:
                raise AssertionError(f"{src}: SQL does not parse: {stmt[:80]} — {exc}") from None
    finally:
        con.close()
