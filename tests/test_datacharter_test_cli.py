"""`datacharter test` runs charter assertions and sets a CI exit code."""

from datacharter.cli import main


def _write(tmp_path, with_failing: bool):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "o.csv").write_text("id,total\n1,10\n2,-5\n")
    charter = (
        "version: 1\nsources:\n  o:\n    type: csv\n    path: data/o.csv\n"
        "tests:\n"
        "  id_not_null:\n    type: not_null\n    relation: o\n    column: id\n"
    )
    if with_failing:
        charter += (
            '  nonneg:\n    type: expression\n    relation: o\n'
            '    expression: "total >= 0"\n'
        )
    (tmp_path / "charter.yaml").write_text(charter)


def test_all_pass_exits_zero(tmp_path, capsys):
    _write(tmp_path, with_failing=False)
    assert main(["test", str(tmp_path)]) == 0
    assert "id_not_null" in capsys.readouterr().out


def test_failure_exits_nonzero(tmp_path, capsys):
    _write(tmp_path, with_failing=True)  # nonneg fails on the -5 row
    assert main(["test", str(tmp_path)]) == 1
    assert "nonneg" in capsys.readouterr().out


def test_select_one(tmp_path, capsys):
    _write(tmp_path, with_failing=True)
    assert main(["test", str(tmp_path), "--select", "id_not_null"]) == 0
    out = capsys.readouterr().out
    assert "id_not_null" in out and "nonneg" not in out
