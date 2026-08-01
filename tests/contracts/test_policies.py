"""Policy grammar: English sentences ⇄ canonical form, validation, loader wiring."""

import pytest

from datacharter.contracts.loader import CharterError, load_charter
from datacharter.contracts.policies import Policy, parse_policies, render_sentences


def test_english_sentences_compile():
    p = parse_policies({
        "crm.customers": [
            "aggregates only",
            "groups of at least 10",
            "no joins to payments, billing",
        ]
    })["crm.customers"]
    assert p.aggregate_only is True
    assert p.min_group_size == 10
    assert p.no_joins_to == {"payments", "billing"}
    assert p.no_joins is False


def test_english_variants_and_case():
    p = parse_policies({"t": ["Agents may only read aggregates", "Groups of 25 or more"]})["t"]
    assert p.aggregate_only and p.min_group_size == 25
    p2 = parse_policies({"t": ["No Joins"]})["t"]
    assert p2.no_joins is True
    p3 = parse_policies({"t": ["never join to orders"]})["t"]
    assert p3.no_joins_to == {"orders"}


def test_structured_form():
    p = parse_policies({"billing": {"aggregate_only": True, "min_group_size": 25, "no_joins": True}})["billing"]
    assert p.aggregate_only and p.min_group_size == 25 and p.no_joins


def test_unknown_sentence_rejected():
    with pytest.raises(CharterError, match="only speak SQL to friends"):
        parse_policies({"t": ["only speak SQL to friends"]})


def test_bad_values_rejected():
    with pytest.raises(CharterError, match="min_group_size"):
        parse_policies({"t": {"min_group_size": 1}})
    with pytest.raises(CharterError, match="unknown"):
        parse_policies({"t": {"aggregates": True}})
    with pytest.raises(CharterError, match="groups of at least"):
        parse_policies({"t": ["groups of at least 1"]})


def test_render_sentences_roundtrip():
    p = Policy(aggregate_only=True, min_group_size=10, no_joins=False, no_joins_to={"payments"})
    sentences = render_sentences(p)
    p2_parts = parse_policies({"t": sentences})["t"]
    assert p2_parts == p


def test_loader_wires_policies(tmp_path):
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources: {}\n"
        "policies:\n"
        "  crm.customers:\n"
        "    - aggregates only\n"
        "    - groups of at least 10\n"
    )
    charter = load_charter(tmp_path)
    assert charter.policies["crm.customers"].min_group_size == 10


def test_loader_rejects_bad_policy(tmp_path):
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources: {}\npolicies:\n  t:\n    - do crimes\n"
    )
    with pytest.raises(CharterError, match="do crimes"):
        load_charter(tmp_path)
