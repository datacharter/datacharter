"""Eval suites: agent-accuracy questions + assertions, versioned with the contract.

Suites live in `evals/*.yaml`. Assertions bind to the agent's answer text, the
SQL it ran, or the last query's scalar result — never to agent-named columns.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

__all__ = [
    "EvalAssertion", "EvalCase", "EvalSuite", "EvalError",
    "load_suites", "parse_suite", "validate_assertion", "check_assertion",
    "ASSERTION_TYPES",
]

EVALS_DIR = "evals"
ASSERTION_TYPES = {
    "answer_contains", "answer_matches", "sql_contains", "sql_excludes", "result_scalar",
}


class EvalError(Exception):
    """evals/*.yaml problem, phrased so the user knows exactly what to fix."""


class EvalAssertion(BaseModel):
    type: str
    value: str | None = None
    pattern: str | None = None
    equals: float | None = None
    tolerance: float | None = None
    column: str | None = None


class EvalCase(BaseModel):
    question: str
    expect: list[EvalAssertion] = Field(default_factory=list)
    expected_answer: str | None = None


class EvalSuite(BaseModel):
    name: str
    cases: list[EvalCase]


def validate_assertion(a: EvalAssertion, ctx: str) -> None:
    if a.type not in ASSERTION_TYPES:
        raise EvalError(f"{ctx}: unknown assertion type {a.type!r}")
    if a.type in ("answer_contains", "sql_contains", "sql_excludes") and not a.value:
        raise EvalError(f"{ctx}: {a.type} needs a 'value'")
    if a.type == "answer_matches" and not a.pattern:
        raise EvalError(f"{ctx}: answer_matches needs a 'pattern'")
    if a.type == "result_scalar" and a.equals is None:
        raise EvalError(f"{ctx}: result_scalar needs 'equals'")


def parse_suite(name: str, text: str) -> EvalSuite:
    """Parse and validate one suite's YAML text (also the save-time validator)."""
    ctx = f"{name}.yaml"
    try:
        raw: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise EvalError(f"{ctx}: invalid YAML: {exc}") from None
    cases_raw = (raw or {}).get("cases") or []
    if not isinstance(cases_raw, list):
        raise EvalError(f"{ctx}: 'cases' must be a list.")
    cases: list[EvalCase] = []
    for i, c in enumerate(cases_raw):
        try:
            case = EvalCase(**c)
        except (ValidationError, TypeError) as exc:
            raise EvalError(f"{ctx}: case {i}: {exc}") from None
        for j, a in enumerate(case.expect):
            validate_assertion(a, f"{ctx}: case {i}: expect[{j}]")
        cases.append(case)
    return EvalSuite(name=name, cases=cases)


def load_suites(workspace: Path | str) -> list[EvalSuite]:
    root = Path(workspace) / EVALS_DIR
    if not root.is_dir():
        return []
    return [parse_suite(f.stem, f.read_text()) for f in sorted(root.glob("*.yaml"))]


def check_assertion(a: EvalAssertion, *, answer: str, sqls: list[str], scalar: Any) -> bool:
    ans = answer.lower()
    sql_blob = " ".join(sqls).lower()
    if a.type == "answer_contains":
        return (a.value or "").lower() in ans
    if a.type == "answer_matches":
        return re.search(a.pattern or "", answer) is not None
    if a.type == "sql_contains":
        return (a.value or "").lower() in sql_blob
    if a.type == "sql_excludes":
        return (a.value or "").lower() not in sql_blob
    if a.type == "result_scalar":
        if scalar is None:
            return False
        try:
            return abs(float(scalar) - float(a.equals)) <= float(a.tolerance or 0.0)
        except (TypeError, ValueError):
            return False
    return False
