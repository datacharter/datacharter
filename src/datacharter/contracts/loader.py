"""charter.yaml loader: validation with actionable errors + D9 portability lint."""

from __future__ import annotations

import re
from pathlib import Path, PureWindowsPath
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from datacharter.contracts.datatests import DataTest
from datacharter.contracts.guides import load_guides
from datacharter.contracts.metrics import Metric, MetricJoin
from datacharter.contracts.resolve import FULL_REF, SecretResolver, UnresolvedReference
from datacharter.models import CONNECTOR_TYPES, FILE_TYPES, Source, SourceType

__all__ = ["Charter", "CharterError", "load_charter"]

CHARTER_FILE = "charter.yaml"
SUPPORTED_VERSION = 1

# Keys whose values are credential-shaped and must be ${NAME} references (D7).
_CREDENTIAL_KEY = re.compile(r"(password|passwd|secret|token|passphrase|api_key)$|(^|_)key$")


from datacharter.contracts.loader_errors import CharterError  # noqa: E402 (re-export)


class Charter(BaseModel):
    version: int
    sources: list[Source]
    warnings: list[str]
    metrics: list[Metric] = Field(default_factory=list)
    tests: list[DataTest] = Field(default_factory=list)
    #: Agent-access overrides for `local.*` snapshot relations (same shape as a
    #: source's `agent_access`: {source?, tables?, columns?}). `on`=real, `off`=masked.
    local_access: dict = Field(default_factory=dict)
    #: Concatenated workspace guides (guides/*.md) — agent-surface context.
    guides: str = ""
    #: Flight-recorder audit of agent access; on by default (`audit: off` disables).
    audit_enabled: bool = True
    #: Canary tripwires: None = off (default), "block" or "log" when enabled.
    canary_mode: str | None = None
    #: Plain-english policies per relation (aggregate_only / k-anonymity / joins).
    policies: dict = Field(default_factory=dict)


def load_charter(
    workspace: Path | str, filename: str = CHARTER_FILE, *, lenient_secrets: bool = False
) -> Charter:
    """Load, validate, and resolve a workspace charter.

    `lenient_secrets` keeps unresolved `${NAME}` references as placeholders
    instead of erroring — for `access diff`, which reviews the governance
    surface (never secret values) and must run in CI without credentials."""
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

    # Source-level governance keys at the top level would be silently ignored —
    # a user who copies them there believes masking/filters are on when nothing
    # is enforced. Fail closed at the config layer instead.
    for key in ("agent_access", "row_filters", "pii", "context", "tables"):
        if key in raw:
            raise CharterError(
                f"{filename}: '{key}' is a source-level field and has no effect at "
                f"the top level — move it under the source it applies to "
                f"(sources.<name>.{key})."
            )
    # Whitelist, not blacklist: a typo'd governance key (`polices:`, `canry:`)
    # that is silently dropped looks enabled while enforcing nothing.
    _reject_unknown_keys(raw, _TOP_LEVEL_KEYS, filename)

    resolver = SecretResolver(workspace, lenient=lenient_secrets)
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
    _validate_access_block(local_access, f"{filename}: local_access")

    audit_raw = raw.get("audit", True)
    if audit_raw in (False, "off"):
        audit_enabled = False
    elif audit_raw in (True, "on"):
        audit_enabled = True
    else:
        raise CharterError(f"{filename}: 'audit' must be on/off (got {audit_raw!r}).")

    canary_raw = raw.get("canary")
    if canary_raw in (None, False, "off"):
        canary_mode: str | None = None
    elif canary_raw in (True, "on"):
        canary_mode = "block"
    elif isinstance(canary_raw, dict) and canary_raw.get("mode") in ("block", "log"):
        canary_mode = canary_raw["mode"]
    else:
        raise CharterError(
            f"{filename}: 'canary' must be on/off or {{mode: block|log}} (got {canary_raw!r})."
        )

    from datacharter.contracts.policies import parse_policies

    policies = parse_policies(raw.get("policies") or {})

    return Charter(
        version=version, sources=sources, warnings=warnings, metrics=metrics,
        tests=tests, local_access=local_access, guides=load_guides(workspace),
        audit_enabled=audit_enabled, canary_mode=canary_mode, policies=policies,
    )


