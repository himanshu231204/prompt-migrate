"""PR 3: configs compare by canonical JSON, so 1, 1.0 and true are distinct (ADR-003a, I3)."""
import sqlite3
from contextlib import closing

import pytest

from pmtest import install_fixture, pm_dir, set_draft
from promptmigrate.core import check, draft_diff, get_config, load_revisions, revision, upgrade
from promptmigrate.errors import DriftError, MigrationConflictError
from promptmigrate.protocol import same


@pytest.mark.parametrize("a, b, expected", [
    (1, True, False),
    (1, 1.0, False),
    (0, False, False),
    ({"a": 1, "b": [2]}, {"b": [2], "a": 1}, True),
    (None, None, True),
])
def test_same(a, b, expected):
    assert same(a, b) is expected


def test_int_to_bool_edit_produces_a_revision(project):
    set_draft(project, "assistant", {"parameters": {"stream": 1}})
    first = revision(project, "stream as int")
    set_draft(project, "assistant", {"parameters": {"stream": True}})
    assert same(draft_diff(project), {"assistant": {"before": {"parameters": {"stream": 1}},
                                                    "after": {"parameters": {"stream": True}}}})
    second = revision(project, "stream as bool")
    assert upgrade(project, "dev") == [first.revision, second.revision]
    assert get_config(project, "dev", "assistant")["parameters"]["stream"] is True


def test_int_to_float_edit_is_a_diff(project):
    set_draft(project, "assistant", {"parameters": {"temperature": 1}})
    revision(project, "int")
    set_draft(project, "assistant", {"parameters": {"temperature": 1.0}})
    assert list(draft_diff(project)) == ["assistant"]


def test_bool_int_drift_detected(project):
    set_draft(project, "assistant", {"parameters": {"stream": 1}})
    revision(project, "stream as int")
    upgrade(project, "dev")
    with closing(sqlite3.connect(pm_dir(project) / "states" / "dev.sqlite3")) as conn, conn:
        conn.execute("UPDATE prompts SET config=? WHERE name='assistant'", ('{"parameters":{"stream":true}}',))
    with pytest.raises(DriftError, match="Environment drift detected for prompts: assistant"):
        check(project, "dev")


def test_hand_edited_bool_int_history_fails_closed(project):
    """The one deliberate tier-A break (spec §5 PR 3): legacy_breaking/ is outside the I14 contract."""
    install_fixture(project, "hand_edited_bool_int", group="legacy_breaking")
    with pytest.raises(MigrationConflictError, match="upgrade bbbbbbbbbbbb: unexpected current value for 'assistant'"):
        load_revisions(project)
