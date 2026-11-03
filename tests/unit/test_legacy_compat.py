"""PR 2: the legacy compatibility contract (spec invariant I14).

Every fixture here is a history the starter accepts today. These tests must keep passing for the whole of cycle 1.
Fixtures that are meant to break belong in tests/fixtures/legacy_breaking/ instead (added in PR 3).

The generated builders (secret_in_history, large_revision, deep_config, symlinked_revision) live in
tests/pmtest.py, so later PRs can import them from the helper module rather than from this test module.
"""
import pytest

from pmtest import GENERATED, install_fixture
from promptmigrate.core import check, downgrade, get_config, load_revisions, upgrade

STATIC = ["case_collision", "noop_null", "noop_equal", "reserved_types"]


@pytest.fixture(params=STATIC + sorted(GENERATED))
def legacy_project(request, project):
    if request.param in GENERATED:
        GENERATED[request.param](project)
    else:
        install_fixture(project, request.param)
    return project


def test_legacy_history_stays_usable(legacy_project):
    total = len(load_revisions(legacy_project))
    assert total >= 1

    upgrade(legacy_project, "dev")
    assert check(legacy_project, "dev", require_head=True) == (total, total)
    assert "messages" in get_config(legacy_project, "dev", "assistant")

    assert len(downgrade(legacy_project, "dev", "base")) == total
    assert check(legacy_project, "dev") == (0, total)
