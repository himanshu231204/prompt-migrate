"""PR 2: the legacy compatibility contract (spec invariant I14).

Every fixture here is a history the starter accepts today. These tests must keep passing for the whole of cycle 1.
Fixtures that are meant to break belong in tests/fixtures/legacy_breaking/ instead (added in PR 3).
"""
import pytest

from pmtest import CFG, create, install_fixture, pm_dir, write_revision
from promptmigrate.core import check, downgrade, get_config, load_revisions, upgrade

A = "a" * 12
LARGE_CONTENT_BYTES = 65536
STATIC = ["case_collision", "noop_null", "noop_equal", "reserved_types"]


def secret_in_history(project):
    token = "sk-" + "0" * 24  # built at runtime: never commit a token-shaped literal
    write_revision(project, A, None, {"assistant": create({**CFG, "api_key": token})})


def large_revision(project):
    big = {"messages": [{"role": "system", "content": "x" * LARGE_CONTENT_BYTES}]}
    write_revision(project, A, None, {"assistant": create(big)})


def deep_config(project):
    nested = {"leaf": 1}
    for _ in range(69):  # 70 nested objects below the config root
        nested = {"n": nested}
    write_revision(project, A, None, {"assistant": create({**CFG, "deep": nested})})


def symlinked_revision(project):
    shared = pm_dir(project) / "shared"
    shared.mkdir()
    link = write_revision(project, A, None, {"assistant": create()})
    target = shared / link.name
    link.replace(target)
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("creating symlinks is not permitted for this user/platform")


GENERATED = {
    "secret_in_history": secret_in_history,
    "large_revision": large_revision,
    "deep_config": deep_config,
    "symlinked_revision": symlinked_revision,
}


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
