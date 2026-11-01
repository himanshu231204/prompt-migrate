"""PR 3b: heuristic secret detection, allowlist parsing and redaction (pure functions, no I/O)."""
import re
import time

import pytest

from pmtest import fake_key
from promptmigrate import secretscan
from promptmigrate.errors import (
    PromptMigrateWarning, SchemaError, SecretDetectedError, SecretInHistoryWarning, SecretRedactedWarning,
    StaleAllowlistWarning,
)
from promptmigrate.secretscan import AllowEntry, Finding

CONTENT = "/messages/0/content"

# Every positive sample is assembled at runtime from fragments; no token-shaped literal is committed.
POSITIVE = {
    "openai-anthropic-key": ["sk-" + "a" * 24, "sk-" + "ant-" + "b" * 24],
    "aws-access-key-id": ["AKIA" + "A1" * 8],
    "github-token": ["gh" + "p_" + "c" * 36, "gh" + "s_" + "d" * 40],
    "slack-token": ["xox" + "b-" + "1" * 12],
    "private-key-pem": ["-----BEGIN " + "RSA PRIVATE KEY" + "-----", "-----BEGIN " + "PRIVATE KEY" + "-----"],
    "bearer-token": ["Bearer " + "e" * 24, "bearer\t" + "f" * 30],
    "jwt": ["eyJ" + "g" * 12 + "." + "h" * 12 + "." + "i" * 12],
}
NEGATIVE = [
    "sk-" + "a" * 5,                    # a short sk- word
    "risk-free",
    "AKIA" + "a" * 16,                  # lowercase
    "gh" + "p_" + "c" * 10,             # too short
    "gh" + "x_" + "c" * 40,             # unknown prefix
    "xox" + "z-" + "1" * 12,
    "xox" + "b-" + "1" * 5,
    "-----BEGIN " + "PUBLIC KEY" + "-----",
    "Bearer short",
    "eyJ" + "g" * 5 + ".a.b",
    "You are a helpful AI assistant.",
]


def prompt(text):
    return {"messages": [{"role": "system", "content": text}]}


def entry(name, path, rule, value):
    return AllowEntry(name, path, rule, secretscan.fingerprint(value), "documentation example")


def test_rule_ids():
    assert secretscan.RULE_IDS == (
        "openai-anthropic-key", "aws-access-key-id", "github-token", "slack-token", "private-key-pem",
        "bearer-token", "jwt", "secret-key-name",
    )


def test_error_and_warning_types():
    assert issubclass(SecretDetectedError, SchemaError)
    for cls in (SecretRedactedWarning, SecretInHistoryWarning, StaleAllowlistWarning):
        assert issubclass(cls, PromptMigrateWarning)
    error = SecretDetectedError([Finding("a", "/x", "jwt"), Finding("b", "/y", "slack-token")])
    assert error.findings == [{"name": "a", "path": "/x", "rule": "jwt"}, {"name": "b", "path": "/y", "rule": "slack-token"}]
    assert str(error) == ("Secret-like values in new revision content: a /x jwt; b /y slack-token. "
                          "No file was written; remove them or allowlist a reviewed false positive.")


# --- value rules ------------------------------------------------------------------------------

@pytest.mark.parametrize("rule, sample", [(rule, s) for rule, samples in POSITIVE.items() for s in samples])
def test_value_rule_positive(rule, sample):
    assert secretscan.scan("assistant", prompt(sample)) == [Finding("assistant", CONTENT, rule)]


@pytest.mark.parametrize("sample", NEGATIVE)
def test_value_rule_negative(sample):
    assert secretscan.scan("assistant", prompt(sample)) == []


def test_jwt_scan_is_linear_on_adversarial_input():
    text = "eyJ" * 70_000 + "."
    start = time.perf_counter()
    secretscan.scan("a", prompt(text))
    assert time.perf_counter() - start < 2


def test_jwt_found_after_a_failed_run():
    text = "eyJ" + "x" * 3 + " " + "eyJ" + "g" * 12 + "." + "h" * 12 + "." + "i" * 12
    assert secretscan.scan("a", prompt(text)) == [Finding("a", CONTENT, "jwt")]


