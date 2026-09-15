"""Auto-charter: a folder of files becomes a reviewable charter.yaml."""

from pathlib import Path

from datacharter.cli import main
from datacharter.contracts import load_charter
from datacharter.contracts.from_files import (
    FromFilesError,
    apply_file_sources,
    discover_data_files,
)


def _csv(path: Path, header: str, *rows: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "\n" + "\n".join(rows) + "\n")


def test_discover_skips_dot_and_guide_dirs(tmp_path: Path) -> None:
    _csv(tmp_path / "customers.csv", "id,email", "1,a@b.com")
    _csv(tmp_path / "data" / "orders.csv", "id,amount", "1,9")
    _csv(tmp_path / ".datacharter" / "uploads" / "secret.csv", "ssn", "111-11-1111")
    _csv(tmp_path / "guides" / "notes.csv", "x", "1")
    _csv(tmp_path / "queries" / "tmp.csv", "x", "1")
    found = discover_data_files(tmp_path)
    names = {f.name for f in found}
    assert names == {"customers", "orders"}
    assert all(f.path in ("customers.csv", "data/orders.csv") for f in found)


def test_discover_disambiguates_same_stem(tmp_path: Path) -> None:
    (tmp_path / "events.csv").write_text("id\n1\n")
    (tmp_path / "events.json").write_text('[{"id": 1}]\n')
    found = {f.name: f.type for f in discover_data_files(tmp_path)}
    assert found["events"] in {"csv", "json"}
    assert "events_csv" in found or "events_json" in found


def test_apply_writes_charter_and_pii(tmp_path: Path) -> None:
    _csv(tmp_path / "people.csv", "id,email,city", "1,ada@volt.dev,EU")
    result = apply_file_sources(tmp_path)
    assert [s.name for s in result.added] == ["people"]
    charter = load_charter(tmp_path)
    src = charter.sources[0]
    assert src.type.value == "csv"
    assert src.path == "people.csv"
    assert "email" in src.pii.get("people", [])
    assert result.pii.get("people") == ["email"] or "email" in (result.pii.get("people") or [])


def test_apply_merge_skips_existing(tmp_path: Path) -> None:
    _csv(tmp_path / "a.csv", "id", "1")
    apply_file_sources(tmp_path)
    _csv(tmp_path / "b.csv", "id", "2")
    second = apply_file_sources(tmp_path)
    assert [s.name for s in second.added] == ["b"]
    names = {s.name for s in load_charter(tmp_path).sources}
    assert names == {"a", "b"}


def test_apply_errors_when_no_files(tmp_path: Path) -> None:
    try:
        apply_file_sources(tmp_path)
    except FromFilesError as exc:
        assert "No csv" in str(exc)
    else:
        raise AssertionError("expected FromFilesError")


def test_init_from_scaffolds_and_queries(tmp_path: Path) -> None:
    _csv(tmp_path / "sales.csv", "id,amount", "1,10", "2,20")
    assert main(["init", str(tmp_path), "--from"]) == 0
    assert (tmp_path / "charter.yaml").exists()
    assert (tmp_path / "queries").is_dir()
    charter = load_charter(tmp_path)
    assert {s.name for s in charter.sources} == {"sales"}
    from datacharter.engine.session import Engine

    with Engine(tmp_path, charter.sources) as eng:
        result = eng.query_sync("SELECT count(*) AS n FROM sales")
        assert result.rows[0][0] == 2


def test_init_from_refuses_demo_combo(tmp_path: Path, capsys) -> None:
    assert main(["init", str(tmp_path), "--from", "--demo"]) == 1
    assert "cannot combine" in capsys.readouterr().err.lower()


def test_from_files_api_registers_live_sources(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from datacharter.server import create_app

    _csv(tmp_path / "leads.csv", "id,email", "1,ada@volt.dev")
    assert main(["init", str(tmp_path)]) == 0
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        resp = client.post("/api/charter/from-files")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["added"][0]["name"] == "leads"
        assert "email" in (body["pii"].get("leads") or [])
        tables = client.get("/api/tables").json()["tables"]
        assert any(t["table"] == "leads" or t["source"] == "leads" for t in tables)
