"""PR 2: known bugs pinned as strict xfails. Each reason names the PR that fixes it."""
import pytest

from pmtest import pm_dir, set_draft, tree_snapshot
from promptmigrate.core import MigrationError, check, draft_diff, revision


@pytest.mark.xfail(strict=True, reason="undeclared env reports OK; fixed in PR 4")
def test_undeclared_env_is_an_error(project):
    revision(project, "initial")
    with pytest.raises(MigrationError):
        check(project, "prdo")


@pytest.mark.xfail(strict=True, reason="read commands create state files; fixed in PR 4")
def test_check_does_not_create_files(project):
    revision(project, "initial")
    before = tree_snapshot(project)
    check(project, "dev")
    assert tree_snapshot(project) == before


@pytest.mark.xfail(strict=True, reason="1 and true compare equal; fixed in PR 3")
def test_int_to_bool_change_is_a_diff(project):
    set_draft(project, "assistant", {"parameters": {"stream": 1}})
    revision(project, "initial")
    set_draft(project, "assistant", {"parameters": {"stream": True}})
    assert draft_diff(project)


@pytest.mark.xfail(strict=True, reason="duplicate JSON keys accepted; fixed in PR 3")
def test_duplicate_keys_rejected(project):
    (pm_dir(project) / "drafts" / "assistant.json").write_text('{"model": "a", "model": "b"}', encoding="utf-8")
    with pytest.raises(MigrationError):
        draft_diff(project)


@pytest.mark.xfail(strict=True, reason="NaN accepted; fixed in PR 3")
def test_nan_rejected(project):
    (pm_dir(project) / "drafts" / "assistant.json").write_text('{"x": NaN}', encoding="utf-8")
    with pytest.raises(MigrationError):
        draft_diff(project)
