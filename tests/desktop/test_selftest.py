from datacharter.selftest import DYNAMIC_TRIPWIRES, format_results, run_selftest


def test_selftest_passes_in_dev_env():
    results = run_selftest()
    failed = [r for r in results if not r[1]]
    assert not failed, format_results(results)


def test_selftest_walk_floor_guards_blind_enumeration(monkeypatch):
    # If the (frozen) importer can't enumerate packages, the selftest must
    # fail loudly rather than "pass" having imported nothing.
    import datacharter.selftest as st

    monkeypatch.setattr(st, "_own_modules", lambda: ["datacharter"])
    results = st.run_selftest()
    walk = next(r for r in results if r[0] == "module-walk")
    assert walk[1] is False


def test_tripwires_cover_the_shipped_failures():
    # pytz, multipart, and ruamel each shipped missing once — never drop them.
    assert {"pytz", "multipart", "ruamel.yaml"} <= set(DYNAMIC_TRIPWIRES)
