"""Run eval suites through an agent backend and score the results.

Two backends share one scoring core: the built-in LLM agent (`run_suite`) and
Claude Code (`run_suite_cc`). The core (`_run_suite`) is backend-agnostic — it
takes a `run_case_fn(question, with_guides)` and an optional judge, so majority
sampling, guide-lift comparison, and scorecard math live in exactly one place.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from datacharter.agent.loop import Agent, AgentConfig
from datacharter.agent.tools import ToolBox
from datacharter.contracts.evals import EvalCase, EvalSuite, check_assertion

#: run_case_fn(question, with_guides) -> (answer, sqls, scalar, error).
RunCaseFn = Callable[[str, bool], Awaitable["tuple[str, list[str], Any, str | None]"]]
#: judge_fn(question, expected, answer) -> pass/fail.
JudgeFn = Callable[[str, str, str], Awaitable[bool]]


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


async def _score_samples(
    case: EvalCase,
    run_one: Callable[[], Awaitable[tuple[str, list[str], Any, str | None]]],
    judge_fn: JudgeFn | None,
    samples: int,
) -> CaseOutcome:
    """Run one case `samples` times; passed = majority. Returns the last run's detail."""
    passes = 0
    last: CaseOutcome | None = None
    for _ in range(max(1, samples)):
        answer, sqls, scalar, error = await run_one()
        if error is not None:
            last = CaseOutcome(
                passed=False, answer=answer, sqls=sqls, scalar=scalar, error=error
            )
            continue
        if not case.expect and judge_fn is None:
            # An `expected_answer`-only case can ONLY be graded by the judge —
            # scoring it against an empty assertion list is `all([])` == True,
            # a silent 100% pass that verified nothing (F-3's failure class).
            last = CaseOutcome(
                passed=False, answer=answer, sqls=sqls, scalar=scalar,
                error="expected_answer requires --judge to grade; not evaluated",
            )
            continue
        last = score_case(case, answer, sqls, scalar)
        if judge_fn is not None and case.expected_answer:
            verdict = await judge_fn(case.question, case.expected_answer, answer)
            last.assertions.append(AssertionOutcome(type="judge", passed=verdict))
            last.passed = last.passed and verdict
        passes += 1 if last.passed else 0
    assert last is not None
    if last.error is None:
        last.passed = passes * 2 >= max(1, samples)  # majority
    return last


_SCALAR_UNSUPPORTED = (
    "result_scalar needs the query's result rows, which the Claude Code backend "
    "does not expose — use answer_matches / answer_contains or --judge instead."
)


async def _run_suite(
    suite: EvalSuite,
    run_case_fn: RunCaseFn,
    judge_fn: JudgeFn | None,
    *,
    compare: bool,
    samples: int,
    scalar_supported: bool = True,
) -> RunRecord:
    """Backend-agnostic core: drive every case (both guide arms when comparing),
    score with majority sampling, and assemble the scorecard. `scalar_supported`
    is False for backends that surface no result rows — a `result_scalar` case is
    then reported as errored (not a misleading fail) and its agent run skipped."""
    results: list[CaseResult] = []
    for case in suite.cases:
        if not scalar_supported and any(a.type == "result_scalar" for a in case.expect):
            unscorable = CaseOutcome(
                passed=False, answer="", sqls=[], scalar=None, error=_SCALAR_UNSUPPORTED
            )
            results.append(CaseResult(
                question=case.question, with_guides=unscorable,
                without_guides=unscorable if compare else None,
            ))
            continue
        on = await _score_samples(
            case, lambda c=case: run_case_fn(c.question, True), judge_fn, samples
        )
        off = (
            await _score_samples(
                case, lambda c=case: run_case_fn(c.question, False), judge_fn, samples
            )
            if compare
            else None
        )
        results.append(CaseResult(question=case.question, with_guides=on, without_guides=off))
    n = len(results) or 1
    on_rate = sum(1 for r in results if r.with_guides.passed) / n
    overall: dict = {"with_guides": on_rate}
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


