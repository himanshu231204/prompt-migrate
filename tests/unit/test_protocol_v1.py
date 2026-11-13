"""PR 8 (cycle 2): protocol v1 and its canonical revision checksum (ADR-026).

A revision file with `"format_version": 1` is v1. It has exactly six top-level keys, and its checksum is
"v1:" + SHA-256 of `protocol.canonical` of the whole parsed object, so whitespace, line endings and key order do not
count and every value does. A file without `format_version` is v0 and keeps its frozen raw-byte checksum (ADR-025).
"""
import hashlib
import json
import re
from datetime import datetime

import pytest

from pmtest import pm_dir, pm_warnings, write_revision
from promptmigrate import protocol, revisions
from promptmigrate.core import SchemaError, check, load_revisions, revision, upgrade

A, B = "a" * 12, "b" * 12
CREATED = "2026-10-30T00:00:00+00:00"
CFG1 = {"messages": [{"role": "system", "content": "Answer briefly."}]}
CREATE = {"assistant": {"before": None, "after": CFG1}}
V1_KEYS = {"format_version", "revision", "down_revision", "message", "created_at", "changes"}
# "v1:" + SHA-256 of canonical(v1_doc()); computed once on 2026-11-13 and pinned so that any change to
# `protocol.canonical` or to the v1 checksum rule fails here first.
PIN_CREATE = "v1:96960da22acff0e36782cd30443bab43ffc2a35ad6952a9d4455d75ef72c8969"


def v1_doc(**overrides):
    item = {"format_version": 1, "revision": A, "down_revision": None, "message": "Create assistant",
            "created_at": CREATED, "changes": CREATE}
    item.update(overrides)
    return item


def put(project, data: bytes, name=A):
    path = pm_dir(project) / "versions" / f"{name}.json"
    path.write_bytes(data)
    return path


