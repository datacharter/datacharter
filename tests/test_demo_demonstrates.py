"""The demo must actually demonstrate every feature it advertises.

Users judged the product on a tour whose Guides, Evals, and Audit panels were
EMPTY (shipped defect #5) — seeding is wrapped in try/except by design, so
only assertions like these notice when it silently stops working.
"""

import keyring
import keyring.backend
import pytest

from datacharter.cli import main as cli_main


class _MemKeyring(keyring.backend.KeyringBackend):
    priority = 1

    def __init__(self):
        self.store = {}

    def get_password(self, s, n):
        return self.store.get((s, n))

    def set_password(self, s, n, v):
        self.store[(s, n)] = v

    def delete_password(self, s, n):
        self.store.pop((s, n), None)


@pytest.fixture
def tour_ws(tmp_path):
    prev = keyring.get_keyring()
    keyring.set_keyring(_MemKeyring())
    assert cli_main(["init", str(tmp_path), "--demo", "--tour"]) == 0
    yield tmp_path
    keyring.set_keyring(prev)


def test_tour_seeds_guides(tour_ws):
    from datacharter.contracts.guides import load_guides

    guides = load_guides(tour_ws)
    assert "Revenue" in guides and "PII" in guides


def test_tour_seeds_a_loadable_eval_suite(tour_ws):
    from datacharter.contracts.evals import load_suites

    suites = load_suites(tour_ws)
    assert suites and all(s.cases for s in suites)
    # Every case must be checkable (the zero-assertion refusal guards this at
    # load, but the demo file itself must never regress into a parse error).
    assert all(c.expect or c.expected_answer for s in suites for c in s.cases)


def test_tour_seeds_a_verifiable_audit_chain(tour_ws):
    from datacharter.audit.evidence import verify_chain

    ok, n, detail = verify_chain(tour_ws)
    assert ok, detail
    assert n >= 2, f"expected a session + accesses, got {detail}"


def test_tour_charter_arms_canaries_and_policies(tour_ws):
    from datacharter.contracts import load_charter

    charter = load_charter(tour_ws)
    assert charter.canary_mode == "block"
    assert charter.policies, "tour charter must ship a policy example"
    assert charter.audit_enabled


def test_tour_seeds_query_history_for_suggest(tour_ws):
    from datacharter.contracts.suggest import mine_history

    assert mine_history(tour_ws), "suggest must have a mined habit in the demo"
