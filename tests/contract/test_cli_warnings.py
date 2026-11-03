"""PR 3: the CLI captures PromptMigrate warnings, deduplicates them per invocation and prints them to stderr."""
import re
import warnings

import pytest

from pmtest import CFG, LEGACY_NAMES, LEGACY_SUFFIX, LEGACY_WARNINGS, install_fixture, install_legacy, set_draft
from promptmigrate import cli, revisions
from promptmigrate.errors import LegacyRevisionWarning, SchemaError

COMMANDS = [["history"], ["upgrade"], ["check"], ["current"], ["get", "assistant"], ["downgrade", "base"]]


def run(capsys, project, *argv):
    code = cli.main(["--project", str(project), *argv])
    out, err = capsys.readouterr()
    return code, out, err


def stderr_for(messages):
    return "".join(f"Warning: {m}\n" for m in messages)


@pytest.mark.parametrize("name", [n for n in LEGACY_NAMES if n != "secret_in_history"])
def test_every_command_prints_each_legacy_warning_once(project, monkeypatch, capsys, name):
    """`current` loads history twice; it must still print each warning once.

    secret_in_history is excluded: from PR 3b its get and check also print secret warnings, which
    tests/security/test_secrets_output.py and tests/security/test_secrets_check.py pin.
    """
    install_legacy(project, monkeypatch, name)
    expected = stderr_for(m + LEGACY_SUFFIX for m in LEGACY_WARNINGS[name])
    for argv in COMMANDS:
        code, _, err = run(capsys, project, *argv)
        assert (code, err) == (0, expected), argv


def test_duplicates_dropped_in_first_seen_order(project, monkeypatch, capsys):
    def noisy(_project):
        for message in ("first", "second", "first"):
            warnings.warn(message, LegacyRevisionWarning)
        return []
    monkeypatch.setattr(revisions, "load_revisions", noisy)
    assert run(capsys, project, "history") == (0, "", "Warning: first\nWarning: second\n")


def test_warnings_print_before_the_error(project, monkeypatch, capsys):
    def failing(_project):
        warnings.warn("careful", LegacyRevisionWarning)
        raise SchemaError("boom")
    monkeypatch.setattr(revisions, "load_revisions", failing)
    assert run(capsys, project, "history") == (1, "", "Warning: careful\nError: boom\n")


def test_warnings_print_before_an_unhandled_exception_propagates(project, monkeypatch, capsys):
    def failing(_project):
        warnings.warn("careful", LegacyRevisionWarning)
        raise RuntimeError("boom")
    monkeypatch.setattr(revisions, "load_revisions", failing)
    with pytest.raises(RuntimeError):
        cli.main(["--project", str(project), "history"])
    assert capsys.readouterr().err == "Warning: careful\n"


def test_other_warnings_pass_through_unprinted(project, monkeypatch, capsys):
    shown = []
    monkeypatch.setattr(warnings, "showwarning", lambda message, category, *args, **kwargs: shown.append(category))

    def noisy(_project):
        warnings.warn("from a library", DeprecationWarning)
        return []
    monkeypatch.setattr(revisions, "load_revisions", noisy)
    assert run(capsys, project, "history") == (0, "", "")
    assert shown == [DeprecationWarning]


def test_reserved_types_remediation_via_cli(project, capsys):
    install_fixture(project, "reserved_types")
    set_draft(project, "assistant", {**CFG, "model": "x", "tools": []})
    code, out, err = run(capsys, project, "revision", "-m", "fix reserved types")
    new = re.search(r"Created ([0-9a-f]{12})", out).group(1)
    carried = (f"revision {new}: assistant before carries reserved-field-type assistant.model, "
               "reserved-field-type assistant.tools from history (copied for compatibility)")
    legacy = [m + LEGACY_SUFFIX for m in LEGACY_WARNINGS["reserved_types"]]
    assert (code, err) == (0, stderr_for([*legacy, carried]))
