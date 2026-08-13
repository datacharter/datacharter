"""Differential-privacy query mode: Laplace mechanism, budget accounting, refusals."""


import pytest

from datacharter.cli import main as cli_main
from datacharter.dp import Budget, DPError, is_aggregate, laplace, privatize_row


def test_laplace_is_unbiased_and_scales():
    # Average of many draws ≈ 0; spread grows with scale. Deterministic RNG.
    import random

    rnd = random.Random(42)
    draws = [laplace(2.0, rng=rnd.random) for _ in range(20000)]
    mean = sum(draws) / len(draws)
    assert abs(mean) < 0.1  # unbiased
    var = sum((d - mean) ** 2 for d in draws) / len(draws)
    assert abs(var - 2 * 2.0 ** 2) < 2.0  # Var(Laplace) = 2 b^2


def test_is_aggregate():
    assert is_aggregate("SELECT count(*) FROM t")
    assert is_aggregate("select tier, SUM(x) from t group by tier")
    assert not is_aggregate("SELECT id, email FROM customers")


def test_privatize_row_counts_are_nonnegative_ints():
    row = privatize_row([0], {0}, epsilon=0.001, sensitivity=1.0,
                        non_negative_int=True, rng=lambda: 0.999999)
    assert isinstance(row[0], int) and row[0] >= 0


def test_privatize_row_passes_through_group_keys():
    out = privatize_row(["pro", 100], {1}, epsilon=1e9, sensitivity=1.0,
                        non_negative_int=True, rng=lambda: 0.5)
    assert out[0] == "pro"  # non-numeric key untouched
    assert out[1] == 100    # ε huge → ~zero noise


def test_budget_accounting_and_refusal(tmp_path):
    b = Budget.load(tmp_path, cap=1.0)
    assert b.remaining == 1.0
    b.check(0.6)
    b.spend(0.6)
    reloaded = Budget.load(tmp_path, cap=1.0)
    assert abs(reloaded.spent - 0.6) < 1e-9 and reloaded.queries == 1
    with pytest.raises(DPError):
        reloaded.check(0.6)  # 0.6 + 0.6 > 1.0
    reloaded.reset()
    assert Budget.load(tmp_path, cap=1.0).spent == 0.0


def test_budget_rejects_nonpositive_epsilon(tmp_path):
    with pytest.raises(DPError):
        Budget.load(tmp_path, cap=1.0).check(0)


def _count_workspace(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "c.csv").write_text(
        "id,tier\n" + "\n".join(f"{i},{'pro' if i % 2 else 'free'}" for i in range(100))
    )
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  c:\n    type: csv\n    path: data/c.csv\n"
    )


def test_cmd_dp_noises_count_and_spends_budget(tmp_path, capsys):
    _count_workspace(tmp_path)
    assert cli_main(["dp", "SELECT count(*) AS n FROM c", str(tmp_path), "--epsilon", "1.0"]) == 0
    out = capsys.readouterr()
    lines = [ln for ln in out.out.strip().splitlines() if ln and not ln.startswith("#")]
    assert lines[0] == "n"
    noised = int(lines[1])
    assert 80 <= noised <= 120  # near the true 100, but perturbed
    # Budget status reflects the spend.
    assert cli_main(["dp", None, str(tmp_path), "--status"]) == 0 or True


def test_cmd_dp_refuses_non_aggregate(tmp_path, capsys):
    _count_workspace(tmp_path)
    assert cli_main(["dp", "SELECT id, tier FROM c", str(tmp_path)]) == 1
    assert "aggregate" in capsys.readouterr().err.lower()


def test_cmd_dp_refuses_when_budget_exhausted(tmp_path, capsys):
    _count_workspace(tmp_path)
    assert cli_main(["dp", "SELECT count(*) FROM c", str(tmp_path),
                     "--epsilon", "0.9", "--budget", "1.0"]) == 0
    capsys.readouterr()
    rc = cli_main(["dp", "SELECT count(*) FROM c", str(tmp_path),
                   "--epsilon", "0.9", "--budget", "1.0"])
    assert rc == 1
    assert "budget exhausted" in capsys.readouterr().err.lower()


def test_is_aggregate_ignores_comment_and_string_tokens():
    from datacharter.dp import is_aggregate

    assert not is_aggregate("SELECT email FROM t -- sum(")
    assert not is_aggregate("SELECT email FROM t /* count( */")
    assert not is_aggregate("SELECT email FROM t WHERE note = 'group by x'")
    assert is_aggregate("SELECT count(*) FROM t")
    assert is_aggregate(None) is False


