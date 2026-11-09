"""PR 7: format_version stability — v0 artifacts load, v1 artifacts load, unknown format_version fails closed (Q1, Q4)."""
import json

import pytest

from pmtest import CFG, write_revision
from promptmigrate.core import load_revisions
from promptmigrate.errors import RevisionGraphError, SchemaError


def _write_v1(project, rid="a" * 12, parent=None, changes=None):
    """Write a revision file in v1 format (with format_version: 1)."""
    if changes is None:
        changes = {"assistant": {"before": None, "after": CFG}}
    item = {
        "revision": rid,
        "down_revision": parent,
        "message": "v1 revision",
        "created_at": "2026-11-05T00:00:00+00:00",
        "format_version": 1,
        "changes": changes,
    }
    path = project / ".promptmigrate" / "versions" / f"{rid}.json"
    path.write_text(json.dumps(item, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path


def test_v0_artifact_without_format_version_loads(project):
    """A starter-format revision (no format_version) loads with format_version == 0."""
    write_revision(project, "a" * 12, None, {"assistant": {"before": None, "after": CFG}})
    revisions = load_revisions(project)
    assert len(revisions) == 1
    assert revisions[0].format_version == 0
    assert revisions[0].artifact_sha256 is None


def test_v1_artifact_with_format_version_1_loads(project):
    """A v1 artifact (format_version: 1) loads with format_version == 1 and an artifact_sha256."""
    _write_v1(project)
    revisions = load_revisions(project)
    assert len(revisions) == 1
    assert revisions[0].format_version == 1
    assert revisions[0].artifact_sha256 is not None
    assert len(revisions[0].artifact_sha256) == 64  # SHA-256 hex


def test_unknown_format_version_fails_closed(project):
    """An unsupported format_version raises SchemaError and writes nothing."""
    path = write_revision(project, "a" * 12, None, {"assistant": {"before": None, "after": CFG}})
    text = path.read_text(encoding="utf-8")
    item = json.loads(text)
    item["format_version"] = 99
    path.write_text(json.dumps(item), encoding="utf-8")
    with pytest.raises(SchemaError, match="Unsupported format_version"):
        load_revisions(project)


def test_format_version_zero_explicit_is_v0(project):
    """An explicit format_version: 0 is treated as v0 (raw-byte checksum semantics)."""
    path = write_revision(project, "a" * 12, None, {"assistant": {"before": None, "after": CFG}})
    text = path.read_text(encoding="utf-8")
    item = json.loads(text)
    item["format_version"] = 0
    path.write_text(json.dumps(item), encoding="utf-8")
    revisions = load_revisions(project)
    assert revisions[0].format_version == 0
    assert revisions[0].artifact_sha256 is None


def test_v1_requires_nonempty_changes_like_v0(project):
    """A v1 artifact with empty changes is still rejected (format_version doesn't weaken validation)."""
    item = {
        "revision": "a" * 12,
        "down_revision": None,
        "message": "empty v1",
        "created_at": "2026-11-05T00:00:00+00:00",
        "format_version": 1,
        "changes": {},
    }
    path = project / ".promptmigrate" / "versions" / "aaaaaaaaaaaa.json"
    path.write_text(json.dumps(item), encoding="utf-8")
    with pytest.raises(SchemaError, match="nonempty changes"):
        load_revisions(project)


def test_v1_linear_chain_still_enforced(project):
    """format_version does not bypass the one-linear-chain graph rule."""
    _write_v1(project, "a" * 12, None)
    _write_v1(project, "b" * 12, "a" * 12)
    _write_v1(project, "c" * 12, "a" * 12)  # branch: two children of a
    with pytest.raises(RevisionGraphError, match="Branching detected"):
        load_revisions(project)