import pytest

from datacharter.contracts.evals import (
    EvalAssertion,
    EvalError,
    check_assertion,
    load_suites,
    validate_assertion,
)


def test_load_suite_from_yaml(tmp_path):
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "analytics.yaml").write_text(
        "version: 1\n"
        "cases:\n"
        "  - question: 'net revenue by region?'\n"
        "    expect:\n"
        "      - { type: sql_contains, value: refunded }\n"
        "      - { type: answer_matches, pattern: 'EU' }\n"
        "    expected_answer: 'EU leads'\n"
    )
    suites = load_suites(tmp_path)
    assert [s.name for s in suites] == ["analytics"]
    case = suites[0].cases[0]
    assert case.question.startswith("net revenue")
    assert case.expected_answer == "EU leads"
    assert case.expect[0].type == "sql_contains"


def test_no_evals_dir_is_empty(tmp_path):
    assert load_suites(tmp_path) == []


def test_unknown_assertion_type_rejected(tmp_path):
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "s.yaml").write_text(
        "version: 1\ncases:\n  - question: q\n    expect:\n      - { type: bogus }\n"
    )
    with pytest.raises(EvalError, match="bogus"):
        load_suites(tmp_path)


def test_missing_required_field_rejected(tmp_path):
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "s.yaml").write_text(
        "version: 1\ncases:\n  - question: q\n    expect:\n      - { type: sql_contains }\n"
    )
    with pytest.raises(EvalError, match="value"):
        load_suites(tmp_path)


@pytest.mark.parametrize("a,ok", [
    ({"type": "answer_contains", "value": "eu"}, True),
    ({"type": "answer_contains", "value": "zz"}, False),
    ({"type": "answer_matches", "pattern": r"\bEU\b"}, True),
    ({"type": "sql_contains", "value": "refunded"}, True),
    ({"type": "sql_contains", "value": "email"}, False),
    ({"type": "sql_excludes", "value": "email"}, True),
    ({"type": "sql_excludes", "value": "refunded"}, False),
])
def test_check_text_and_sql_assertions(a, ok):
    got = check_assertion(
        EvalAssertion(**a),
        answer="EU leads with the most revenue",
        sqls=["SELECT sum(amount) FROM sales WHERE refunded = false"],
        scalar=None,
    )
    assert got is ok


@pytest.mark.parametrize("scalar,equals,tol,ok", [
    (512.24, 512.24, 0.01, True),
    (512.20, 512.24, 0.01, False),
    (512.24, 512.0, 1.0, True),
    (None, 512.24, 0.01, False),
])
def test_check_result_scalar(scalar, equals, tol, ok):
    a = EvalAssertion(type="result_scalar", equals=equals, tolerance=tol)
    assert check_assertion(a, answer="", sqls=[], scalar=scalar) is ok


def test_validate_assertion_direct():
    with pytest.raises(EvalError, match="pattern"):
        validate_assertion(EvalAssertion(type="answer_matches"), "ctx")
