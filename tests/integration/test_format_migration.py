"""PR 7: format migration — apply v0 and v1 revisions; tampering detected via the correct hash per format version."""
import json

import pytest

from pmtest import CFG, write_revision
from promptmigrate.core import check, load_revisions, upgrade
from promptmigrate.errors import IntegrityError


def _write_v1(project, rid, parent, changes):
    item = {
        "revision": rid,
        "down_revision": parent,
        "message": f"v1 {rid}",
        "created_at": "2026-11-05T00:00:00+00:00",
        "format_version": 1,
        "changes": changes,
    }
    path = project / ".promptmigrate" / "versions" / f"{rid}.json"
    path.write_text(json.dumps(item, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


def test_apply_v0_then_check_and_upgrade_still_works(project):
    """A v0 revision applies, check passes, and upgrade is idempotent (raw-byte checksum semantics)."""
    write_revision(project, "a" * 12, None, {"assistant": {"before": None, "after": CFG}})
    assert upgrade(project, "dev") == ["a" * 12]
    assert check(project, "dev") == (1, 1)
    # Idempotent: upgrade again is a no-op.
    assert upgrade(project, "dev") == []


def test_apply_v1_crlf_is_not_false_tamper(project):
    """A v1 revision applies; a whitespace-only (CRLF) edit is NOT detected (canonical hash normalizes whitespace)."""
    _write_v1(project, "a" * 12, None, {"assistant": {"before": None, "after": CFG}})
    assert upgrade(project, "dev") == ["a" * 12]
    assert check(project, "dev") == (1, 1)

    # Whitespace-only edit (CRLF) of a v1 artifact: same logical content, different bytes.
    # Canonical hash normalizes line endings, so check still passes (no false tamper).
    path = project / ".promptmigrate" / "versions" / "aaaaaaaaaaaa.json"
    raw = path.read_bytes()
    crlf = raw.replace(b"\n", b"\r\n")
    path.write_bytes(crlf)
    assert check(project, "dev") == (1, 1)


def test_apply_v1_real_content_change_is_detected(project):
    """A v1 revision applies; a real content change to its bytes IS detected via canonical hash."""
    _write_v1(project, "a" * 12, None, {"assistant": {"before": None, "after": CFG}})
    assert upgrade(project, "dev") == ["a" * 12]
    assert check(project, "dev") == (1, 1)

    # Real content change: modify the message field (_write_v1 uses "v1 <rid>").
    path = project / ".promptmigrate" / "versions" / "aaaaaaaaaaaa.json"
    raw = path.read_bytes()
    tampered = raw.replace(b'"v1 aaaaaaaaaaaa"', b'"tampered message"')
    path.write_bytes(tampered)

    with pytest.raises(IntegrityError, match="modified after apply"):
        check(project, "dev")


def test_apply_v0_detects_raw_byte_tamper(project):
    """A v0 artifact's raw-byte checksum detects any byte change (whitespace included)."""
    write_revision(project, "a" * 12, None, {"assistant": {"before": None, "after": CFG}})
    assert upgrade(project, "dev") == ["a" * 12]
    path = project / ".promptmigrate" / "versions" / "aaaaaaaaaaaa.json"
    raw = path.read_bytes()
    path.write_bytes(raw.replace(b'"m"', b'"modified message"'))
    with pytest.raises(IntegrityError, match="modified after apply"):
        check(project, "dev")