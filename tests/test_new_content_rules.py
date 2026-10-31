"""PR 3: tier-B hygiene and limit rules reject drafts and newly generated revisions (I9, I15)."""
import re

import pytest

from pmtest import CFG, nested_config, pm_dir, pm_warnings, set_draft
from promptmigrate import core, protocol
from promptmigrate.core import draft_diff, load_revisions, revision
from promptmigrate.errors import SchemaError


def versions(project):
    return sorted((pm_dir(project) / "versions").iterdir())


BAD_RESERVED = [
    ("model", 1),
    ("model", None),
    ("parameters", []),
    ("tools", {}),
    ("response_schema", "x"),
    ("response_schema", []),
]


@pytest.mark.parametrize("field, value", BAD_RESERVED)
def test_reserved_field_type_rejected_in_draft_and_revision(project, field, value):
    set_draft(project, "assistant", {**CFG, field: value})
    message = f"Invalid draft assistant.json: reserved-field-type assistant.{field}"
    with pytest.raises(SchemaError, match=re.escape(message)):
        draft_diff(project)
    with pytest.raises(SchemaError, match=re.escape(message)):
        revision(project, "bad")
    assert versions(project) == []


def test_reserved_fields_with_valid_types_accepted(project):
    """Guard: valid values and absent fields pass."""
    set_draft(project, "assistant", {**CFG, "model": "m", "parameters": {}, "tools": [], "response_schema": None})
    set_draft(project, "other", {"response_schema": {}, "note": 1})
    assert sorted(draft_diff(project)) == ["assistant", "other"]


def test_draft_at_depth_limit_accepted(project):
    """Guard: depth 64 is allowed."""
    set_draft(project, "assistant", nested_config(64))
    assert "assistant" in draft_diff(project)


def test_draft_over_depth_limit_refused_before_writing(project):
    set_draft(project, "assistant", nested_config(65))
    with pytest.raises(SchemaError, match=re.escape("Invalid draft assistant.json: config-depth assistant")):
        revision(project, "deep")
    assert versions(project) == []


def test_case_colliding_draft_names_rejected(project):
    set_draft(project, "Assistant", CFG)
    if len(list((pm_dir(project) / "drafts").glob("*.json"))) == 1:
        pytest.skip("case-insensitive filesystem: Assistant.json and assistant.json are one file")
    with pytest.raises(SchemaError, match=re.escape("Invalid drafts: case-collision Assistant/assistant")):
        draft_diff(project)


def test_revision_over_size_limit_refused_before_writing(project, monkeypatch):
    monkeypatch.setattr(protocol, "MAX_REVISION_BYTES", 100)
    with pytest.raises(SchemaError, match=r"New revision would be \d+ bytes; the limit is 100"):
        revision(project, "initial")
    assert versions(project) == []


def test_revision_size_limit_checked_against_real_file_size(project, monkeypatch):
    """D5: the pre-write size check (test_revision_over_size_limit_refused_before_writing) is pinned against
    the real on-disk file size, not a tautological guess at it."""
    r = revision(project, "initial")
    size = r.path.stat().st_size
    r.path.unlink()

    # isoformat() drops the 7-character microseconds part when microseconds is 0, so the real size can
    # vary by up to 7 bytes between runs; the 8-byte margin below absorbs that.
    monkeypatch.setattr(protocol, "MAX_REVISION_BYTES", size - 8)
    with pytest.raises(SchemaError, match=r"New revision would be \d+ bytes; the limit is"):
        revision(project, "initial")
    assert versions(project) == []

    monkeypatch.setattr(protocol, "MAX_REVISION_BYTES", size + 50)
    revision(project, "initial")
    assert pm_warnings(load_revisions, project)[1] == []


def test_revision_rechecks_after_values(project, monkeypatch):
    """I15 defence in depth: even with draft validation bypassed, revision() refuses an invalid new after."""
    monkeypatch.setattr(core, "read_drafts", lambda project_dir: {"assistant": {"model": 1}})
    message = "New revision would be invalid: reserved-field-type assistant.model"
    with pytest.raises(SchemaError, match=re.escape(message)):
        revision(project, "bypass")
    assert versions(project) == []
