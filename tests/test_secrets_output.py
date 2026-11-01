"""PR 3b: diff and get redact secret-like values in their output; allowlisted values are shown (I13)."""
import json

import pytest

from pmtest import CFG, GENERATED, allow_entry, fake_key, pm_warnings, set_draft, write_allowlist
from promptmigrate import cli
from promptmigrate.core import get_config, redacted_config, redacted_diff, upgrade

TOKEN = fake_key()  # the value the secret_in_history fixture contains
REDACTED = "<redacted:openai-anthropic-key>"
REDACTED_WARNING = "1 secret-like value(s) redacted from this output; detection is heuristic and can miss secrets"


def run(capsys, project, *argv):
    code = cli.main(["--project", str(project), *argv])
    out, err = capsys.readouterr()
    return code, out, err


@pytest.fixture
def leaked(project):
    GENERATED["secret_in_history"](project)
    return project


def test_diff_redacts_a_history_secret(leaked, capsys):
    code, out, err = run(capsys, leaked, "diff")
    assert (code, err) == (0, f"Warning: {REDACTED_WARNING}\n")
    assert json.loads(out)["assistant"]["before"]["note"] == REDACTED
    assert TOKEN not in out


def test_get_redacts_an_applied_secret(leaked, capsys):
    upgrade(leaked, "dev")
    code, out, err = run(capsys, leaked, "get", "assistant")
    assert (code, err) == (0, f"Warning: {REDACTED_WARNING}\n")
    assert json.loads(out)["note"] == REDACTED
    assert TOKEN not in out


def test_redacted_diff_lists_what_it_redacted(leaked):
    (changes, redacted), got = pm_warnings(redacted_diff, leaked)
    assert redacted == [{"name": "assistant", "side": "before", "path": "/note"}]
    assert changes["assistant"]["before"]["note"] == REDACTED
    assert got == [REDACTED_WARNING]


def test_redacted_config_lists_what_it_redacted(leaked):
    upgrade(leaked, "dev")
    (config, paths), got = pm_warnings(redacted_config, leaked, "dev", "assistant")
    assert (config["note"], paths, got) == (REDACTED, ["/note"], [REDACTED_WARNING])


def test_draft_secret_is_redacted_in_diff(project, capsys):
    set_draft(project, "assistant", {**CFG, "tools": [{"name": "http", "auth": "Bearer " + "k" * 24}]})
    code, out, _ = run(capsys, project, "diff")
    assert code == 0
    assert json.loads(out)["assistant"]["after"]["tools"][0]["auth"] == "<redacted:bearer-token>"
    assert "k" * 24 not in out


def test_allowlisted_value_is_shown(leaked, capsys):
    write_allowlist(leaked, [allow_entry("assistant", "/note", "openai-anthropic-key", TOKEN)])
    code, out, err = run(capsys, leaked, "diff")
    assert (code, err) == (0, "")
    assert json.loads(out)["assistant"]["before"]["note"] == TOKEN


def test_non_matching_allowlist_entry_has_no_effect(leaked, capsys):
    write_allowlist(leaked, [allow_entry("assistant", "/other", "openai-anthropic-key", TOKEN)])
    _, out, _ = run(capsys, leaked, "diff")
    assert json.loads(out)["assistant"]["before"]["note"] == REDACTED


def test_stored_data_is_not_redacted(leaked):
    upgrade(leaked, "dev")
    assert get_config(leaked, "dev", "assistant")["note"] == TOKEN


def test_blocked_revision_never_prints_the_value(project, capsys):
    set_draft(project, "assistant", {**CFG, "note": TOKEN})
    code, out, err = run(capsys, project, "revision", "-m", "leak")
    assert code == 1  # exit code 3 is asserted from PR 6
    assert TOKEN not in out + err
    assert err.startswith("Error: Secret-like values in new revision content: assistant /note openai-anthropic-key.")