def reversed_keys(value):
    """The same JSON value with every object's keys in reverse order."""
    if isinstance(value, dict):
        return {key: reversed_keys(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [reversed_keys(item) for item in value]
    return value


PRETTY = (json.dumps(v1_doc(), indent=2) + "\n").encode("utf-8")

VARIANTS = {
    "pretty": PRETTY,
    "crlf": PRETTY.replace(b"\n", b"\r\n"),
    "compact": json.dumps(v1_doc(), separators=(",", ":")).encode("utf-8"),
    "indent-tab": json.dumps(v1_doc(), indent="\t").encode("utf-8"),
    "reversed-keys": json.dumps(reversed_keys(v1_doc()), indent=4).encode("utf-8"),
    "unicode-escape": PRETTY.replace(b'"Answer', b'"\\u0041nswer'),
    "bom": b"\xef\xbb\xbf" + PRETTY,
    "trailing-space": PRETTY + b"   \n\n",
}


# --- reader: v1 is recognised, v0 is unchanged ----------------------------------------------------

def test_v1_checksum_is_pinned(project):
    put(project, PRETTY)
    [revision] = load_revisions(project)
    assert revision.format_version == 1
    assert revision.checksum == PIN_CREATE


def test_v1_checksum_is_tagged_sha256_of_canonical_parsed_object(project):
    put(project, PRETTY)
    [revision] = load_revisions(project)
    digest = hashlib.sha256(protocol.canonical(v1_doc()).encode("utf-8")).hexdigest()
    assert revision.checksum == "v1:" + digest


def test_v0_file_keeps_format_version_0_and_raw_byte_checksum(project):
    path = write_revision(project, A, None, CREATE)
    [revision] = load_revisions(project)
    assert revision.format_version == 0
    assert revision.checksum == hashlib.sha256(path.read_bytes()).hexdigest()


def test_v1_file_loads_without_warnings(project):
    write_revision(project, A, None, CREATE, format_version=1)
    revisions_, warned = pm_warnings(load_revisions, project)
    assert [r.format_version for r in revisions_] == [1]
    assert warned == []


# --- I16: the v1 checksum ignores serialization and follows every value ---------------------------

@pytest.mark.parametrize("variant", sorted(VARIANTS))
def test_v1_checksum_ignores_serialization(project, variant):
    put(project, VARIANTS[variant])
    [revision] = load_revisions(project)
    assert revision.checksum == PIN_CREATE


MUTATIONS = {
    "message": {"message": "Create assistant!"},
    "created_at": {"created_at": "2026-10-30T00:00:01+00:00"},
    "down_revision": {"down_revision": B},
    "changes-after": {"changes": {"assistant": {"before": None, "after": {"messages": []}}}},
    "changes-before": {"changes": {"assistant": {"before": CFG1, "after": CFG1}}},
    "changes-name": {"changes": {"assistant2": {"before": None, "after": CFG1}}},
    "revision": {"revision": B},
}


@pytest.mark.parametrize("field", sorted(MUTATIONS))
def test_v1_checksum_changes_with_any_value(field):
    assert revisions._v1_checksum(v1_doc()) == PIN_CREATE
    assert revisions._v1_checksum(v1_doc(**MUTATIONS[field])) != PIN_CREATE


def test_v1_checksum_distinguishes_1_1_0_and_true():
    """Consistent with ADR-003a: canonical JSON keeps 1, 1.0 and true apart, so the checksum does too."""
    assert len({revisions._v1_checksum({"x": value}) for value in (1, 1.0, True)}) == 3


# --- format_version values -------------------------------------------------------------------------

@pytest.mark.parametrize("literal", ["0", "2", "-1", "true", "false", "null", "1.0", "1e0", '"1"', "[1]", '{"v": 1}'])
def test_unsupported_format_version_is_schema_error(project, literal):
    put(project, PRETTY.replace(b'"format_version": 1', b'"format_version": ' + literal.encode()))
    with pytest.raises(SchemaError, match=r"^Unsupported format_version in aaaaaaaaaaaa\.json$"):
        load_revisions(project)


def test_unknown_v1_top_level_key_is_schema_error(project):
    put(project, json.dumps(v1_doc(author="x", notes="y")).encode("utf-8"))
    with pytest.raises(SchemaError, match=r"^Unknown top-level key in aaaaaaaaaaaa\.json: author, notes$"):
        load_revisions(project)


@pytest.mark.parametrize("key", sorted(V1_KEYS - {"format_version"}))
def test_each_v1_key_is_required(project, key):
    item = v1_doc()
    del item[key]
    put(project, json.dumps(item).encode("utf-8"))
    with pytest.raises(SchemaError, match=r"^Invalid migration format: aaaaaaaaaaaa\.json$"):
        load_revisions(project)


# --- generator: new revisions are v1 with LF line endings -----------------------------------------

def test_generated_revision_is_v1_with_lf_line_endings(project):
    created = revision(project, "initial")
    raw = created.path.read_bytes()
    item = json.loads(raw)
    assert b"\r" not in raw and raw.endswith(b"}\n")
    assert set(item) == V1_KEYS and type(item["format_version"]) is int and item["format_version"] == 1
    assert created.format_version == 1
    assert created.checksum == revisions._v1_checksum(item)


def test_generated_revision_survives_whitespace_edit(project):
    created = revision(project, "initial")
    upgrade(project, "dev")
    created.path.write_bytes(created.path.read_bytes().replace(b"\n", b"\n  ") + b"\n")
    assert check(project, "dev", require_head=True) == (1, 1)


class _FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 11, 13, 12, 0, 0, 123456, tzinfo=tz)


def test_size_check_counts_the_lf_bytes_written(project, monkeypatch):
    monkeypatch.setattr("promptmigrate.commands.revision.datetime", _FixedClock)
    limit = protocol.limits.MAX_REVISION_BYTES
    monkeypatch.setattr(protocol.limits, "MAX_REVISION_BYTES", 1)
    with pytest.raises(SchemaError, match=r"^New revision would be (\d+) bytes; the limit is 1$") as refused:
        revision(project, "initial")
    reported = int(re.search(r"would be (\d+) bytes", str(refused.value)).group(1))
    monkeypatch.setattr(protocol.limits, "MAX_REVISION_BYTES", limit)
    assert revision(project, "initial").path.stat().st_size == reported
