"""PR 3b: revision() refuses new secret-like content (I13); the allowlist file; secrets copied from history."""
import re
import warnings

import pytest

from pmtest import CFG, GENERATED, allow_entry, fake_key, pm_dir, pm_warnings, set_draft, symlink_or_skip, write_allowlist
from promptmigrate import protocol, secretscan
from promptmigrate.core import load_allowlist, revision
from promptmigrate.errors import SchemaError, SecretDetectedError, SecretInHistoryWarning

CONTENT = "/messages/0/content"


def versions(project):
    return sorted((pm_dir(project) / "versions").iterdir())


def prompt(text):
    return {"messages": [{"role": "system", "content": text}]}


# --- blocking ---------------------------------------------------------------------------------

def test_secret_in_new_after_blocks_revision(project):
    token = fake_key()
    set_draft(project, "assistant", prompt("key " + token))
    with pytest.raises(SecretDetectedError) as info:
        revision(project, "add key")
    assert versions(project) == []
    assert info.value.findings == [{"name": "assistant", "path": CONTENT, "rule": "openai-anthropic-key"}]
    assert str(info.value) == ("Secret-like values in new revision content: assistant /messages/0/content "
                               "openai-anthropic-key. No file was written; remove them or allowlist a reviewed "
                               "false positive.")
    assert token not in str(info.value)


def test_secret_key_name_blocks_revision(project):
    set_draft(project, "assistant", {**CFG, "parameters": {"api_key": "hunter2"}})
    with pytest.raises(SecretDetectedError, match="assistant /parameters/api_key secret-key-name"):
        revision(project, "add key")
    assert versions(project) == []


def test_secret_reference_is_allowed(project):
    set_draft(project, "assistant", {**CFG, "parameters": {"api_key": "secret://openai/key"}})
    r = revision(project, "use a reference")
    assert r.changes["assistant"]["after"]["parameters"]["api_key"] == "secret://openai/key"


def test_secret_in_the_message_blocks_revision(project):
    with pytest.raises(SecretDetectedError, match=re.escape("(message) /message openai-anthropic-key")):
        revision(project, "rotate " + fake_key())
    assert versions(project) == []


# --- allowlist --------------------------------------------------------------------------------

def test_allowlisted_value_passes_revision(project):
    token = fake_key()
    set_draft(project, "assistant", prompt(token))
    write_allowlist(project, [allow_entry("assistant", CONTENT, "openai-anthropic-key", token)])
    r = revision(project, "documented example")
    assert r.changes["assistant"]["after"]["messages"][0]["content"] == token


def test_replacing_an_allowlisted_value_blocks_again(project):
    write_allowlist(project, [allow_entry("assistant", CONTENT, "openai-anthropic-key", fake_key("1"))])
    set_draft(project, "assistant", prompt(fake_key("2")))
    with pytest.raises(SecretDetectedError):
        revision(project, "swap")
    assert versions(project) == []


def test_an_index_shift_unbinds_the_entry(project):
    token = fake_key()
    write_allowlist(project, [allow_entry("assistant", CONTENT, "openai-anthropic-key", token)])
    set_draft(project, "assistant", {"messages": [{"role": "system", "content": "first"},
                                                  {"role": "user", "content": token}]})
    with pytest.raises(SecretDetectedError, match="assistant /messages/1/content openai-anthropic-key"):
        revision(project, "shifted")
    assert versions(project) == []


# --- secrets copied from history --------------------------------------------------------------

def test_removing_a_history_secret_warns_about_the_copied_before(project):
    GENERATED["secret_in_history"](project)
    set_draft(project, "assistant", CFG)  # the fixture's config without the leaked note
    new, got = pm_warnings(revision, project, "remove leaked key")
    assert got == ["assistant /note openai-anthropic-key copied from history into before; the credential must be rotated"]
    assert secretscan.scan("assistant", new.changes["assistant"]["after"]) == []


def test_copied_history_secret_warning_category(project):
    GENERATED["secret_in_history"](project)
    set_draft(project, "assistant", CFG)
    with pytest.warns(SecretInHistoryWarning, match="the credential must be rotated"):
        revision(project, "remove leaked key")


def test_refused_revision_warns_about_nothing(project):
    GENERATED["secret_in_history"](project)
    set_draft(project, "assistant", {**CFG, "note": fake_key("7")})
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(SecretDetectedError):
            revision(project, "swap leaked key")
    assert not any(issubclass(w.category, SecretInHistoryWarning) for w in caught)


# --- the allowlist file -----------------------------------------------------------------------

def test_no_allowlist_file_means_no_entries(project):
    assert load_allowlist(project) == []


def test_allowlist_file_is_loaded(project):
    token = fake_key()
    write_allowlist(project, [allow_entry("assistant", CONTENT, "openai-anthropic-key", token)])
    assert load_allowlist(project) == [secretscan.AllowEntry(
        "assistant", CONTENT, "openai-anthropic-key", secretscan.fingerprint(token), "documentation example")]


def test_malformed_allowlist_blocks_revision(project):
    write_allowlist(project, [{"name": "assistant"}])
    with pytest.raises(SchemaError, match=re.escape("Invalid secret allowlist secret-allowlist.json: entry 0: missing path")):
        revision(project, "initial")
    assert versions(project) == []


def test_allowlist_is_parsed_strictly(project):
    (pm_dir(project) / "secret-allowlist.json").write_text('{"allow": [], "allow": []}', encoding="utf-8")
    message = "Invalid secret allowlist secret-allowlist.json: duplicate key 'allow'"
    with pytest.raises(SchemaError, match=re.escape(message)):
        load_allowlist(project)


def test_allowlist_over_size_limit_rejected(project, monkeypatch):
    monkeypatch.setattr(protocol.limits, "MAX_CONTROL_FILE_BYTES", 10)
    write_allowlist(project, [])  # '{"allow": []}' is 13 bytes
    message = "Invalid secret allowlist secret-allowlist.json: 13 bytes exceeds the 10-byte limit"
    with pytest.raises(SchemaError, match=re.escape(message)):
        load_allowlist(project)


def test_symlinked_allowlist_rejected(project):
    target = pm_dir(project) / "shared-allowlist.json"
    target.write_text('{"allow": []}', encoding="utf-8")
    symlink_or_skip(pm_dir(project) / "secret-allowlist.json", target)
    message = "Invalid secret allowlist secret-allowlist.json: must not be a symlink"
    with pytest.raises(SchemaError, match=re.escape(message)):
        load_allowlist(project)