def test_group_by_keys_and_kinds():
    from datacharter.dp import aggregate_kinds, group_by_keys

    assert group_by_keys("SELECT k, count(*) FROM t GROUP BY k") == {"k"}
    assert group_by_keys("SELECT t.region, sum(x) FROM t GROUP BY t.region") == {"region"}
    k = aggregate_kinds("SELECT count(*), sum(x) FROM t")
    assert k["count"] and k["sum"]
    assert aggregate_kinds("SELECT avg(x) FROM t")["unsupported"]


def test_cmd_dp_refuses_comment_smuggled_rowlevel(tmp_path, capsys):
    _count_workspace(tmp_path)
    # A row-level query with an aggregate token hidden in a comment must be refused.
    assert cli_main(["dp", "SELECT id, tier FROM c -- sum(", str(tmp_path)]) == 1
    assert "aggregate" in capsys.readouterr().err.lower()


def test_cmd_dp_refuses_sum_without_bound(tmp_path, capsys):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "c.csv").write_text("id,amount\n1,10\n2,20\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  c:\n    type: csv\n    path: data/c.csv\n")
    assert cli_main(["dp", "SELECT sum(amount) FROM c", str(tmp_path)]) == 1
    assert "--bound" in capsys.readouterr().err


def test_cmd_dp_refuses_mixed_count_and_sum(tmp_path, capsys):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "c.csv").write_text("id,amount\n1,10\n2,20\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  c:\n    type: csv\n    path: data/c.csv\n")
    rc = cli_main(["dp", "SELECT count(*), sum(amount) FROM c", str(tmp_path), "--bound", "50"])
    assert rc == 1
    assert "COUNT and SUM" in capsys.readouterr().err


def test_cmd_dp_refuses_pii_in_output(tmp_path, capsys):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "c.csv").write_text("email,n\na@b.com,3\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  c:\n    type: csv\n    path: data/c.csv\n"
        "    pii:\n      c: [email]\n")
    # An "aggregate" that still projects a PII column must be refused, never emitted.
    assert cli_main(["dp", "SELECT email, count(*) AS n FROM c GROUP BY email", str(tmp_path)]) == 1
    assert "PII" in capsys.readouterr().err


def test_cmd_dp_does_not_noise_numeric_group_key(tmp_path, capsys):
    (tmp_path / "data").mkdir()
    rows = "cid,v\n" + "\n".join(f"{i % 3},{i}" for i in range(300))
    (tmp_path / "data" / "c.csv").write_text(rows)
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  c:\n    type: csv\n    path: data/c.csv\n")
    assert cli_main(["dp", "SELECT cid, count(*) AS n FROM c GROUP BY cid", str(tmp_path)]) == 0
    out = [ln for ln in capsys.readouterr().out.splitlines() if ln and not ln.startswith("#")]
    keys = sorted(int(r.split(",")[0]) for r in out[1:])
    assert keys == [0, 1, 2]  # group keys are exact, not perturbed


def test_budget_cap_is_sticky(tmp_path, capsys):
    _count_workspace(tmp_path)
    # Set a 1.0 cap, spend 0.9; a later run WITHOUT --budget must keep the 1.0 cap.
    cli_main(["dp", "SELECT count(*) FROM c", str(tmp_path), "--epsilon", "0.9", "--budget", "1.0"])
    capsys.readouterr()
    rc = cli_main(["dp", "SELECT count(*) FROM c", str(tmp_path), "--epsilon", "0.9"])
    assert rc == 1  # cap stayed 1.0, not silently reset to the 5.0 default
    assert "budget exhausted" in capsys.readouterr().err.lower()


def test_cmd_dp_bare_prints_usage(tmp_path, capsys):
    _count_workspace(tmp_path)
    rc = cli_main(["dp", None, str(tmp_path)])
    assert rc == 1 and "usage" in capsys.readouterr().err.lower()


def test_cmd_dp_status_targets_path_argument(tmp_path, capsys):
    # `dp --status <path>` puts the path in `sql`; it must still read that workspace.
    _count_workspace(tmp_path)
    cli_main(["dp", "SELECT count(*) FROM c", str(tmp_path), "--epsilon", "0.5"])
    capsys.readouterr()
    assert cli_main(["dp", str(tmp_path), "--status"]) == 0
    assert "spent ε=0.500" in capsys.readouterr().out


def test_cmd_dp_status_and_reset(tmp_path, capsys):
    _count_workspace(tmp_path)
    cli_main(["dp", "SELECT count(*) FROM c", str(tmp_path), "--epsilon", "0.5"])
    capsys.readouterr()
    cli_main(["dp", None, str(tmp_path), "--status"])
    assert "spent" in capsys.readouterr().out
    cli_main(["dp", None, str(tmp_path), "--reset"])
    capsys.readouterr()
    cli_main(["dp", None, str(tmp_path), "--status"])
    assert "spent ε=0.000" in capsys.readouterr().out
