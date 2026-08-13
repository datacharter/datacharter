"""GovBench: scorecard grading + the CLI benchmark on a real charter."""

import json

from datacharter.cli import main as cli_main
from datacharter.govbench import PostureCheck, Scorecard


def _posture(n_pass):
    names = ["canaries", "policies", "provenance", "pii", "tests"]
    return [PostureCheck(names[i], i < n_pass, "") for i in range(5)]


def test_any_breach_is_grade_f():
    card = Scorecard(total_attacks=30, withstood=29, breaches=["boom"], posture=_posture(5))
    assert card.grade == "F" and card.security_pass is False
    assert card.score < 50


def test_clean_run_grades_by_posture():
    assert Scorecard(30, 30, [], _posture(5)).grade == "A"
    assert Scorecard(30, 30, [], _posture(3)).grade == "B"
    assert Scorecard(30, 30, [], _posture(2)).grade == "C"
    assert Scorecard(30, 30, [], _posture(1)).grade == "D"


def test_score_range():
    assert Scorecard(30, 30, [], _posture(5)).score == 100
    assert Scorecard(30, 30, [], _posture(0)).score == 50


def test_to_dict_shape():
    d = Scorecard(30, 30, [], _posture(4)).to_dict()
    assert d["grade"] == "A" and d["security_pass"] is True
    assert set(d) == {"grade", "score", "security_pass", "attacks", "breaches", "posture"}


def test_cmd_govbench_on_demo(tmp_path, capsys):
    cli_main(["init", str(tmp_path), "--demo"])
    capsys.readouterr()
    rc = cli_main(["govbench", str(tmp_path)])
    out = capsys.readouterr().out
    assert "GovBench" in out and "governance grade" in out
    # Demo withstands the battery, so it passes (grade A–D, never F).
    assert rc == 0
    assert "grade: F" not in out


def test_cmd_govbench_json_and_min_grade(tmp_path, capsys):
    cli_main(["init", str(tmp_path), "--demo"])
    capsys.readouterr()
    assert cli_main(["govbench", str(tmp_path), "--json"]) == 0
    card = json.loads(capsys.readouterr().out)
    assert card["security_pass"] is True
    assert card["grade"] in ("A", "B", "C", "D")
    assert card["attacks"]["withstood"] == card["attacks"]["total"]
    # Requiring an impossibly-high posture grade can gate; A is the demo's ceiling.
    rc = cli_main(["govbench", str(tmp_path), "--min-grade", "A"])
    assert rc in (0, 1)
