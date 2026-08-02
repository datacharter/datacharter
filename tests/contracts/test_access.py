from datacharter.contracts.access import resolve_masked

# resolve_masked(...) -> True means MASKED (agent access OFF).
BASE = dict(declared_pii={"email"}, auto_pii={"ssn"})


def test_pii_defaults_masked_others_real():
    assert resolve_masked("store", "customers", "email", overrides={}, **BASE) is True
    assert resolve_masked("store", "customers", "ssn", overrides={}, **BASE) is True  # auto
    assert resolve_masked("store", "customers", "tier", overrides={}, **BASE) is False


def test_overrides_win_field_over_table_over_source():
    ov = {
        "store": {
            "source": False,  # source-wide: masked
            "tables": {"customers": True},  # customers table: real
            "columns": {"customers.email": False},  # email field: masked
        }
    }
    # field beats table beats source
    assert resolve_masked("store", "customers", "email", overrides=ov, **BASE) is True
    # table (real) unmasks a PII-by-default column with no field override
    assert resolve_masked("store", "customers", "ssn", overrides=ov, **BASE) is False
    # source (masked) masks a non-PII column in another table
    assert resolve_masked("store", "orders", "tier", overrides=ov, **BASE) is True


def test_field_on_unmasks_pii():
    ov = {"store": {"columns": {"customers.email": True}}}
    assert resolve_masked("store", "customers", "email", overrides=ov, **BASE) is False


def test_build_overrides_remaps_file_sources_to_memory():
    # csv/parquet/json sources register as views under the engine's `memory`
    # database — their toggles must reach those registrations (the charter-name
    # key never matches, which silently disabled source/table toggles).
    from datacharter.contracts.access import build_overrides
    from datacharter.models import Source, SourceType

    csv = Source(
        name="people", type=SourceType.CSV, path="people.csv",
        tables=["people"], agent_access={"source": False},
    )
    ov = build_overrides([csv])
    assert ov["memory"]["tables"]["people"] is False
    assert resolve_masked("memory", "people", "plan", overrides=ov, **BASE) is True


def test_build_overrides_finer_file_entries_win():
    from datacharter.contracts.access import build_overrides
    from datacharter.models import Source, SourceType

    csv = Source(
        name="people", type=SourceType.CSV, path="people.csv", tables=["people"],
        agent_access={"source": False, "tables": {"people": True},
                      "columns": {"people.email": False}},
    )
    ov = build_overrides([csv])
    assert ov["memory"]["tables"]["people"] is True  # explicit table beats source
    assert resolve_masked("memory", "people", "email", overrides=ov, **BASE) is True
    assert resolve_masked("memory", "people", "plan", overrides=ov, **BASE) is False


def test_build_overrides_leaves_attach_sources_alone():
    from datacharter.contracts.access import build_overrides
    from datacharter.models import Source, SourceType

    pg = Source(
        name="crm", type=SourceType.POSTGRES, tables=["accounts"],
        agent_access={"source": True},
    )
    ov = build_overrides([pg], local_access={"tables": {"snap": False}})
    assert ov["crm"] == {"source": True}
    assert "memory" not in ov
    assert ov["local"]["tables"]["snap"] is False
