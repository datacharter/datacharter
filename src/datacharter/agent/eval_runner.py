"""Run eval suites through the existing Agent and score the results."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from datacharter.agent.loop import Agent, AgentConfig
from datacharter.agent.tools import ToolBox
from datacharter.contracts.evals import EvalCase, EvalSuite, check_assertion


@dataclass
class AssertionOutcome:
    type: str
    passed: bool


@dataclass
class CaseOutcome:
    passed: bool
    answer: str
    sqls: list[str]
    scalar: Any
    assertions: list[AssertionOutcome] = field(default_factory=list)
    #: Set when the agent errored (endpoint down, LLM failure) — the case was
    #: never actually evaluated, which is a different fact than "failed".
    error: str | None = None


@dataclass
class CaseResult:
    question: str
    with_guides: CaseOutcome
    without_guides: CaseOutcome | None = None


@dataclass
class RunRecord:
    suite: str
    mode: str
    samples: int
    overall: dict
    cases: list[CaseResult]


def _scalar_from_tool_result(detail: str) -> Any:
    """The single cell of a 1x1 query result, else None."""
    try:
        payload = json.loads(detail)
    except (ValueError, TypeError):
        return None
    rows = payload.get("rows")
    if isinstance(rows, list) and len(rows) == 1 and len(rows[0]) == 1:
        return rows[0][0]
    return None


async def run_case(agent: Agent, question: str) -> tuple[str, list[str], Any, str | None]:
    answer_parts: list[str] = []
    sqls: list[str] = []
    scalar: Any = None
    error: str | None = None
    async for ev in agent.run(question):
        if ev.kind == "text":
            answer_parts.append(ev.text)
        elif ev.kind == "tool_call" and ev.sql:
            sqls.append(ev.sql)
        elif ev.kind == "tool_result" and ev.tool == "query":
            scalar = _scalar_from_tool_result(ev.detail)
        elif ev.kind == "error":
            # The agent never finished — score_case on a partial answer would
            # report "failed" (or "0% passed") for what is really an outage.
            error = ev.detail or "agent error"
            break
        elif ev.kind == "done":
            break
    return "".join(answer_parts), sqls, scalar, error


def score_case(case: EvalCase, answer: str, sqls: list[str], scalar: Any) -> CaseOutcome:
    outcomes = [
        AssertionOutcome(
            type=a.type, passed=check_assertion(a, answer=answer, sqls=sqls, scalar=scalar)
        )
        for a in case.expect
    ]
    return CaseOutcome(
        passed=all(o.passed for o in outcomes),
        answer=answer, sqls=sqls, scalar=scalar, assertions=outcomes,
    )


_JUDGE_SYSTEM = (
    "You grade whether an ANSWER is consistent with the EXPECTED answer for a "
    "QUESTION about a dataset. Reply with exactly one word: PASS or FAIL."
)


async def judge_answer(llm, question: str, expected: str, answer: str) -> bool:
    """One LLM call (no tools) grading the agent's answer against the reference."""
    messages = [
        {"role": "system", "content": _JUDGE_SYSTEM},
        {
            "role": "user",
            "content": (
                f"QUESTION: {question}\nEXPECTED: {expected}\nANSWER: {answer}\n\n"
                "Is the ANSWER consistent with EXPECTED? Reply PASS or FAIL."
            ),
        },
    ]
    text = ""
    async for delta in llm.stream(messages, []):
        if delta.text:
            text += delta.text
    verdict = text.strip().upper()
    return "PASS" in verdict and "FAIL" not in verdict


async def _run_and_score(
    case: EvalCase, toolbox: ToolBox, llm, samples: int, judge: bool = False
) -> CaseOutcome:
    """Run one case `samples` times; passed = majority. Returns the last run's detail."""
    passes = 0
    last: CaseOutcome | None = None
    for _ in range(max(1, samples)):
        agent = Agent(toolbox, AgentConfig(llm=llm))
        answer, sqls, scalar, error = await run_case(agent, case.question)
        if error is not None:
            last = CaseOutcome(
                passed=False, answer=answer, sqls=sqls, scalar=scalar, error=error
            )
            continue
        if not case.expect and not judge:
            # An `expected_answer`-only case can ONLY be graded by the judge —
            # scoring it against an empty assertion list is `all([])` == True,
            # a silent 100% pass that verified nothing (F-3's failure class).
            last = CaseOutcome(
                passed=False, answer=answer, sqls=sqls, scalar=scalar,
                error="expected_answer requires --judge to grade; not evaluated",
            )
            continue
        last = score_case(case, answer, sqls, scalar)
        if judge and case.expected_answer:
            verdict = await judge_answer(llm, case.question, case.expected_answer, answer)
            last.assertions.append(AssertionOutcome(type="judge", passed=verdict))
            last.passed = last.passed and verdict
        passes += 1 if last.passed else 0
    assert last is not None
    if last.error is None:
        last.passed = passes * 2 >= max(1, samples)  # majority
    return last


async def run_suite(
    suite: EvalSuite,
    toolbox: ToolBox,
    *,
    llm,
    toolbox_off: ToolBox | None = None,
    samples: int = 1,
    judge: bool = False,
) -> RunRecord:
    compare = toolbox_off is not None
    results: list[CaseResult] = []
    for case in suite.cases:
        on = await _run_and_score(case, toolbox, llm, samples, judge)
        off = await _run_and_score(case, toolbox_off, llm, samples, judge) if compare else None
        results.append(CaseResult(question=case.question, with_guides=on, without_guides=off))
    n = len(results) or 1
    on_rate = sum(1 for r in results if r.with_guides.passed) / n
    overall = {"with_guides": on_rate}
    errored = sum(1 for r in results if r.with_guides.error is not None) + sum(
        1 for r in results if r.without_guides and r.without_guides.error is not None
    )
    if errored:
        overall["errored"] = errored
    if compare:
        off_rate = sum(1 for r in results if r.without_guides and r.without_guides.passed) / n
        overall["without_guides"] = off_rate
        overall["lift"] = on_rate - off_rate
    return RunRecord(
        suite=suite.name,
        mode="compare-guides" if compare else "plain",
        samples=samples, overall=overall, cases=results,
    )
