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
