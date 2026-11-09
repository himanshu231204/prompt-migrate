"""PR 7: revision reader migration — v0 and v1 artifacts produce usable Revision objects; v1 verification uses canonical hash."""
import json

import pytest

from pmtest import CFG, write_revision
from promptmigrate.core import load_revisions
from promptmigrate.errors import SchemaError


def test_v0_revision_produces_usable_revision_object(project):
    """Loading a v0 revision gives a Revision with all expected fields and no format_version surprises."""
    write_revision(project, "a" * 12, None, {"assistant": {"before": None, "after": CFG}})
    revisions = load_revisions(project)
    r = revisions[0]
    assert r.revision == "a" * 12
    assert r.down_revision is None
    assert r.message == "m"
    assert r.format_version == 0
    assert r.artifact_sha256 is None
    assert r.changes == {"assistant": {"before": None, "after": CFG}}


def test_v1_revision_produces_usable_revision_object(project):
    """Loading a v1 revision gives a Revision with format_version and artifact_sha256 populated."""
    item = {
        "revision": "a" * 12,
        "down_revision": None,
        "message": "v1",
        "created_at": "2026-11-05T00:00:00+00:00",
        "format_version": 1,
        "changes": {"assistant": {"before": None, "after": CFG}},
    }
    path = project / ".promptmigrate" / "versions" / "aaaaaaaaaaaa.json"
    path.write_text(json.dumps(item), encoding="utf-8")
    revisions = load_revisions(project)
    r = revisions[0]
    assert r.format_version == 1
    assert isinstance(r.artifact_sha256, str)
    assert len(r.artifact_sha256) == 64


def test_v0_and_v1_can_coexist_in_one_chain(project):
    """A chain mixing v0 and v1 revisions loads (format_version is per-artifact, not per-project)."""
    write_revision(project, "a" * 12, None, {"assistant": {"before": None, "after": CFG}})
    item = {
        "revision": "b" * 12,
        "down_revision": "a" * 12,
        "message": "v1 second",
        "created_at": "2026-11-05T00:00:00+00:00",
        "format_version": 1,
        "changes": {"assistant": {"before": CFG, "after": {**CFG, "model": "provider/model-id"}}},
    }
    path = project / ".promptmigrate" / "versions" / "bbbbbbbbbbbb.json"
    path.write_text(json.dumps(item), encoding="utf-8")
    revisions = load_revisions(project)
    assert [r.format_version for r in revisions] == [0, 1]
    assert revisions[1].down_revision == "a" * 12