def test_jwt_inside_longer_text():
    token = "eyJ" + "g" * 12 + "." + "h" * 12 + "." + "i" * 12
    text = "token=" + token + " end"
    assert secretscan.scan("a", prompt(text)) == [Finding("a", CONTENT, "jwt")]


def test_embedded_in_a_longer_prompt_is_detected():
    text = "Use the key " + fake_key() + " when calling the API."
    assert secretscan.scan("assistant", prompt(text)) == [Finding("assistant", CONTENT, "openai-anthropic-key")]


def test_nested_inside_tools_is_detected():
    config = {"tools": [{"name": "search"}, {"name": "db", "headers": {"Authorization": "Bearer " + "z" * 24}}]}
    assert secretscan.scan("agent", config) == [Finding("agent", "/tools/1/headers/Authorization", "bearer-token")]


def test_one_finding_per_path_and_rule():
    text = fake_key("1") + " and " + fake_key("2")
    assert secretscan.scan("a", prompt(text)) == [Finding("a", CONTENT, "openai-anthropic-key")]


def test_rules_at_one_path_are_in_table_order():
    text = "Bearer " + "w" * 24 + " " + fake_key()
    assert [f.rule for f in secretscan.scan("a", prompt(text))] == ["openai-anthropic-key", "bearer-token"]


def test_findings_follow_document_order():
    config = {"b": fake_key("1"), "a": [fake_key("2"), "fine"]}
    assert [f.path for f in secretscan.scan("x", config)] == ["/b", "/a/0"]


def test_json_pointer_escapes_tilde_and_slash():
    config = {"a/b": {"c~d": "Bearer " + "q" * 24}}
    assert secretscan.scan("x", config) == [Finding("x", "/a~1b/c~0d", "bearer-token")]


# --- key rule ---------------------------------------------------------------------------------

@pytest.mark.parametrize("key", [
    "api_key", "API-KEY", "apikey", "password", "passwd", "secret", "client_secret", "access-token", "auth_token",
    "token", "private_key",
])
def test_secret_key_name_positive(key):
    assert secretscan.scan("a", {"parameters": {key: "hunter2"}}) == [Finding("a", f"/parameters/{key}", "secret-key-name")]


@pytest.mark.parametrize("config", [
    {"parameters": {"max_tokens": "512"}},
    {"parameters": {"api_key": "secret://openai/key"}},
    {"parameters": {"api_key": ""}},
    {"parameters": {"api_key": 12345}},
    {"parameters": {"tokens": "x"}},
    {"parameters": {"token_limit": "x"}},
    {"parameters": {"password": ["x"]}},
])
def test_secret_key_name_negative(config):
    assert secretscan.scan("a", config) == []


# --- fingerprint and allowlist matching -------------------------------------------------------

