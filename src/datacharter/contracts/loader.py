"""charter.yaml loader: validation with actionable errors + D9 portability lint."""

from __future__ import annotations

import re
from pathlib import Path, PureWindowsPath
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from datacharter.contracts.datatests import DataTest
from datacharter.contracts.metrics import Metric, MetricJoin
from datacharter.contracts.resolve import FULL_REF, SecretResolver, UnresolvedReference
from datacharter.models import CONNECTOR_TYPES, FILE_TYPES, Source, SourceType

__all__ = ["Charter", "CharterError", "load_charter"]

CHARTER_FILE = "charter.yaml"
SUPPORTED_VERSION = 1

# Keys whose values are credential-shaped and must be ${NAME} references (D7).
_CREDENTIAL_KEY = re.compile(r"(password|passwd|secret|token|passphrase|api_key)$|(^|_)key$")


class CharterError(Exception):
    """charter.yaml problem, phrased so the user knows exactly what to fix."""


class Charter(BaseModel):
    version: int
    sources: list[Source]
    warnings: list[str]
    metrics: list[Metric] = Field(default_factory=list)
    tests: list[DataTest] = Field(default_factory=list)
    #: Agent-access overrides for `local.*` snapshot relations (same shape as a
    #: source's `agent_access`: {source?, tables?, columns?}). `on`=real, `off`=masked.
    local_access: dict = Field(default_factory=dict)


def load_charter(workspace: Path | str, filename: str = CHARTER_FILE) -> Charter:
    """Load, validate, and resolve a workspace charter."""
    workspace = Path(workspace).resolve()
    path = workspace / filename
    if not path.exists():
        raise CharterError(f"{filename} not found in {workspace}. Run `datacharter init` to start.")
    try:
        raw: Any = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise CharterError(f"{filename} is not valid YAML: {exc}") from None
    if not isinstance(raw, dict):
        raise CharterError(f"{filename} must be a mapping with 'version' and 'sources'.")

    version = raw.get("version")
    if version != SUPPORTED_VERSION:
        raise CharterError(
            f"{filename}: unsupported version {version!r}; expected {SUPPORTED_VERSION}."
        )
    sources_raw = raw.get("sources")
    if sources_raw is None:  # a fresh `datacharter init` workspace: add sources later
        sources_raw = {}
    if not isinstance(sources_raw, dict):
        raise CharterError(f"{filename}: 'sources' must be a mapping of name -> source.")

    resolver = SecretResolver(workspace)
    warnings: list[str] = []
    sources: list[Source] = []
    for name, body in sources_raw.items():
        sources.append(_build_source(str(name), body, resolver, warnings))

    metrics_raw = raw.get("metrics") or {}
    if not isinstance(metrics_raw, dict):
        raise CharterError(f"{filename}: 'metrics' must be a mapping of name -> metric.")
    metrics = [_build_metric(str(n), b, filename) for n, b in metrics_raw.items()]

    tests_raw = raw.get("tests") or {}
    if not isinstance(tests_raw, dict):
        raise CharterError(f"{filename}: 'tests' must be a mapping of name -> test.")
    tests = [_build_test(str(n), b, filename) for n, b in tests_raw.items()]

    local_access = raw.get("local_access") or {}
    if not isinstance(local_access, dict):
        raise CharterError(f"{filename}: 'local_access' must be a mapping.")

    return Charter(
        version=version, sources=sources, warnings=warnings, metrics=metrics,
        tests=tests, local_access=local_access,
    )


def _build_metric(name: str, body: Any, filename: str) -> Metric:
    if not isinstance(body, dict):
        raise CharterError(f"{filename}: metrics.{name} must be a mapping.")
    relation, expression = body.get("relation"), body.get("expression")
    if not relation or not expression:
        raise CharterError(f"{filename}: metrics.{name} needs a 'relation' and an 'expression'.")
    try:
        return Metric(
            name=name,
            relation=str(relation),
            expression=str(expression),
            dimensions=[str(d) for d in (body.get("dimensions") or [])],
            joins=[
                MetricJoin(
                    relation=str(j.get("relation")),
                    # YAML parses a bare `on:` key as the boolean True — accept both.
                    on=str(j.get("on", j.get(True, ""))),
                    type=str(j.get("type", "inner")),
                )
                for j in (body.get("joins") or [])
            ],
            time_column=(str(body["time_column"]) if body.get("time_column") else None),
        )
    except ValidationError as exc:
        raise CharterError(f"{filename}: metrics.{name}: {exc}") from None


