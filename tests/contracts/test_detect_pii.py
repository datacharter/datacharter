from datacharter.cli import main as core_main
from datacharter.contracts import load_charter
from datacharter.contracts.pii import detect_pii
from datacharter.engine.session import Engine


async def test_detect_pii_flags_email_in_demo(tmp_path):
    core_main(["init", str(tmp_path), "--demo"])
    charter = load_charter(tmp_path)
    with Engine(tmp_path, charter.sources) as eng:
        found = await detect_pii(eng)
    flat = {c.lower() for cols in found.values() for c in cols}
    assert "email" in flat  # name heuristic flags the customers.email column
