"""CRUD helpers for charter sources: keyring + charter.yaml + live engine."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from datacharter.contracts import secrets as secretstore
from datacharter.contracts.resolve import SecretResolver
from datacharter.contracts.writer import remove_source as write_remove
from datacharter.contracts.writer import upsert_source
from datacharter.engine.session import Engine
from datacharter.models import CONNECTOR_TYPES, Source, SourceType

__all__ = [
    "SourceForm",
    "resolved_source",
    "charter_body",
    "create_source",
    "update_source",
    "delete_source",
    "probe_source",
]


class SourceForm(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")
    type: SourceType
    connection: dict[str, str | int] = Field(default_factory=dict)
    password: str | None = None
    path: str | None = None
    tables: list[str] = Field(default_factory=list)
    pii: dict[str, list[str]] = Field(default_factory=dict)
    max_rows: int | None = Field(default=None, gt=0)


def _password_ref(name: str) -> str:
    return secretstore.secret_ref_name(name, "password")


def resolved_source(form: SourceForm, password: str | None) -> Source:
    """In-memory Source with the *resolved* credential for engine registration."""
    creds = {"password": password} if password else {}
    return Source(
        name=form.name,
        type=form.type,
        connection=form.connection,
        credentials=creds,
        path=form.path,
        tables=form.tables,
        pii=form.pii,
        max_rows=form.max_rows,
    )


def charter_body(form: SourceForm) -> dict:
    """The charter.yaml entry — credential as a ${NAME} ref, never a literal."""
    body: dict = {"type": form.type.value}
    if form.connection:
        body["connection"] = dict(form.connection)
    if form.password is not None:
        body["credentials"] = {"password": "${" + _password_ref(form.name) + "}"}
    if form.path:
        body["path"] = form.path
    if form.tables:
        body["tables"] = list(form.tables)
    if form.pii:
        body["pii"] = {k: list(v) for k, v in form.pii.items()}
    if form.max_rows is not None:
        body["max_rows"] = form.max_rows
    return body


def _effective_password(workspace: Path, form: SourceForm) -> str | None:
    """Password to use: the typed one, else the stored keyring value (edit-blank)."""
    if form.password:
        return form.password
    if form.type in CONNECTOR_TYPES or "user" in form.connection:
        return SecretResolver(workspace).resolve_optional(_password_ref(form.name))
    return None


def create_source(
    engine: Engine, workspace: Path, form: SourceForm, *, apply_to_engine: bool = True
) -> None:
    if form.password:
        secretstore.store_secret(_password_ref(form.name), form.password)
    if apply_to_engine:
        try:
            engine.add_source(resolved_source(form, _effective_password(workspace, form)))
        except Exception:
            if form.password:
                secretstore.delete_secret(_password_ref(form.name))
            raise
    upsert_source(workspace, form.name, charter_body(form))


def update_source(engine: Engine, workspace: Path, form: SourceForm) -> None:
    if form.password:
        secretstore.store_secret(_password_ref(form.name), form.password)
    engine.remove_source(form.name)
    engine.add_source(resolved_source(form, _effective_password(workspace, form)))
    body = charter_body(form)
    # On edit-blank, keep the ${NAME} ref only if a secret is actually stored.
    if form.password is None and _effective_password(workspace, form):
        body["credentials"] = {"password": "${" + _password_ref(form.name) + "}"}
    upsert_source(workspace, form.name, body)


def delete_source(engine: Engine, workspace: Path, name: str) -> None:
    engine.remove_source(name)
    write_remove(workspace, name)
    secretstore.delete_secret(secretstore.secret_ref_name(name, "password"))


def probe_source(engine: Engine, workspace: Path, form: SourceForm) -> None:
    engine.test_source(resolved_source(form, _effective_password(workspace, form)))
