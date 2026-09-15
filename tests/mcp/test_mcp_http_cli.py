"""mcp --http is loopback-only and cannot combine with --serve-url."""

from datacharter.cli import main as cli_main


def test_mcp_http_refuses_non_loopback(tmp_path, capsys):
    assert cli_main(["init", str(tmp_path), "--demo"]) == 0
    assert cli_main(["mcp", str(tmp_path), "--http", "--host", "0.0.0.0"]) == 1
    err = capsys.readouterr().err
    assert "loopback" in err.lower()


def test_mcp_http_cannot_combine_with_serve_url(capsys):
    assert cli_main(["mcp", ".", "--http", "--serve-url", "http://127.0.0.1:8321"]) == 1
    err = capsys.readouterr().err
    assert "--serve-url" in err
