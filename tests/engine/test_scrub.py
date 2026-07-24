from datacharter.engine.scrub import MASK, scrub


def test_scrub_replaces_all_occurrences():
    msg = "auth failed for hunter2 (password=hunter2)"
    assert scrub(msg, ["hunter2"]) == f"auth failed for {MASK} (password={MASK})"


def test_scrub_longest_secret_first():
    msg = "key=abcdef123 partial=abcdef"
    out = scrub(msg, ["abcdef", "abcdef123"])
    assert "abcdef" not in out


def test_scrub_ignores_degenerate_short_values():
    assert scrub("select a from t", ["a"]) == "select a from t"


def test_scrub_no_secrets_is_identity():
    assert scrub("plain message", []) == "plain message"
