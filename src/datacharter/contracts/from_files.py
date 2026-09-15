"""Turn a folder of files into charter.yaml sources a human can review."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from datacharter.contracts.loader import CHARTER_FILE
from datacharter.contracts.writer import set_pii, upsert_source
from datacharter.models import SourceType

__all__ = [
    "FromFilesError",
    "ProposedFile",
    "ApplyResult",
    "discover_data_files",
    "apply_file_sources",
]

_SUFFIX_TYPE: dict[str, SourceType] = {
    ".csv": SourceType.CSV,
    ".parquet": SourceType.PARQUET,
    ".json": SourceType.JSON,
    ".xlsx": SourceType.EXCEL,
}

_SKIP_DIRS = {
    ".datacharter",
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    "queries",
    "guides",
    "dist",
    "build",
}


class FromFilesError(Exception):
    """No usable files, or the workspace refused the write."""


@dataclass(frozen=True)
class ProposedFile:
    name: str
    type: str
    path: str


@dataclass
class ApplyResult:
    added: list[ProposedFile] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    pii: dict[str, list[str]] = field(default_factory=dict)


def _source_name(stem: str, used: set[str], suffix: str) -> str:
    slug = re.sub(r"[^a-z0-9_]", "_", stem.lower()).strip("_") or "file"
    if not slug[0].isalpha():
        slug = "f_" + slug
    slug = slug[:63].rstrip("_") or "file"
    if slug not in used:
        return slug
    extra = suffix.lstrip(".")
    alt = f"{slug}_{extra}"[:63].rstrip("_")
    if alt not in used:
        return alt
    n = 2
    while f"{slug}_{n}" in used:
        n += 1
    return f"{slug}_{n}"


def discover_data_files(root: Path) -> list[ProposedFile]:
    """csv/parquet/json/xlsx under root, skipping state and guide dirs."""
    root = root.resolve()
    used: set[str] = set()
    found: list[ProposedFile] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        kind = _SUFFIX_TYPE.get(path.suffix.lower())
        if kind is None:
            continue
        name = _source_name(path.stem, used, path.suffix.lower())
        used.add(name)
        rel = path.relative_to(root).as_posix()
        found.append(ProposedFile(name=name, type=kind.value, path=rel))
    return found


def _existing_names(workspace: Path) -> set[str]:
    from datacharter.contracts.loader import load_charter

    path = workspace / CHARTER_FILE
    if not path.exists():
        return set()
    try:
        return {s.name for s in load_charter(workspace).sources}
    except Exception:
        return set()


def _write_sources(workspace: Path, proposed: list[ProposedFile]) -> None:
    path = workspace / CHARTER_FILE
    if not path.exists():
        path.write_text("version: 1\n\nsources: {}\n")
    for item in proposed:
        upsert_source(workspace, item.name, {"type": item.type, "path": item.path})


def _scan_pii_sync(engine) -> dict[str, list[str]]:
    from datacharter.contracts.pii import classify_pii, detect_value_pii

    tables = engine.query_sync("SHOW ALL TABLES")
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
            sample = engine.query_sync(f"SELECT * FROM {relation} LIMIT 25")
            pos = {c: i for i, c in enumerate(sample.columns)}
            for col in remaining:
                if col in pos and detect_value_pii([r[pos[col]] for r in sample.rows]):
                    flagged.add(col)
        if flagged:
            suggestions[relation] = [c for c in columns if c in flagged]
    return suggestions


def _write_pii_for(
    workspace: Path,
    proposed: list[ProposedFile],
    suggestions: dict[str, list[str]],
) -> dict[str, list[str]]:
    by_name = {p.name: p for p in proposed}
    written: dict[str, list[str]] = {}
    for relation, cols in suggestions.items():
        parts = relation.split(".")
        source = parts[0] if len(parts) > 1 else relation
        table = parts[-1]
        if source not in by_name:
            source = table if table in by_name else source
        if source not in by_name:
            continue
        try:
            set_pii(workspace, source, source, cols)
            written[source] = cols
        except Exception:
            continue
    return written


def _attach_and_scan_pii(workspace: Path, proposed: list[ProposedFile]) -> dict[str, list[str]]:
    from datacharter.contracts.loader import load_charter
    from datacharter.engine.session import Engine

    charter = load_charter(workspace)
    with Engine(workspace, charter.sources) as eng:
        suggestions = _scan_pii_sync(eng)
    return _write_pii_for(workspace, proposed, suggestions)


def apply_file_sources(
    workspace: Path,
    *,
    merge: bool = True,
    engine=None,
) -> ApplyResult:
    """Upsert file sources from disk. Merge skips names already in the charter."""
    workspace = workspace.resolve()
    discovered = discover_data_files(workspace)
    if not discovered:
        raise FromFilesError(
            f"No csv, parquet, json, or xlsx files in {workspace}."
        )
    existing = _existing_names(workspace) if merge else set()
    to_add = [p for p in discovered if p.name not in existing]
    skipped = [p.name for p in discovered if p.name in existing]
    if not to_add:
        return ApplyResult(added=[], skipped=skipped)
    _write_sources(workspace, to_add)
    from datacharter.contracts.loader import load_charter

    loaded = {s.name: s for s in load_charter(workspace).sources}
    if engine is not None:
        for item in to_add:
            src = loaded.get(item.name)
            if src is not None:
                engine.add_source(src)
        pii = _write_pii_for(workspace, to_add, _scan_pii_sync(engine))
    else:
        pii = _attach_and_scan_pii(workspace, to_add)
    return ApplyResult(added=to_add, skipped=skipped, pii=pii)
