"""PR 3: strict JSON loading of drafts and revision files (tier A, plus the draft file limits)."""
import pathlib
import re

import pytest

from pmtest import create, pm_dir, sized_draft, symlink_or_skip, write_revision
from promptmigrate import protocol
from promptmigrate.core import draft_diff, load_revisions, revision
from promptmigrate.errors import SchemaError

A = "a" * 12
DEEP = "[" * 100_000 + "]" * 100_000  # deeper than the json parser's recursion limit
REVISION = ('{"revision": "%s", "down_revision": null, "message": "m", "created_at": "t", '
            '"changes": {"assistant": {"before": null, "after": {"x": %s}}}}')


def draft_file(project):
    return pm_dir(project) / "drafts" / "assistant.json"


def revision_file(project):
    return pm_dir(project) / "versions" / f"{A}.json"


def write_draft(project, text):
    draft_file(project).write_text(text, encoding="utf-8")


def write_revision_text(project, text):
    revision_file(project).write_text(text, encoding="utf-8")


# --- duplicate keys ---------------------------------------------------------------------------

def test_duplicate_key_in_draft_names_key_and_file(project):
    write_draft(project, '{"model": "a", "model": "b"}')
    with pytest.raises(SchemaError, match=re.escape("Invalid JSON draft assistant.json: duplicate key 'model'")):
        draft_diff(project)


def test_nested_duplicate_key_in_draft(project):
    write_draft(project, '{"parameters": {"t": 1, "t": 2}}')
    with pytest.raises(SchemaError, match=re.escape("duplicate key 't'")):
        draft_diff(project)


def test_duplicate_key_in_revision(project):
    text = REVISION.replace('"message": "m"', '"message": "m", "message": "n"') % (A, "1")
    write_revision_text(project, text)
    with pytest.raises(SchemaError, match=re.escape(f"Unreadable migration {A}.json: duplicate key 'message'")):
        load_revisions(project)


# --- non-finite numbers -----------------------------------------------------------------------

@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_number_in_draft(project, constant):
    write_draft(project, '{"x": %s}' % constant)
    message = f"Invalid JSON draft assistant.json: non-finite number {constant} is not allowed"
    with pytest.raises(SchemaError, match=re.escape(message)):
        draft_diff(project)


def test_non_finite_number_in_revision(project):
    write_revision_text(project, REVISION % (A, "NaN"))
    with pytest.raises(SchemaError, match=re.escape(f"Unreadable migration {A}.json: non-finite number NaN")):
        load_revisions(project)


# --- number literals that overflow to infinity (C1, I15) ----------------------------------------

@pytest.mark.parametrize("literal", ["1e400", "-1e400"])
def test_overflowing_number_in_draft_rejected(project, literal):
    write_draft(project, '{"x": %s}' % literal)
    message = "Invalid JSON draft assistant.json: number out of range"
    with pytest.raises(SchemaError, match=re.escape(message)):
        draft_diff(project)


def test_overflowing_draft_number_blocks_revision_without_writing(project):
    """I15: revision() must never write Infinity to a new file."""
    write_draft(project, '{"x": 1e400}')
    with pytest.raises(SchemaError, match=re.escape("Invalid JSON draft assistant.json: number out of range")):
        revision(project, "inf")
    assert list((pm_dir(project) / "versions").iterdir()) == []


def test_overflowing_number_in_revision_rejected(project):
    write_revision_text(project, REVISION % (A, "1e400"))
    message = f"Unreadable migration {A}.json: number out of range"
    with pytest.raises(SchemaError, match=re.escape(message)):
        load_revisions(project)


# --- nesting the parser can't handle -----------------------------------------------------------

def test_draft_nested_too_deep_to_parse(project):
    write_draft(project, '{"x": %s}' % DEEP)
    with pytest.raises(SchemaError, match=re.escape("Invalid JSON draft assistant.json: nested too deep to parse")):
        draft_diff(project)


def test_revision_nested_too_deep_to_parse(project):
    write_revision_text(project, DEEP)
    with pytest.raises(SchemaError, match=re.escape(f"Unreadable migration {A}.json: nested too deep to parse")):
        load_revisions(project)


# --- BOM behaviour is unchanged (spec §3) ------------------------------------------------------

def test_bom_in_draft_still_rejected(project):
    draft_file(project).write_bytes(b"\xef\xbb\xbf{}")
    with pytest.raises(SchemaError, match=re.escape("Invalid JSON draft assistant.json: Unexpected UTF-8 BOM")):
        draft_diff(project)


def test_bom_in_revision_still_accepted(project):
    write_revision(project, A, None, {"assistant": create()})
    revision_file(project).write_bytes(b"\xef\xbb\xbf" + revision_file(project).read_bytes())
    assert [r.revision for r in load_revisions(project)] == [A]


# --- draft size limit (patched small; the real 1 MiB limit round-trips in test_legacy_warnings) --

def test_draft_at_size_limit_loads(project, monkeypatch):
    monkeypatch.setattr(protocol, "MAX_DRAFT_BYTES", 200)
    sized_draft(project, 200)
    assert "assistant" in draft_diff(project)


def test_draft_over_size_limit_rejected(project, monkeypatch):
    monkeypatch.setattr(protocol, "MAX_DRAFT_BYTES", 200)
    sized_draft(project, 201)
    message = "Invalid JSON draft assistant.json: 201 bytes exceeds the 200-byte limit"
    with pytest.raises(SchemaError, match=re.escape(message)):
        draft_diff(project)


# --- symlinks (skipped where os.symlink is not permitted) --------------------------------------

def test_symlinked_draft_inside_tree_rejected(project):
    target = pm_dir(project) / "shared.json"
    draft_file(project).replace(target)
    symlink_or_skip(draft_file(project), target)
    with pytest.raises(SchemaError, match=re.escape("Invalid JSON draft assistant.json: drafts must not be symlinks")):
        draft_diff(project)


def test_symlinked_draft_outside_tree_rejected(project):
    outside = project / "outside.json"
    draft_file(project).replace(outside)
    symlink_or_skip(draft_file(project), outside)
    message = "Invalid JSON draft assistant.json: resolves outside .promptmigrate/"
    with pytest.raises(SchemaError, match=re.escape(message)):
        draft_diff(project)


def test_symlinked_revision_outside_tree_rejected(project):
    outside = project / "outside.json"
    write_revision(project, A, None, {"assistant": create()})
    revision_file(project).replace(outside)
    symlink_or_skip(revision_file(project), outside)
    message = f"Unreadable migration {A}.json: resolves outside .promptmigrate/"
    with pytest.raises(SchemaError, match=re.escape(message)):
        load_revisions(project)


# --- symlink loops raise an untyped RuntimeError on Python 3.10-3.12 (I2) ----------------------

def test_symlink_loop_in_draft_is_a_schema_error(project, monkeypatch):
    original = pathlib.Path.resolve

    def resolve(self, strict=False):
        if self.name == "assistant.json":
            raise RuntimeError("Symlink loop from 'x'")
        return original(self, strict)

    monkeypatch.setattr(pathlib.Path, "resolve", resolve)
    message = "Invalid JSON draft assistant.json: symlink loop"
    with pytest.raises(SchemaError, match=re.escape(message)):
        draft_diff(project)
