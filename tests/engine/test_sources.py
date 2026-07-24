import pytest

from datacharter.engine.sources import SourceConfigError, registration_sql
from datacharter.models import Source, SourceType


def test_postgres_uses_temporary_secret_and_readonly_attach(tmp_path):
    src = Source(
        name="pg",
        type=SourceType.POSTGRES,
        connection={"host": "db.internal", "port": 5432, "database": "app", "user": "reader"},
        credentials={"password": "pw'quote"},
    )
    secret, attach = registration_sql(src, tmp_path)
    assert secret.startswith("CREATE OR REPLACE TEMPORARY SECRET pg_secret (TYPE postgres")
    assert "PASSWORD 'pw''quote'" in secret
    assert attach == "ATTACH '' AS pg (TYPE postgres, SECRET pg_secret, READ_ONLY)"


def test_mysql_registration_shape(tmp_path):
    src = Source(
        name="shop",
        type=SourceType.MYSQL,
        connection={"host": "h", "database": "d", "user": "u"},
        credentials={"password": "p123"},
    )
    secret, attach = registration_sql(src, tmp_path)
    assert "TYPE mysql" in secret
    assert "READ_ONLY" in attach


def test_db_source_requires_database(tmp_path):
    src = Source(name="pg", type=SourceType.POSTGRES, connection={"host": "h"})
    with pytest.raises(SourceConfigError):
        registration_sql(src, tmp_path)


def test_relative_file_path_resolves_against_workspace(tmp_path):
    src = Source(name="f", type=SourceType.CSV, path="data/x.csv")
    (stmt,) = registration_sql(src, tmp_path)
    assert str(tmp_path / "data" / "x.csv") in stmt


def test_s3_parquet_gets_s3_secret(tmp_path):
    src = Source(
        name="lake",
        type=SourceType.PARQUET,
        path="s3://bucket/data/*.parquet",
        credentials={"key_id": "AKIAEXAMPLE", "secret": "s3secretvalue", "region": "us-west-2"},
    )
    secret, view = registration_sql(src, tmp_path)
    assert secret.startswith("CREATE OR REPLACE TEMPORARY SECRET lake_s3 (TYPE s3")
    assert "KEY_ID 'AKIAEXAMPLE'" in secret
    assert "read_parquet('s3://bucket/data/*.parquet')" in view


def test_file_source_without_path_errors(tmp_path):
    src = Source(name="f", type=SourceType.CSV)
    with pytest.raises(SourceConfigError):
        registration_sql(src, tmp_path)


def test_iceberg_and_delta_views(tmp_path):
    for stype, func in [(SourceType.ICEBERG, "iceberg_scan"), (SourceType.DELTA, "delta_scan")]:
        src = Source(name="lakehouse", type=stype, path="s3://bucket/tbl")
        stmts = registration_sql(src, tmp_path)
        assert any(func in s for s in stmts)
