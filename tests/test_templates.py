"""Template gallery: every starter charter parses and carries its promised governance."""

import pytest
import yaml

from datacharter.cli import TEMPLATES
from datacharter.cli import main as cli_main


def test_list_templates(capsys):
    assert cli_main(["init", "--list-templates"]) == 0
    out = capsys.readouterr().out
    for name in TEMPLATES:
        assert name in out


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_template_is_valid_yaml(name):
    doc = yaml.safe_load(TEMPLATES[name][1])
    assert doc["version"] == 1 and isinstance(doc["sources"], dict) and doc["sources"]


def test_secure_template_is_hardened():
    doc = yaml.safe_load(TEMPLATES["secure"][1])
    assert doc["firewall"] == "block"
    assert doc["canary"] is True  # YAML 1.1 parses `on` as boolean true → canary block mode
    assert doc["policies"]  # has at least one policy


def test_init_from_template_writes_charter(tmp_path, capsys):
    assert cli_main(["init", str(tmp_path), "--template", "postgres"]) == 0
    text = (tmp_path / "charter.yaml").read_text()
    assert "postgres" in text and "${PG_PASSWORD}" in text
    # It loads through the real charter loader (secrets left as placeholders).
    from datacharter.contracts import load_charter

    charter = load_charter(tmp_path, lenient_secrets=True)
    assert charter.sources[0].type.value == "postgres"


def test_init_unknown_template_errors(tmp_path, capsys):
    assert cli_main(["init", str(tmp_path), "--template", "nope"]) == 1
    assert "Unknown template" in capsys.readouterr().err


def test_files_template_hint_has_no_env_mention(tmp_path, capsys):
    # The files template has no ${ENV}; its hint must not tell users to fill creds.
    assert cli_main(["init", str(tmp_path), "--template", "files"]) == 0
    out = capsys.readouterr().out
    assert "${ENV}" not in out and "point the paths" in out


def test_secure_template_loads_with_firewall(tmp_path):
    from datacharter.contracts import load_charter

    cli_main(["init", str(tmp_path), "--template", "secure"])
    charter = load_charter(tmp_path, lenient_secrets=True)
    assert charter.firewall_mode == "block" and charter.canary_mode == "block"
