"""Workspace guides: loading, ordering, capping, and charter integration."""

from pathlib import Path

from datacharter.contracts.guides import load_guides
from datacharter.contracts.loader import load_charter


def _workspace(tmp_path: Path, charter: str = "version: 1\nsources: {}\n") -> Path:
    (tmp_path / "charter.yaml").write_text(charter)
    return tmp_path


def test_no_guides_dir_is_empty(tmp_path):
    assert load_guides(tmp_path) == ""


def test_guides_concatenated_sorted_with_headers(tmp_path):
    g = tmp_path / "guides"
    g.mkdir()
    (g / "b-metrics.md").write_text("Revenue is net of refunds.")
    (g / "a-overview.md").write_text("Orders come from the store source.")
    (g / "notes.txt").write_text("not markdown — ignored")
    out = load_guides(tmp_path)
    assert out.index("## Guide: a-overview") < out.index("## Guide: b-metrics")
    assert "Orders come from the store source." in out
    assert "not markdown" not in out


def test_guides_capped_with_marker(tmp_path):
    g = tmp_path / "guides"
    g.mkdir()
    (g / "big.md").write_text("x" * 20000)
    out = load_guides(tmp_path, max_chars=100)
    assert len(out) < 200
    assert out.endswith("[guides truncated]")


def test_empty_guide_files_skipped(tmp_path):
    g = tmp_path / "guides"
    g.mkdir()
    (g / "empty.md").write_text("   \n")
    assert load_guides(tmp_path) == ""


def test_charter_loads_guides(tmp_path):
    ws = _workspace(tmp_path)
    g = ws / "guides"
    g.mkdir()
    (g / "overview.md").write_text("Exclude test accounts (region = 'ZZ').")
    charter = load_charter(ws)
    assert "Exclude test accounts" in charter.guides


def test_charter_without_guides_has_empty_string(tmp_path):
    charter = load_charter(_workspace(tmp_path))
    assert charter.guides == ""


def test_html_comments_stripped_so_scaffold_is_inert(tmp_path):
    from datacharter.cli import main as core_main

    core_main(["init", str(tmp_path)])  # scaffolds guides/overview.md (all-comment template)
    assert (tmp_path / "guides" / "overview.md").exists()
    assert load_guides(tmp_path) == ""
    # real content next to a comment survives
    (tmp_path / "guides" / "real.md").write_text("<!-- note to self -->\nUse net revenue.")
    assert load_guides(tmp_path) == "## Guide: real\nUse net revenue."
