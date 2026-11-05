"""`plan`: read-only preview of upgrade/downgrade. Never writes; same errors as the commands it previews."""
import pytest

from pmtest import CFG, create, manifest, pm_dir, run_cli, snapshot, write_revision
from promptmigrate import core, errors

CFG2 = {"messages": [{"role": "system", "content": "B"}]}
A, B = "a" * 12, "b" * 12


@pytest.fixture
def two(project):
    write_revision(project, A, None, {"assistant": create()})
    write_revision(project, B, A, {"assistant": {"before": CFG, "after": CFG2}, "extra": create()})
    return project


def test_plan_from_base_previews_upgrade(two, capsys):
    code, out, err = run_cli(capsys, two, "plan", "--env", "dev")
    assert (code, err) == (0, "")
    assert out == (
        f"dev: would apply 2 revision(s) (base -> {B})\n"
        f"  {A}\n    assistant (create)\n"
        f"  {B}\n    assistant (update)\n    extra (create)\n"
    )


def test_plan_target_revision(two, capsys):
    code, out, _ = run_cli(capsys, two, "plan", "--env", "dev", "--target", A)
    assert code == 0 and out == f"dev: would apply 1 revision(s) (base -> {A})\n  {A}\n    assistant (create)\n"


def test_plan_defaults_to_head_and_dev(two, capsys):
    assert run_cli(capsys, two, "plan")[1].startswith("dev: would apply 2 revision(s)")


def test_plan_previews_downgrade(two, capsys):
    core.upgrade(two, "dev")
    code, out, _ = run_cli(capsys, two, "plan", "--env", "dev", "--target", "-1")
    assert code == 0
    assert out == f"dev: would revert 1 revision(s) ({B} -> {A})\n  {B}\n    assistant (update)\n    extra (delete)\n"


def test_plan_downgrade_to_base_label(two, capsys):
    core.upgrade(two, "dev")
    out = run_cli(capsys, two, "plan", "--env", "dev", "--target", "base")[1]
    assert out.splitlines()[0] == f"dev: would revert 2 revision(s) ({B} -> base)"


def test_plan_nothing_to_do_at_head(two, capsys):
    core.upgrade(two, "dev")
    assert run_cli(capsys, two, "plan", "--env", "dev") == (0, f"dev: nothing to do (at {B})\n", "")


def test_plan_nothing_to_do_at_base(two, capsys):
    assert run_cli(capsys, two, "plan", "--env", "dev", "--target", "base") == (0, "dev: nothing to do (at base)\n", "")


def test_plan_with_no_revisions(project, capsys):
    assert run_cli(capsys, project, "plan") == (0, "dev: nothing to do (at base)\n", "")


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("target", ["head", "base", "-1", A])
def test_plan_never_writes(two, capsys, legacy, target):
    manifest(two, {"dev": {}, "staging": {}})
    if legacy:
        (pm_dir(two) / "environments.json").unlink()
    before = snapshot(two)
    run_cli(capsys, two, "plan", "--env", "dev", "--target", target)
    assert snapshot(two) == before


def test_plan_never_writes_with_existing_state(two, capsys):
    core.upgrade(two, "dev")
    before = snapshot(two)
    run_cli(capsys, two, "plan", "--env", "dev", "--target", "base")
    assert snapshot(two) == before


def test_plan_unknown_target(two, capsys):
    assert run_cli(capsys, two, "plan", "--target", "zzz") == (1, "", "Error: Unknown target revision: zzz\n")


def test_plan_undeclared_environment(two, capsys):
    manifest(two, {"dev": {}})
    code, out, err = run_cli(capsys, two, "plan", "--env", "qa")
    assert (code, out) == (1, "") and "not declared" in err


def test_plan_detects_drift(two, capsys):
    core.upgrade(two, "dev")
    from contextlib import closing
    import sqlite3
    with closing(sqlite3.connect(pm_dir(two) / "states" / "dev.sqlite3")) as db:
        db.execute("UPDATE prompts SET config='{\"messages\":[]}' WHERE name='extra'")
        db.commit()
    code, out, err = run_cli(capsys, two, "plan", "--env", "dev")
    assert (code, out) == (4, "") and err.startswith("Error: Environment drift detected")


def test_plan_rejects_unknown_target_before_drift_like_upgrade(two, capsys):
    core.upgrade(two, "dev")
    from contextlib import closing
    import sqlite3
    with closing(sqlite3.connect(pm_dir(two) / "states" / "dev.sqlite3")) as db:
        db.execute("UPDATE prompts SET config='{\"messages\":[]}' WHERE name='extra'")
        db.commit()
    expected = (1, "", "Error: Unknown target revision: zzz\n")
    assert run_cli(capsys, two, "upgrade", "zzz", "--env", "dev") == expected
    assert run_cli(capsys, two, "plan", "--target", "zzz", "--env", "dev") == expected


def test_plan_detects_edited_applied_revision(two, capsys):
    core.upgrade(two, "dev", A)
    path = pm_dir(two) / "versions" / f"{A}.json"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    code, _, err = run_cli(capsys, two, "plan", "--env", "dev")
    assert code == 4 and "Migration file was modified after apply" in err


def test_plan_not_initialized(tmp_path, capsys):
    code, out, err = run_cli(capsys, tmp_path, "plan")
    assert (code, out) == (1, "") and err.startswith("Error:")


def test_core_facade_exports_plan(two):
    assert core.plan(two, "dev").direction == "upgrade"
    assert errors.TargetError
