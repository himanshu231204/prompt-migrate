"""PR 3b: check reports secrets in history and stale allowlist entries; warnings never change the exit code."""
import sqlite3
from contextlib import closing

import pytest

from pmtest import (
    CFG, GENERATED, LEGACY_ID, allow_entry, create, fake_key, pm_dir, pm_warnings, set_draft, write_allowlist,
    write_revision,
)
from promptmigrate import cli
from promptmigrate.core import audit_secrets, upgrade
from promptmigrate.errors import SecretInHistoryWarning, StaleAllowlistWarning

TOKEN = fake_key()
B, C = "b" * 12, "c" * 12
HISTORY = f"revision {LEGACY_ID}: assistant /note openai-anthropic-key"
STALE = "secret allowlist entry assistant /note openai-anthropic-key matched nothing in drafts or history"


def run(capsys, project, *argv):
    code = cli.main(["--project", str(project), *argv])
    out, err = capsys.readouterr()
    return code, out, err


def test_check_warns_about_a_history_secret_and_exits_0(project, capsys):
    GENERATED["secret_in_history"](project)
    code, out, err = run(capsys, project, "check")
    assert (code, err) == (0, f"Warning: {HISTORY}\n")
    assert TOKEN not in out + err


def test_one_warning_per_revision_name_path_and_rule(project):
    leaky = {**CFG, "note": TOKEN}
    write_revision(project, LEGACY_ID, None, {"assistant": create(leaky)})
    edited = {**leaky, "messages": [{"role": "system", "content": "B"}]}
    write_revision(project, B, LEGACY_ID, {"assistant": {"before": leaky, "after": edited}})
    write_revision(project, C, B, {"other": create(CFG)})
    assert pm_warnings(audit_secrets, project)[1] == [HISTORY, f"revision {B}: assistant /note openai-anthropic-key"]


def test_history_warning_category(project):
    GENERATED["secret_in_history"](project)
    with pytest.warns(SecretInHistoryWarning, match="assistant /note openai-anthropic-key"):
        audit_secrets(project)


def test_stale_allowlist_entry_warns(project):
    write_allowlist(project, [allow_entry("assistant", "/note", "openai-anthropic-key", TOKEN)])
    assert pm_warnings(audit_secrets, project)[1] == [STALE]
    with pytest.warns(StaleAllowlistWarning):
        audit_secrets(project)


def test_entry_used_by_history_is_not_stale(project):
    GENERATED["secret_in_history"](project)
    write_allowlist(project, [allow_entry("assistant", "/note", "openai-anthropic-key", TOKEN)])
    assert pm_warnings(audit_secrets, project)[1] == []


def test_entry_used_by_a_draft_is_not_stale(project):
    set_draft(project, "assistant", {**CFG, "note": TOKEN})
    write_allowlist(project, [allow_entry("assistant", "/note", "openai-anthropic-key", TOKEN)])
    assert pm_warnings(audit_secrets, project)[1] == []


def test_unreadable_drafts_skip_the_stale_check(project, capsys):
    """Plan decision E3: check never starts failing because of a broken draft."""
    write_allowlist(project, [allow_entry("assistant", "/note", "openai-anthropic-key", TOKEN)])
    (pm_dir(project) / "drafts" / "assistant.json").write_text("{", encoding="utf-8")
    assert run(capsys, project, "check") == (0, "OK: dev is consistent (0/0 revisions applied)\n", "")


def test_warnings_print_before_a_check_error(project, capsys):
    GENERATED["secret_in_history"](project)
    upgrade(project, "dev")
    with closing(sqlite3.connect(pm_dir(project) / "states" / "dev.sqlite3")) as conn, conn:
        conn.execute("UPDATE prompts SET config='{}' WHERE name='assistant'")
    assert run(capsys, project, "check") == (
        4, "", f"Warning: {HISTORY}\nError: Environment drift detected for prompts: assistant\n")


def test_current_does_not_audit(project, capsys):
    """Plan decision E2."""
    GENERATED["secret_in_history"](project)
    assert run(capsys, project, "current")[2] == ""


def test_history_message_secret_is_reported(project):
    write_revision(project, LEGACY_ID, None, {"assistant": create(CFG)}, message="rotate " + TOKEN)
    assert pm_warnings(audit_secrets, project)[1] == [
        f"revision {LEGACY_ID}: (message) /message openai-anthropic-key"]


def test_allowlisted_message_is_not_stale(project):
    write_revision(project, LEGACY_ID, None, {"assistant": create(CFG)}, message="rotate " + TOKEN)
    write_allowlist(project, [allow_entry("(message)", "/message", "openai-anthropic-key", TOKEN)])
    assert pm_warnings(audit_secrets, project)[1] == []
