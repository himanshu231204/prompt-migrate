"""PR 7: canonical artifact hash — CRLF vs LF produces different canonical hashes; v0 keeps raw-byte checksum; v1 carries both."""
import hashlib
import json

import pytest

from pmtest import CFG, write_revision
from promptmigrate.core import load_revisions
from promptmigrate.protocol.format import artifact_hash, canonical_artifact_bytes, FORMAT_VERSION_V1


def _raw_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_v1_bytes() -> bytes:
    item = {
        "revision": "a" * 12,
        "down_revision": None,
        "message": "hash me",
        "created_at": "2026-11-05T00:00:00+00:00",
        "format_version": 1,
        "changes": {"assistant": {"before": None, "after": CFG}},
    }
    return json.dumps(item, sort_keys=True, indent=2).encode("utf-8")


def test_canonical_hash_differs_under_crlf():
    """Same logical content, different line endings => SAME canonical artifact hash (CRLF false-tamper eliminated).

    The whole point of v1 canonical hashing is that whitespace-only edits (LF <-> CRLF) do not change the
    hash, so a whitespace-only edit to a v1 artifact is NOT flagged as tampering.
    """
    lf = _make_v1_bytes()
    crlf = lf.replace(b"\n", b"\r\n")
    assert artifact_hash(lf, FORMAT_VERSION_V1) == artifact_hash(crlf, FORMAT_VERSION_V1)
    assert canonical_artifact_bytes(json.loads(lf)) == canonical_artifact_bytes(json.loads(crlf))


def test_v0_checksum_stays_raw_byte(project):
    """A v0 artifact's checksum is the raw SHA-256 of the on-disk bytes (unchanged behavior)."""
    write_revision(project, "a" * 12, None, {"assistant": {"before": None, "after": CFG}})
    path = project / ".promptmigrate" / "versions" / "aaaaaaaaaaaa.json"
    raw = path.read_bytes()
    revisions = load_revisions(project)
    assert revisions[0].format_version == 0
    assert revisions[0].checksum == _raw_sha256(raw)
    assert revisions[0].artifact_sha256 is None


def test_v1_artifact_carries_both_hashes(project):
    """A v1 artifact carries both the raw checksum and the canonical artifact_sha256."""
    data = _make_v1_bytes()
    path = project / ".promptmigrate" / "versions" / "aaaaaaaaaaaa.json"
    path.write_bytes(data)
    revisions = load_revisions(project)
    assert revisions[0].format_version == 1
    assert revisions[0].checksum == _raw_sha256(data)  # raw hash still present
    assert revisions[0].artifact_sha256 == artifact_hash(data, FORMAT_VERSION_V1)
    assert revisions[0].checksum != revisions[0].artifact_sha256  # they differ when bytes aren't canonical


def test_artifact_hash_selector_for_v0():
    """format_version 0 selects the raw-byte hash."""
    data = b'{"revision": "a" * 12}'
    assert artifact_hash(data, 0) == _raw_sha256(data)


def test_artifact_hash_selector_for_v1():
    """format_version 1 selects the canonical artifact hash."""
    data = _make_v1_bytes()
    expected = hashlib.sha256(canonical_artifact_bytes(json.loads(data))).hexdigest()
    assert artifact_hash(data, FORMAT_VERSION_V1) == expected