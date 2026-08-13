"""Governed synthetic data: schema-matched rows, PII columns rendered as fakes."""

import csv
import io
import random

from datacharter.cli import main as cli_main
from datacharter.synth import Column, synth_value, synthesize


def test_synth_value_pii_email_is_fake():
    rng = random.Random(1)
    v = synth_value(Column("email", "VARCHAR", is_pii=True), rng, 0)
    assert "@" in v and (v.endswith(".com") or v.endswith(".org") or v.endswith(".invalid"))


def test_synth_value_id_is_sequential():
    rng = random.Random(1)
    assert synth_value(Column("id", "BIGINT"), rng, 41) == 42


def test_synth_value_types():
    rng = random.Random(1)
    assert isinstance(synth_value(Column("n", "INTEGER"), rng, 0), int)
    assert isinstance(synth_value(Column("amt", "DOUBLE"), rng, 0), float)
    assert isinstance(synth_value(Column("ok", "BOOLEAN"), rng, 0), bool)
    d = synth_value(Column("d", "DATE"), rng, 0)
    assert len(d) == 10 and d.count("-") == 2


def test_synthesize_is_reproducible_with_seed():
    cols = [Column("id", "BIGINT"), Column("email", "VARCHAR", is_pii=True)]
    assert synthesize(cols, 5, seed=7) == synthesize(cols, 5, seed=7)


def _workspace(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "c.csv").write_text("id,email,tier\n1,real@corp.com,pro\n2,x@y.com,free\n")
    (tmp_path / "charter.yaml").write_text(
        "version: 1\nsources:\n  c:\n    type: csv\n    path: data/c.csv\n"
        "    pii:\n      c: [email]\n"
    )
    return tmp_path


def test_cmd_synth_matches_schema_and_fakes_pii(tmp_path, capsys):
    ws = _workspace(tmp_path)
    assert cli_main(["synth", "c", str(ws), "--rows", "20", "--seed", "3"]) == 0
    out = capsys.readouterr().out
    reader = list(csv.reader(io.StringIO(out)))
    assert reader[0] == ["id", "email", "tier"]  # schema preserved
    assert len(reader) == 21  # header + 20 rows
    emails = [r[1] for r in reader[1:]]
    assert "real@corp.com" not in emails  # never the real value
    assert all("@" in e for e in emails)  # but shaped like emails


def test_cmd_synth_json_and_file(tmp_path):
    import json

    ws = _workspace(tmp_path)
    out = tmp_path / "fake.json"
    assert cli_main(["synth", "c", str(ws), "--rows", "3", "--format", "json",
                     "-o", str(out), "--seed", "1"]) == 0
    data = json.loads(out.read_text())
    assert len(data) == 3 and set(data[0]) == {"id", "email", "tier"}


def test_cmd_synth_requires_charter(tmp_path, capsys):
    assert cli_main(["synth", "c", str(tmp_path)]) == 1
    assert "No charter.yaml" in capsys.readouterr().err
