import datacharter.cli as cli
from datacharter.agent.llm import Delta
from datacharter.cli import main as cli_main


def _write_suite(ws, body):
    (ws / "evals").mkdir(exist_ok=True)
    (ws / "evals" / "s.yaml").write_text(body)


def test_eval_passes_and_exits_zero(tmp_path, monkeypatch):
    cli_main(["init", str(tmp_path), "--demo"])
    _write_suite(
        tmp_path,
        "version: 1\ncases:\n  - question: how many orders?\n"
        "    expect:\n      - { type: answer_contains, value: '90' }\n",
    )

    class StubLLM:
        def __init__(self, *a, **k):
            pass

        async def stream(self, messages, tools):
            for d in [Delta(text="There are 90 orders.")]:
                yield d

    monkeypatch.setattr(cli, "LLMClient", StubLLM, raising=False)
    assert cli_main(["eval", str(tmp_path), "--threshold", "1.0"]) == 0


def test_eval_below_threshold_exits_nonzero(tmp_path, monkeypatch):
    cli_main(["init", str(tmp_path), "--demo"])
    _write_suite(
        tmp_path,
        "version: 1\ncases:\n  - question: q\n"
        "    expect:\n      - { type: answer_contains, value: 'zzz' }\n",
    )

    class StubLLM:
        def __init__(self, *a, **k):
            pass

        async def stream(self, messages, tools):
            for d in [Delta(text="nope")]:
                yield d

    monkeypatch.setattr(cli, "LLMClient", StubLLM, raising=False)
    assert cli_main(["eval", str(tmp_path), "--threshold", "0.5"]) == 1


def test_eval_no_suites_errors(tmp_path):
    cli_main(["init", str(tmp_path), "--demo"])
    assert cli_main(["eval", str(tmp_path)]) == 1
