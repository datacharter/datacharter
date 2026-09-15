"""Frozen GovBench corpus: file, runner, and public page stay the same set."""

from pathlib import Path

from datacharter.agent.redteam import (
    ATTACKS,
    CORPUS_ID,
    corpus_cite,
    corpus_sha256,
    load_corpus,
)

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "docs" / "govbench.md"
CORPUS = Path(__file__).resolve().parents[2] / "src" / "datacharter" / "agent" / "govbench_v1.json"


def test_corpus_id_and_count():
    assert CORPUS_ID == "govbench-v1"
    assert CORPUS.is_file()
    loaded = load_corpus()
    assert len(loaded) == 28
    assert len(ATTACKS) == 28
    assert [a.sql for a in loaded] == [a.sql for a in ATTACKS]


def test_corpus_sha256_is_stable():
    digest = corpus_sha256()
    assert len(digest) == 64
    assert digest == corpus_cite()["sha256"]
    # Bump govbench-v1 -> v2 (and this pin) if the attack list changes.
    assert digest == "7223b8a3f4186d2ed9dd1409c9d8857f11e216bbfa0a2ca254355a4e220ec42b"


def test_public_page_cites_corpus_and_lists_sql():
    page = PAGE.read_text()
    assert CORPUS_ID in page
    assert corpus_sha256() in page
    assert "datacharter govbench" in page
    for attack in ATTACKS:
        assert attack.sql in page


def test_cite_shape():
    cite = corpus_cite()
    assert cite["id"] == "govbench-v1"
    assert cite["attacks"] == 28
    assert set(cite) == {"id", "sha256", "attacks"}