def _build_metric(name: str, body: Any, filename: str) -> Metric:
    if not isinstance(body, dict):
        raise CharterError(f"{filename}: metrics.{name} must be a mapping.")
    _reject_unknown_keys(body, _METRIC_KEYS, f"{filename}: metrics.{name}")
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
    _reject_unknown_keys(body, _TEST_KEYS, f"{filename}: tests.{name}")
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


_TOP_LEVEL_KEYS = {
    "version", "sources", "metrics", "tests", "local_access",
    "audit", "canary", "policies",
}
_SOURCE_KEYS = {
    "type", "connection", "credentials", "path", "tables", "pii",
    "agent_access", "row_filters", "context", "max_rows",
}
_METRIC_KEYS = {"relation", "expression", "dimensions", "joins", "time_column"}
_TEST_KEYS = {"type", "relation", "column", "columns", "values", "min", "max", "expression"}


def _reject_unknown_keys(body: dict, allowed: set, ctx: str) -> None:
    """A typo'd governance key that is silently dropped looks enabled while
    enforcing nothing — the exact failure class of the top-level-key bug.
    Fail closed with the spelling that would have worked."""
    unknown = sorted(set(body) - allowed)
    if unknown:
        raise CharterError(
            f"{ctx}: unknown key(s) {', '.join(map(repr, unknown))} — "
            f"allowed: {', '.join(sorted(allowed))}."
        )


def _build_source(name: str, body: Any, resolver: SecretResolver, warnings: list[str]) -> Source:
    ctx = f"sources.{name}"
    if not isinstance(body, dict):
        raise CharterError(f"{ctx}: must be a mapping.")
    _reject_unknown_keys(body, _SOURCE_KEYS, ctx)
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

    _validate_access_block(body.get("agent_access") or {}, f"{ctx}.agent_access")

    context_raw = body.get("context") or {}
    if not isinstance(context_raw, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in context_raw.items()
    ):
        raise CharterError(f"{ctx}.context: must be a mapping of table -> text.")

    pii = _validate_pii_block(body.get("pii") or {}, f"{ctx}.pii")

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
            pii=pii,
            agent_access=dict(body.get("agent_access") or {}),
            row_filters=dict(body.get("row_filters") or {}),
            table_context=context_raw,
            max_rows=max_rows,
        )
    except ValidationError as exc:
        first = exc.errors()[0]
        raise CharterError(f"{ctx}: {first['loc'][0]}: {first['msg']}") from None


def _validate_pii_block(pii: Any, ctx: str) -> dict[str, list[str]]:
    """`pii: {customers: email}` must mean the email COLUMN — `list("email")`
    silently became the character list ['e','m',...] and masked nothing."""
    if not isinstance(pii, dict):
        raise CharterError(
            f"{ctx}: must be a mapping of table -> column list "
            f"(e.g. pii: {{customers: [email]}})."
        )
    out: dict[str, list[str]] = {}
    for table, cols in pii.items():
        if isinstance(cols, str):
            cols = [cols]
        if not isinstance(cols, list) or not all(isinstance(c, str) for c in cols):
            raise CharterError(
                f"{ctx}.{table}: must be a list of column names "
                f"(e.g. [email, phone]) — got {cols!r}."
            )
        out[str(table)] = [str(c) for c in cols]
    return out


def _validate_access_block(aa: Any, ctx: str) -> None:
    """Agent-access overrides must be booleans — YAML strings like `deny` would
    otherwise be truthy and silently UNMASK the column they meant to protect."""
    if not isinstance(aa, dict):
        raise CharterError(f"{ctx}: must be a mapping (source/tables/columns).")

    def _require_bool(value: Any, where: str) -> None:
        if not isinstance(value, bool):
            raise CharterError(
                f"{ctx}.{where}: must be true (agent sees real values) or false "
                f"(masked) — got {value!r}."
            )

    for key, value in aa.items():
        if key == "source":
            _require_bool(value, "source")
        elif key in ("tables", "columns"):
            if not isinstance(value, dict):
                raise CharterError(f"{ctx}.{key}: must be a mapping of name -> true/false.")
            for name, v in value.items():
                # A column override must be `table.column` — a bare `column` key
                # never matches at runtime, so it silently protects nothing.
                if key == "columns" and "." not in str(name):
                    raise CharterError(
                        f"{ctx}.columns.{name}: must be qualified as 'table.column' "
                        f"(a bare column name matches no relation and is ignored)."
                    )
                _require_bool(v, f"{key}.{name}")
        else:
            raise CharterError(
                f"{ctx}: unknown key {key!r} (allowed: source, tables, columns)."
            )


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