async def run_suite(
    suite: EvalSuite,
    toolbox: ToolBox,
    *,
    llm,
    toolbox_off: ToolBox | None = None,
    samples: int = 1,
    judge: bool = False,
) -> RunRecord:
    """Score a suite with the built-in LLM agent. Guides on/off = two toolboxes."""
    compare = toolbox_off is not None

    async def run_case_fn(question: str, with_guides: bool):
        box = toolbox if with_guides else toolbox_off
        assert box is not None  # off arm only runs when compare (toolbox_off set)
        agent = Agent(box, AgentConfig(llm=llm))
        return await run_case(agent, question)

    judge_fn: JudgeFn | None = (
        (lambda q, e, a: judge_answer(llm, q, e, a)) if judge else None
    )
    return await _run_suite(
        suite, run_case_fn, judge_fn, compare=compare, samples=samples
    )


# --- Claude Code backend -----------------------------------------------------
# The agent-under-test drives the real Claude Code (pinned to `agent_model`)
# through the same governed MCP server the app serves; the judge is a SEPARATE,
# stronger model with no data tools. Guides on/off is the system-prompt context,
# not a toolbox swap — the governed surface is identical for both arms.


async def run_case_cc(
    question: str,
    serve_url: str,
    *,
    deny: list[str] | None,
    guides: str | None,
    with_guides: bool,
    model: str | None,
) -> tuple[str, list[str], Any, str | None]:
    """One eval case through Claude Code — a fresh (non-resumed) turn per case."""
    from datacharter.agent import claude_code as cc

    context = cc.system_context(guides if with_guides else None)
    answer_parts: list[str] = []
    sqls: list[str] = []
    error: str | None = None
    async for ev in cc.run_turn(
        question, serve_url, session_id=None, deny=deny, context=context, model=model
    ):
        kind = ev["kind"]
        if kind == "text":
            answer_parts.append(ev["text"])
        elif kind == "tool_call" and ev.get("sql"):
            sqls.append(ev["sql"])
        elif kind == "error":
            error = ev.get("detail") or "Claude Code error"
            break
        elif kind == "result":
            if ev.get("is_error"):
                error = ev.get("text") or "Claude Code error"
            elif not answer_parts and ev.get("text"):
                answer_parts.append(ev["text"])
    # Claude Code surfaces no query result rows to us, so scalar assertions
    # can't be scored on this backend — sql_contains / answer_matches / judge do.
    return "".join(answer_parts), sqls, None, error


async def judge_answer_cc(question: str, expected: str, answer: str, model: str | None) -> bool:
    """Grade with a stronger Claude model that has NO data tools (text-only)."""
    from datacharter.agent import claude_code as cc

    prompt = (
        f"QUESTION: {question}\nEXPECTED: {expected}\nANSWER: {answer}\n\n"
        "Is the ANSWER consistent with EXPECTED? Reply PASS or FAIL."
    )
    text = await cc.grade(prompt, model=model, system=_JUDGE_SYSTEM)
    verdict = text.strip().upper()
    return "PASS" in verdict and "FAIL" not in verdict


async def run_suite_cc(
    suite: EvalSuite,
    *,
    serve_url: str,
    deny: list[str] | None,
    guides: str | None,
    compare: bool = False,
    samples: int = 1,
    judge: bool = False,
    agent_model: str | None = None,
    judge_model: str | None = None,
) -> RunRecord:
    """Score a suite by driving Claude Code as the agent and a stronger model as judge."""

    async def run_case_fn(question: str, with_guides: bool):
        return await run_case_cc(
            question, serve_url, deny=deny, guides=guides,
            with_guides=with_guides, model=agent_model,
        )

    judge_fn: JudgeFn | None = (
        (lambda q, e, a: judge_answer_cc(q, e, a, judge_model)) if judge else None
    )
    return await _run_suite(
        suite, run_case_fn, judge_fn, compare=compare, samples=samples,
        scalar_supported=False,
    )
