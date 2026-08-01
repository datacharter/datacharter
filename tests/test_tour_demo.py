"""The guided-tour demo ships real governance content; the plain demo stays lean."""

from datacharter.audit.evidence import read_entries, verify_chain
from datacharter.cli import main as cli_main
from datacharter.contracts import load_charter


def test_plain_demo_stays_minimal_and_fast(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])
    charter = load_charter(tmp_path)
    assert charter.policies == {} and charter.canary_mode is None
    assert not (tmp_path / "evals").exists()
    assert read_entries(tmp_path) == []


def test_tour_demo_has_every_surface_populated(tmp_path):
    cli_main(["init", str(tmp_path), "--demo", "--tour"])
    charter = load_charter(tmp_path)
    # policy + canary + context are declared
    assert charter.policies["store.customers"].min_group_size == 2
    assert charter.canary_mode == "block"
    assert "Revenue" in charter.guides
    assert (tmp_path / "evals" / "demo.yaml").exists()
    # a REAL audit chain: one allowed aggregate, one policy refusal
    entries = read_entries(tmp_path)
    accesses = [e for e in entries if e["type"] == "access"]
    assert len(accesses) == 2
    assert any(a.get("error", "").startswith("Error: policy") for a in accesses)
    ok, n, _ = verify_chain(tmp_path)
    assert ok and n == 3
    # history seeded so `suggest` has a habit to mine
    from datacharter.contracts.suggest import mine_history

    assert any("tier" in s.text for s in mine_history(tmp_path))
