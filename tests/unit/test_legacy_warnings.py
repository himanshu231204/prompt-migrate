"""PR 3: existing revision files that break tier-B rules still load, with one LegacyRevisionWarning per violation."""
import warnings

import pytest

from pmtest import (
    CFG, GENERATED, LEGACY_NAMES, LEGACY_SUFFIX, LEGACY_WARNINGS, create, install_fixture, install_legacy,
    nested_config, pm_warnings, set_draft, sized_draft, write_revision,
)
from promptmigrate import protocol
from promptmigrate.core import check, load_revisions, revision, upgrade
from promptmigrate.errors import LegacyRevisionWarning, PromptMigrateWarning, RevisionGraphError


def legacy(name):
    return [m + LEGACY_SUFFIX for m in LEGACY_WARNINGS[name]]


@pytest.mark.parametrize("name", LEGACY_NAMES)
def test_each_violation_warns_exactly_once(project, monkeypatch, name):
    install_legacy(project, monkeypatch, name)
    assert pm_warnings(load_revisions, project)[1] == legacy(name)


def test_warning_category(project):
    install_fixture(project, "noop_null")
    with pytest.warns(LegacyRevisionWarning, match="no-op-change ghost"):
        load_revisions(project)


def test_large_revision_under_real_limit_does_not_warn(project):
    """Guard: the 16 MiB limit is far above the large_revision fixture."""
    GENERATED["large_revision"](project)
    assert pm_warnings(load_revisions, project)[1] == []


def test_tier_a_error_raised_before_any_legacy_warning(project):
    """Guard (I9): a broken history raises without first emitting warnings about its other revisions."""
    install_fixture(project, "noop_null")
    write_revision(project, "b" * 12, "c" * 12, {"other": create()})
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(RevisionGraphError, match="Missing parent"):
            load_revisions(project)
    assert [w for w in caught if issubclass(w.category, PromptMigrateWarning)] == []


# --- I15: revisions generated at the limits load without warnings -------------------------------

def test_largest_draft_round_trips_without_warning(project):
    sized_draft(project, protocol.MAX_DRAFT_BYTES)
    assert pm_warnings(revision, project, "largest draft")[1] == []
    assert pm_warnings(load_revisions, project)[1] == []


def test_deepest_draft_round_trips_without_warning(project):
    set_draft(project, "assistant", nested_config(protocol.MAX_CONFIG_DEPTH))
    assert pm_warnings(revision, project, "deepest draft")[1] == []
    assert pm_warnings(load_revisions, project)[1] == []


# --- remediation: a new revision fixes a legacy violation ---------------------------------------

def test_reserved_types_remediation(project):
    install_fixture(project, "reserved_types")
    set_draft(project, "assistant", {**CFG, "model": "x", "tools": []})
    new, got = pm_warnings(revision, project, "fix reserved types")
    carried = [m for m in got if m.startswith(f"revision {new.revision}:")]
    assert carried == [f"revision {new.revision}: assistant before carries reserved-field-type assistant.model, "
                       "reserved-field-type assistant.tools from history (copied for compatibility)"]
    assert set(got) - set(carried) == set(legacy("reserved_types"))
    assert pm_warnings(load_revisions, project)[1] == legacy("reserved_types")
    assert protocol.config_violations("assistant", new.changes["assistant"]["after"]) == []


def test_case_collision_remediation(project):
    install_fixture(project, "case_collision")
    # init's assistant draft differs from the fixture, and Assistant has no draft, so it is deleted.
    new, _ = pm_warnings(revision, project, "drop Assistant")
    assert sorted(new.changes) == ["Assistant", "assistant"]
    assert new.changes["Assistant"]["after"] is None
    assert pm_warnings(load_revisions, project)[1] == legacy("case_collision")
    upgrade(project, "dev")
    assert check(project, "dev", require_head=True) == (2, 2)
