import dataclasses

from datacharter.agent.eval_runner import CaseOutcome, CaseResult, RunRecord
from datacharter.agent.eval_store import load_history, regression_diff, save_run


def _record(q_pass):
    cases = [
        CaseResult(
            question=q,
            with_guides=CaseOutcome(passed=p, answer="", sqls=[], scalar=None, assertions=[]),
        )
        for q, p in q_pass.items()
    ]
    rate = sum(1 for p in q_pass.values() if p) / (len(q_pass) or 1)
    return RunRecord(
        suite="s", mode="plain", samples=1, overall={"with_guides": rate}, cases=cases
    )


def test_save_and_load_history(tmp_path):
    save_run(tmp_path, _record({"a": True, "b": False}))
    save_run(tmp_path, _record({"a": True, "b": True}))
    hist = load_history(tmp_path)
    assert len(hist) == 2
    assert hist[-1]["overall"]["with_guides"] == 1.0


def test_regression_diff_flags_newly_failing():
    prev = _record({"a": True, "b": True})
    curr = _record({"a": True, "b": False})
    diff = regression_diff(dataclasses.asdict(prev), dataclasses.asdict(curr))
    assert diff == ["b"]