def _build_test(name: str, body: Any, filename: str) -> DataTest:
    if not isinstance(body, dict):
        raise CharterError(f"{filename}: tests.{name} must be a mapping.")
    try:
        return DataTest(
            name=name,
            type=str(body.get("type", "")),
            relation=str(body.get("relation", "")),
            column=(str(body["column"]) if body.get("column") else None),
            columns=[str(c) for c in (body.get("columns") or [])],
            values=list(body.get("values") or []),
            min=body.get("min"),
            max=body.get("max"),
            expression=(str(body["expression"]) if body.get("expression") else None),
        )
    except ValidationError as exc:
        raise CharterError(f"{filename}: tests.{name}: {exc}") from None


def _build_source(name: str, body: Any, resolver: SecretResolver, warnings: list[str]) -> Source:
    ctx = f"sources.{name}"
    if not isinstance(body, dict):
        raise CharterError(f"{ctx}: must be a mapping.")
    type_raw = body.get("type")
    try:
        stype = SourceType(type_raw)
    except ValueError:
        valid = ", ".join(t.value for t in SourceType)
        raise CharterError(f"{ctx}.type: {type_raw!r} is not one of: {valid}.") from None

    credentials = _resolve_credentials(ctx, body.get("credentials") or {}, resolver)
    connection = _check_connection(ctx, body.get("connection") or {})
    path_value = body.get("path")
    if path_value is not None:
        path_value = resolver.interpolate(str(path_value))
        _lint_path(ctx, path_value, stype, warnings)

    max_rows = body.get("max_rows")
    if max_rows is not None and stype not in CONNECTOR_TYPES:
        warnings.append(
            f"{ctx}.max_rows: only applies to connector sources (snowflake); "
            f"{stype.value} sources stream and ignore it."
        )

    try:
        return Source(
            name=name,
            type=stype,
            connection=connection,
            credentials=credentials,
            path=path_value,
            tables=list(body.get("tables") or []),
            pii={k: list(v) for k, v in (body.get("pii") or {}).items()},
            agent_access=dict(body.get("agent_access") or {}),
            row_filters=dict(body.get("row_filters") or {}),
            max_rows=max_rows,
        )
    except ValidationError as exc:
        first = exc.errors()[0]
        raise CharterError(f"{ctx}: {first['loc'][0]}: {first['msg']}") from None


def _resolve_credentials(ctx: str, creds: Any, resolver: SecretResolver) -> dict[str, str]:
    if not isinstance(creds, dict):
        raise CharterError(f"{ctx}.credentials: must be a mapping.")
    resolved: dict[str, str] = {}
    for key, value in creds.items():
        ref = FULL_REF.match(str(value))
        if ref is None:
            raise CharterError(
                f"{ctx}.credentials.{key}: literal values are not allowed here. "
                f"Use ${{NAME}} and store the secret in the environment, .env, "
                f"or `datacharter secrets set NAME`."
            )
        try:
            resolved[str(key)] = resolver.resolve(ref.group(1))
        except UnresolvedReference as exc:
            raise CharterError(f"{ctx}.credentials.{key}: {exc}") from None
    return resolved


def _check_connection(ctx: str, connection: Any) -> dict[str, str | int]:
    if not isinstance(connection, dict):
        raise CharterError(f"{ctx}.connection: must be a mapping.")
    for key, value in connection.items():
        if _CREDENTIAL_KEY.search(str(key)) and not FULL_REF.match(str(value)):
            raise CharterError(
                f"{ctx}.connection.{key}: credential-shaped keys belong under "
                f"'credentials:' with a ${{NAME}} reference."
            )
    return {str(k): v for k, v in connection.items()}


def _lint_path(ctx: str, value: str, stype: SourceType, warnings: list[str]) -> None:
    if stype not in FILE_TYPES and stype != SourceType.SQLITE:
        return
    if "://" in value:
        return
    if "\\" in value:
        warnings.append(f"{ctx}.path: use POSIX separators ('/') for portability (D9).")
    if Path(value).is_absolute() or PureWindowsPath(value).is_absolute():
        warnings.append(
            f"{ctx}.path: absolute path hurts portability (D9) — prefer a "
            f"workspace-relative path or a ${{VAR}} reference."
        )
