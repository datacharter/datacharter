"""Differential-privacy query mode: add calibrated Laplace noise to aggregate
answers and spend from a per-workspace privacy budget.

The threat this closes: an agent chains "safe" aggregates — count here, count
there — to difference out a single individual. Bounded noise on every aggregate,
metered by a finite ε budget, makes that attack pay a cost it runs out of.

Scope, stated honestly (DP done wrong is false security):
- The Laplace mechanism samples noise ∝ sensitivity/ε. We support **COUNT**
  (sensitivity 1) and **SUM** (sensitivity = a caller-provided value bound, since
  DuckDB cannot know your column's range). Each individual is assumed to affect at
  most one output row — *bounded contribution*. Use it for grouped/global counts
  and sums, not for row-level SELECTs.
- The budget is a simple sequential composition ledger: ε spends add up; when the
  workspace total would exceed the cap, the query is refused. This is the honest,
  conservative accounting — no advanced composition credit.
"""

from __future__ import annotations

import json
import math
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "DPError", "laplace", "is_aggregate", "aggregate_kinds", "group_by_keys",
    "strip_sql_noise", "privatize_row", "Budget", "BUDGET_FILE",
]

BUDGET_FILE = "dp_budget.json"


class DPError(Exception):
    """A misuse of DP mode the caller should fix (non-aggregate query, budget spent)."""


def _uniform() -> float:
    """A uniform draw in (0, 1) from a cryptographic source — noise must not be
    predictable, or an attacker averages it away."""
    return (secrets.randbits(53) + 1) / (2 ** 53 + 1)


def laplace(scale: float, rng=None) -> float:
    """Sample Laplace(0, scale) via inverse-CDF. `rng` (a callable → uniform in
    (0,1)) is injectable so tests are deterministic; default is cryptographic."""
    draw = rng or _uniform
    u = draw() - 0.5
    return -scale * math.copysign(1.0, u) * math.log(1.0 - 2.0 * abs(u))


_AGG_TOKENS = ("count(", "sum(", "avg(", "min(", "max(", "group by")
# COUNT gets sensitivity 1; SUM needs a caller bound; AVG/MIN/MAX are unbounded-
# sensitivity under add/remove and are not supported by this simple mechanism.
_SUM_FN = re.compile(r"\bsum\s*\(", re.IGNORECASE)
_COUNT_FN = re.compile(r"\bcount\s*\(", re.IGNORECASE)
_UNSUPPORTED_FN = re.compile(r"\b(avg|min|max|median|quantile|stddev|var)\s*\(", re.IGNORECASE)
_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING_LIT = re.compile(r"'(?:[^']|'')*'")
_GROUP_BY = re.compile(r"\bgroup\s+by\b(.*?)(?:\border\s+by\b|\bhaving\b|\blimit\b|$)",
                       re.IGNORECASE | re.DOTALL)


def strip_sql_noise(sql: str) -> str:
    """Remove comments and string literals so token checks can't be fooled by an
    aggregate keyword hidden in a comment or a quoted value."""
    s = _BLOCK_COMMENT.sub(" ", sql)
    s = _LINE_COMMENT.sub(" ", s)
    return _STRING_LIT.sub("''", s)


def is_aggregate(sql: str | None) -> bool:
    """True when the query has an aggregate function or GROUP BY — checked against
    the comment/literal-stripped text, so `SELECT email FROM t -- sum(` is *not*
    treated as an aggregate. Guards against pointing DP at row-level data."""
    if not sql:
        return False
    low = strip_sql_noise(sql).lower()
    return any(tok in low for tok in _AGG_TOKENS)


def group_by_keys(sql: str) -> set[str]:
    """Lowercased bare column names in the GROUP BY clause — these are grouping
    keys (including numeric ids), never aggregate outputs, so they pass through
    un-noised."""
    m = _GROUP_BY.search(strip_sql_noise(sql))
    if not m:
        return set()
    keys: set[str] = set()
    for part in m.group(1).split(","):
        tok = part.strip().split()[0] if part.strip() else ""
        # A bare or table-qualified column; skip positional/expression keys.
        col = tok.rsplit(".", 1)[-1]
        if col.isidentifier():
            keys.add(col.lower())
    return keys


def aggregate_kinds(sql: str) -> dict:
    """Which aggregate families the (noise-stripped) query uses."""
    s = strip_sql_noise(sql)
    return {
        "count": bool(_COUNT_FN.search(s)),
        "sum": bool(_SUM_FN.search(s)),
        "unsupported": bool(_UNSUPPORTED_FN.search(s)),
    }


def privatize_row(
    values: list, numeric_cols: set[int], *, epsilon: float, sensitivity: float,
    non_negative_int: bool, rng=None,
) -> list:
    """Return the row with Laplace noise added to each numeric aggregate cell.

    scale = sensitivity/ε. COUNT cells are rounded to a non-negative integer; SUM
    cells keep their fractional noise. Group-key (non-numeric) cells pass through."""
    scale = sensitivity / epsilon
    out = list(values)
    for i in numeric_cols:
        v = values[i]
        if v is None:
            continue
        noised = float(v) + laplace(scale, rng)
        if non_negative_int:
            out[i] = max(0, round(noised))
        else:
            out[i] = round(noised, 4)
    return out


@dataclass
class Budget:
    """Sequential-composition ε ledger persisted under .datacharter/."""

    path: Path
    cap: float
    spent: float = 0.0
    queries: int = 0

    @classmethod
    def load(cls, ws: Path, cap: float | None = None) -> Budget:
        """Load the ledger. `cap` overrides the workspace cap; when None, the cap
        persisted on first use is honored (so a later run without `--budget` does
        not silently reset the ceiling), defaulting to 5.0 if never set."""
        path = ws / ".datacharter" / BUDGET_FILE
        if path.exists():
            data = json.loads(path.read_text())
            resolved = cap if cap is not None else float(data.get("cap", 5.0))
            return cls(path, resolved, float(data.get("spent", 0.0)),
                       int(data.get("queries", 0)))
        return cls(path, cap if cap is not None else 5.0, 0.0, 0)

    @property
    def remaining(self) -> float:
        return max(0.0, self.cap - self.spent)

    def check(self, epsilon: float) -> None:
        """Raise if this spend would exceed the cap — the refusal that gives ε teeth."""
        if epsilon <= 0:
            raise DPError("epsilon must be > 0.")
        if self.spent + epsilon > self.cap + 1e-9:
            raise DPError(
                f"privacy budget exhausted: {self.remaining:.3f} of ε={self.cap} left, "
                f"query asks for {epsilon}. Raise --budget or --reset to start over."
            )

    def spend(self, epsilon: float) -> None:
        self.spent += epsilon
        self.queries += 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(
            {"spent": self.spent, "queries": self.queries, "cap": self.cap}, indent=2
        ))

    def reset(self) -> None:
        """Zero the spend but persist the cap, so the announced ceiling is the one
        that actually applies to the next run (a reset with `--budget` sets it)."""
        self.spent, self.queries = 0.0, 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(
            {"spent": 0.0, "queries": 0, "cap": self.cap}, indent=2
        ))
