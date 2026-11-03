"""PR 2: pin current revision-graph and target behaviour before any refactor."""
import pytest

from pmtest import create, set_draft, write_revision
from promptmigrate.core import MigrationError, check, downgrade, load_revisions, revision, upgrade

A, B, C = "a" * 12, "b" * 12, "c" * 12


# --- revision graph -------------------------------------------------------------------------

def test_two_roots_rejected(project):
    write_revision(project, A, None, {"x": create()})
    write_revision(project, B, None, {"y": create()})
    with pytest.raises(MigrationError, match="exactly one root revision"):
        load_revisions(project)


def test_missing_parent_rejected(project):
    write_revision(project, A, None, {"x": create()})
    write_revision(project, B, C, {"y": create()})
    with pytest.raises(MigrationError, match=f"Missing parent of revision {B}: {C}"):
        load_revisions(project)


def test_cycle_rejected(project):
    write_revision(project, A, None, {"x": create()})
    write_revision(project, B, C, {"y": create()})
    write_revision(project, C, B, {"z": create()})
    with pytest.raises(MigrationError, match="Disconnected or cyclic"):
        load_revisions(project)


def test_branch_rejected(project):
    write_revision(project, A, None, {"x": create()})
    write_revision(project, B, A, {"y": create()})
    write_revision(project, C, A, {"z": create()})
    with pytest.raises(MigrationError, match="Branching detected"):
        load_revisions(project)


def test_duplicate_id_rejected(project):
    write_revision(project, A, None, {"x": create()}, filename="one")
    write_revision(project, A, None, {"y": create()}, filename="two")
    with pytest.raises(MigrationError, match=f"Duplicate revision id: {A}"):
        load_revisions(project)


def test_malformed_id_rejected(project):
    write_revision(project, "XYZ", None, {"x": create()})
    with pytest.raises(MigrationError, match="Invalid revision id in XYZ.json"):
        load_revisions(project)


def test_empty_changes_rejected(project):
    write_revision(project, A, None, {})
    with pytest.raises(MigrationError, match="nonempty changes"):
        load_revisions(project)


def test_missing_keys_rejected(project):
    (project / ".promptmigrate" / "versions" / "x.json").write_text('{"revision": "aaaaaaaaaaaa"}', encoding="utf-8")
    with pytest.raises(MigrationError, match="Invalid migration format: x.json"):
        load_revisions(project)


# --- targets --------------------------------------------------------------------------------

@pytest.fixture
def two_revisions(project):
    first = revision(project, "one")
    set_draft(project, "assistant", {"messages": [{"role": "system", "content": "two"}]})
    second = revision(project, "two")
    return first.revision, second.revision


def test_upgrade_head_is_idempotent(project, two_revisions):
    assert upgrade(project, "dev") == list(two_revisions)
    assert upgrade(project, "dev") == []


def test_downgrade_at_base_is_noop(project, two_revisions):
    assert downgrade(project, "dev") == []


def test_upgrade_to_older_target_rejected(project, two_revisions):
    upgrade(project, "dev")
    with pytest.raises(MigrationError, match="behind current revision; use downgrade"):
        upgrade(project, "dev", two_revisions[0])


def test_downgrade_to_newer_target_rejected(project, two_revisions):
    upgrade(project, "dev", two_revisions[0])
    with pytest.raises(MigrationError, match="ahead of current revision; use upgrade"):
        downgrade(project, "dev", two_revisions[1])


@pytest.mark.parametrize("operation", [upgrade, downgrade])
def test_unknown_target_rejected(project, two_revisions, operation):
    with pytest.raises(MigrationError, match="Unknown target revision: ffffffffffff"):
        operation(project, "dev", "f" * 12)


def test_staging_may_lag_behind_head(project, two_revisions):
    upgrade(project, "dev")
    assert check(project, "staging") == (0, 2)
    with pytest.raises(MigrationError, match="Environment is behind head: 2 pending revisions"):
        check(project, "staging", require_head=True)
