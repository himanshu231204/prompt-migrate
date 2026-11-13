"""PR 3: every handled error raises a specific MigrationError subclass; messages are unchanged."""
import json
import re
import sqlite3
from contextlib import closing

import pytest

from pmtest import CFG, create, pm_dir, set_draft, write_revision
from promptmigrate import core, errors
from promptmigrate.core import check, downgrade, draft_diff, get_config, init, load_revisions, revision, upgrade
from promptmigrate.errors import (
    DriftError, InitializationError, IntegrityError, LegacyRevisionWarning, MigrationConflictError, MigrationError,
    PendingRevisionsError, PromptMigrateWarning, RevisionGraphError, SchemaError, TargetError,
)

A, B, C = "a" * 12, "b" * 12, "c" * 12
CFG2 = {"messages": [{"role": "system", "content": "B"}]}


def test_hierarchy():
    assert core.MigrationError is errors.MigrationError
    for cls in (InitializationError, SchemaError, RevisionGraphError, MigrationConflictError, DriftError,
                IntegrityError, TargetError, PendingRevisionsError):
        assert issubclass(cls, MigrationError)
    assert issubclass(PromptMigrateWarning, UserWarning)
    assert issubclass(LegacyRevisionWarning, PromptMigrateWarning)


# --- InitializationError ----------------------------------------------------------------------

def test_not_initialized(tmp_path):
    with pytest.raises(InitializationError, match="Not initialized. Run: promptmigrate init"):
        load_revisions(tmp_path)


def test_already_initialized(project):
    with pytest.raises(InitializationError, match="Already exists"):
        init(project)


# --- SchemaError: drafts ----------------------------------------------------------------------

def _draft_text(text):
    def write(project):
        (pm_dir(project) / "drafts" / "assistant.json").write_text(text, encoding="utf-8")
    return write


DRAFT_CASES = {
    "bad name": (lambda p: set_draft(p, "1bad", CFG), "Invalid prompt name: '1bad'"),
    "not an object": (lambda p: set_draft(p, "assistant", []), "Prompt 'assistant' must contain a JSON object"),
    "bad messages": (lambda p: set_draft(p, "assistant", {"messages": [{"role": 1}]}),
                     "Prompt 'assistant' has invalid messages"),
    "invalid json": (_draft_text("{"), "Invalid JSON draft assistant.json"),
}


@pytest.mark.parametrize("case", sorted(DRAFT_CASES))
def test_draft_schema_errors(project, case):
    setup, message = DRAFT_CASES[case]
    setup(project)
    with pytest.raises(SchemaError, match=re.escape(message)):
        draft_diff(project)


# --- SchemaError: revision files --------------------------------------------------------------

def _revision_text(text):
    def write(project):
        (pm_dir(project) / "versions" / f"{A}.json").write_text(text, encoding="utf-8")
    return write


REVISION_CASES = {
    "unparseable": (_revision_text("{"), f"Unreadable migration {A}.json"),
    "missing keys": (_revision_text('{"revision": "%s"}' % A), f"Invalid migration format: {A}.json"),
    "malformed id": (lambda p: write_revision(p, "XYZ", None, {"x": create()}), "Invalid revision id in XYZ.json"),
    "malformed parent": (lambda p: write_revision(p, A, "nope", {"x": create()}), f"Invalid down_revision in {A}.json"),
    "bad metadata": (lambda p: write_revision(p, A, None, {"x": create()}, message=1), f"Invalid metadata in {A}.json"),
    "empty changes": (lambda p: write_revision(p, A, None, {}), f"Migration must contain nonempty changes: {A}.json"),
    "bad change": (lambda p: write_revision(p, A, None, {"x": {"after": None}}),
                   f"Invalid change operation in {A}.json: x"),
    "bad config": (lambda p: write_revision(p, A, None, {"x": create([])}), "Prompt 'x' must contain a JSON object"),
}


@pytest.mark.parametrize("case", sorted(REVISION_CASES))
def test_revision_schema_errors(project, case):
    setup, message = REVISION_CASES[case]
    setup(project)
    with pytest.raises(SchemaError, match=re.escape(message)):
        load_revisions(project)


# --- RevisionGraphError -----------------------------------------------------------------------

def _duplicate_id(p):
    write_revision(p, A, None, {"x": create()}, filename="one")
    write_revision(p, A, None, {"y": create()}, filename="two")


def _two_roots(p):
    write_revision(p, A, None, {"x": create()})
    write_revision(p, B, None, {"y": create()})


def _missing_parent(p):
    write_revision(p, A, None, {"x": create()})
    write_revision(p, B, C, {"y": create()})