def test_fingerprint_is_sha256_of_the_utf8_text():
    assert secretscan.fingerprint("abc") == (
        "sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


def test_allowlist_entry_suppresses_its_exact_finding():
    token = fake_key()
    exact = entry("assistant", CONTENT, "openai-anthropic-key", token)
    used = set()
    assert secretscan.scan("assistant", prompt(token), [exact], used) == []
    assert used == {exact}


@pytest.mark.parametrize("field", ["name", "path", "rule", "fingerprint"])
def test_allowlist_entry_with_one_field_different_has_no_effect(field):
    token = fake_key()
    fields = {"name": "assistant", "path": CONTENT, "rule": "openai-anthropic-key",
              "fingerprint": secretscan.fingerprint(token), "reason": "doc"}
    fields[field] = {"name": "other", "path": "/messages/1/content", "rule": "bearer-token",
                     "fingerprint": secretscan.fingerprint(fake_key("9"))}[field]
    used = set()
    found = secretscan.scan("assistant", prompt(token), [AllowEntry(**fields)], used)
    assert found == [Finding("assistant", CONTENT, "openai-anthropic-key")]
    assert used == set()


def test_value_rule_fingerprint_covers_only_the_matched_substring():
    token = fake_key()
    text = "prefix " + token + " suffix"
    assert secretscan.scan("a", prompt(text), [entry("a", CONTENT, "openai-anthropic-key", token)]) == []


def test_key_rule_fingerprint_covers_the_whole_value():
    allow = [entry("a", "/password", "secret-key-name", "example-pass")]
    assert secretscan.scan("a", {"password": "example-pass"}, allow) == []


# --- redaction --------------------------------------------------------------------------------

def test_redact_replaces_the_whole_string_and_lists_paths():
    token = fake_key()
    config = {"messages": [{"role": "system", "content": "key " + token}], "note": "fine"}
    redacted, paths = secretscan.redact("a", config)
    assert redacted == {"messages": [{"role": "system", "content": "<redacted:openai-anthropic-key>"}], "note": "fine"}
    assert paths == [CONTENT]
    assert config["messages"][0]["content"] == "key " + token  # the input is not mutated


def test_redact_marks_the_first_rule_at_a_path():
    text = "Bearer " + "w" * 24 + " " + fake_key()
    redacted, paths = secretscan.redact("a", prompt(text))
    assert (redacted["messages"][0]["content"], paths) == ("<redacted:openai-anthropic-key>", [CONTENT])


def test_redact_keeps_allowlisted_values():
    token = fake_key()
    config = prompt(token)
    assert secretscan.redact("a", config, [entry("a", CONTENT, "openai-anthropic-key", token)]) == (config, [])


def test_redact_without_findings_returns_the_input():
    config = prompt("hello")
    assert secretscan.redact("a", config) == (config, [])


def test_redact_handles_a_flagged_bare_string_root():
    assert secretscan.redact("a", fake_key()) == ("<redacted:openai-anthropic-key>", [""])


# --- allowlist parsing ------------------------------------------------------------------------

def item(**overrides):
    value = {"name": "a", "path": "/x", "rule": "bearer-token", "fingerprint": "sha256:" + "0" * 64, "reason": "doc"}
    value.update(overrides)
    return value


def without(key):
    return {k: v for k, v in item().items() if k != key}


def test_parse_allowlist_accepts_valid_entries():
    assert secretscan.parse_allowlist({"allow": [item()]}, "f.json") == [
        AllowEntry("a", "/x", "bearer-token", "sha256:" + "0" * 64, "doc")]


BAD = {
    "not an object": ([], 'the top level must be {"allow": [...]}'),
    "extra top-level key": ({"allow": [], "x": 1}, 'the top level must be {"allow": [...]}'),
    "allow not a list": ({"allow": {}}, 'the top level must be {"allow": [...]}'),
    "entry not an object": ({"allow": ["x"]}, "entry 0 must be an object"),
    "missing reason": ({"allow": [without("reason")]}, "entry 0: missing reason"),
    "missing fingerprint": ({"allow": [without("fingerprint")]}, "entry 0: missing fingerprint"),
    "unknown key": ({"allow": [item(extra="1")]}, "entry 0: unknown key 'extra'"),
    "unknown rule": ({"allow": [item(rule="nope")]}, "entry 0: unknown rule 'nope'"),
    "non-string field": ({"allow": [item(path=1)]}, "entry 0: every field must be a string"),
    "bad fingerprint": ({"allow": [item(fingerprint="md5:abc")]},
                        "entry 0: fingerprint must be 'sha256:' followed by 64 lowercase hex digits"),
    "empty reason": ({"allow": [item(reason=" ")]}, "entry 0: reason must not be empty"),
    "second entry": ({"allow": [item(), item(rule="nope")]}, "entry 1: unknown rule 'nope'"),
    "duplicate entry": ({"allow": [item(), item(reason="other")]}, "entry 1: duplicates entry 0"),
}


@pytest.mark.parametrize("case", sorted(BAD))
def test_parse_allowlist_rejects(case):
    value, message = BAD[case]
    with pytest.raises(SchemaError, match=re.escape(f"Invalid secret allowlist f.json: {message}")):
        secretscan.parse_allowlist(value, "f.json")


def test_allowlist_errors_never_print_fingerprints():
    fingerprint = "sha256:" + "ab" * 32
    for bad in (item(fingerprint=fingerprint, rule="nope"), item(fingerprint=fingerprint, reason=""),
                item(fingerprint=fingerprint, extra="1"), item(rule=fingerprint),
                {**item(), fingerprint: "x"}):
        with pytest.raises(SchemaError) as info:
            secretscan.parse_allowlist({"allow": [bad]}, "f.json")
        assert "ab" * 32 not in str(info.value)