def _branch(p):
    write_revision(p, A, None, {"x": create()})
    write_revision(p, B, A, {"y": create()})
    write_revision(p, C, A, {"z": create()})


def _cycle(p):
    write_revision(p, A, None, {"x": create()})
    write_revision(p, B, C, {"y": create()})
    write_revision(p, C, B, {"z": create()})


GRAPH_CASES = {
    "duplicate id": (_duplicate_id, f"Duplicate revision id: {A}"),
    "two roots": (_two_roots, "MVP requires exactly one root revision (linear history)"),
    "missing parent": (_missing_parent, f"Missing parent of revision {B}: {C}"),
    "branch": (_branch, "Branching detected"),
    "cycle": (_cycle, "Disconnected or cyclic migration history"),
}


@pytest.mark.parametrize("case", sorted(GRAPH_CASES))
def test_graph_errors(project, case):
    setup, message = GRAPH_CASES[case]
    setup(project)
    with pytest.raises(RevisionGraphError, match=re.escape(message)):
        load_revisions(project)


# --- MigrationConflictError -------------------------------------------------------------------

def test_precondition_mismatch_is_conflict(project):
    write_revision(project, A, None, {"x": create()})
    write_revision(project, B, A, {"x": {"before": CFG2, "after": CFG}})
    with pytest.raises(MigrationConflictError, match=f"upgrade {B}: unexpected current value for 'x'"):
        load_revisions(project)


# --- IntegrityError, DriftError, PendingRevisionsError ----------------------------------------

@pytest.fixture
def applied(project):
    first = revision(project, "initial")
    upgrade(project, "dev")
    return first


def test_edited_applied_revision_is_integrity_error(project, applied):
    item = json.loads(applied.path.read_bytes())
    applied.path.write_text(json.dumps({**item, "message": "edited after apply"}), encoding="utf-8")
    with pytest.raises(IntegrityError, match=f"Migration file was modified after apply: {applied.revision}"):
        check(project, "dev")


def test_diverged_ledger_is_integrity_error(project, applied):
    applied.path.unlink()
    write_revision(project, A, None, {"assistant": create()})
    with pytest.raises(IntegrityError, match="Applied revisions diverge from source history at index 0"):
        check(project, "dev")


def test_ledger_longer_than_history_is_integrity_error(project, applied):
    applied.path.unlink()
    with pytest.raises(IntegrityError, match="more applied revisions than source history"):
        check(project, "dev")


def test_state_drift_is_drift_error(project, applied):
    with closing(sqlite3.connect(pm_dir(project) / "states" / "dev.sqlite3")) as conn, conn:
        conn.execute("UPDATE prompts SET config='{}' WHERE name='assistant'")
    with pytest.raises(DriftError, match="Environment drift detected for prompts: assistant"):
        check(project, "dev")


def test_behind_head_is_pending(project):
    revision(project, "initial")
    with pytest.raises(PendingRevisionsError, match="Environment is behind head: 1 pending revisions"):
        check(project, "dev", require_head=True)


# --- TargetError ------------------------------------------------------------------------------

@pytest.fixture
def two(project):
    first = revision(project, "one")
    set_draft(project, "assistant", CFG2)
    second = revision(project, "two")
    return first.revision, second.revision


@pytest.mark.parametrize("operation", [upgrade, downgrade])
def test_unknown_target_is_target_error(project, two, operation):
    with pytest.raises(TargetError, match="Unknown target revision: ffffffffffff"):
        operation(project, "dev", "f" * 12)


def test_upgrade_to_older_target_is_target_error(project, two):
    upgrade(project, "dev")
    with pytest.raises(TargetError, match="behind current revision; use downgrade"):
        upgrade(project, "dev", two[0])


def test_downgrade_to_newer_target_is_target_error(project, two):
    upgrade(project, "dev", two[0])
    with pytest.raises(TargetError, match="ahead of current revision; use upgrade"):
        downgrade(project, "dev", two[1])


def test_missing_config_is_target_error(project, applied):
    with pytest.raises(TargetError, match="No prompt named 'nope' in environment 'dev'"):
        get_config(project, "dev", "nope")


# --- Plan decision D1 -------------------------------------------------------------------------

def test_invalid_env_name_is_schema_error(project):
    with pytest.raises(SchemaError, match="Environment must be alphanumeric, starting with a letter"):
        check(project, "../escape")


def test_empty_message_is_schema_error(project):
    with pytest.raises(SchemaError, match="Revision message cannot be empty"):
        revision(project, "   ")


def test_no_changes_is_schema_error(project, applied):
    with pytest.raises(SchemaError, match="No changes between drafts and migration head"):
        revision(project, "again")
