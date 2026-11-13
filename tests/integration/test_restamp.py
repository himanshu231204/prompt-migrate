"""PR 9 (cycle 2): `restamp` accepts line-ending-only changes to applied v0 revisions (ADR-027, I20).

`restamp` re-stamps a v0 ledger row only when the file on disk differs from the applied bytes in line endings alone.
Any other mismatch, a v1 row, a diverging ledger or drift fails closed with the normal error and writes nothing.
Read commands never re-stamp (I5). There is no audit record of a re-stamp until the cycle-3 events table.
"""
import hashlib
import json
import sqlite3
from contextlib import closing

import pytest

from pmtest import FIXTURES, install_fixture, pm_dir, run_cli, swap_line_endings, tree_snapshot
from promptmigrate import core
from promptmigrate.core import check, load_revisions, revision, upgrade
from promptmigrate.commands.restamp import restamp
from promptmigrate.errors import DriftError, EnvironmentNotDeclaredError, IntegrityError

A, B = "a" * 12, "b" * 12
PINS = json.loads((FIXTURES / "v0_checksums.json").read_text(encoding="utf-8"))


def db_path(project, env="dev"):
    return pm_dir(project) / "states" / f"{env}.sqlite3"


def ledger(project, env="dev"):
    with closing(sqlite3.connect(db_path(project, env))) as db:
        return db.execute("SELECT revision, checksum FROM applied_revisions ORDER BY seq").fetchall()


def db_digest(project, env="dev"):
    return hashlib.sha256(db_path(project, env).read_bytes()).hexdigest()


def target(project, name="aaaaaaaaaaaa_create.json"):
    return pm_dir(project) / "versions" / name


def applied_then_swapped(project, applied="crlf"):
    install_fixture(project, applied, "crlf")
    upgrade(project, "dev")
    swap_line_endings(target(project))


@pytest.mark.parametrize("applied,now", [("crlf", "lf"), ("lf", "crlf")])
def test_restamp_accepts_a_line_ending_only_change(project, applied, now):
    applied_then_swapped(project, applied)
    with pytest.raises(IntegrityError, match=f"^Migration file was modified after apply: {A}"):
        check(project, "dev")
    assert restamp(project, "dev") == [A]
    assert ledger(project) == [(A, PINS[f"crlf/{now}/aaaaaaaaaaaa_create.json"])]
    assert check(project, "dev") == (1, 1)


def test_restamp_re_stamps_every_affected_row_in_order(project):
    install_fixture(project, "basic", "v0_frozen")
    upgrade(project, "dev")
    for path in sorted((pm_dir(project) / "versions").glob("*.json")):
        swap_line_endings(path)
    assert restamp(project, "dev") == [A, B]
    assert ledger(project) == [(r.revision, r.checksum) for r in load_revisions(project)]
    assert check(project, "dev") == (2, 2)


def test_restamp_skips_rows_that_already_match(project):
    install_fixture(project, "basic", "v0_frozen")
    upgrade(project, "dev")
    swap_line_endings(target(project, "bbbbbbbbbbbb_update.json"))
    before = ledger(project)
    assert restamp(project, "dev") == [B]
    assert ledger(project)[0] == before[0]


def test_restamp_on_a_consistent_env_changes_nothing(project):
    install_fixture(project, "crlf", "crlf")
    upgrade(project, "dev")
    before = db_digest(project)
    assert restamp(project, "dev") == []
    assert db_digest(project) == before


def test_restamp_without_state_is_base_and_creates_nothing(project):
    install_fixture(project, "crlf", "crlf")
    before = tree_snapshot(project)
    assert restamp(project, "dev") == []
    assert tree_snapshot(project) == before
    assert not db_path(project).exists()


def test_restamp_of_an_undeclared_env_fails_before_any_state(project):
    install_fixture(project, "crlf", "crlf")
    before = tree_snapshot(project)
    with pytest.raises(EnvironmentNotDeclaredError):
        restamp(project, "qa")
    assert tree_snapshot(project) == before


def test_value_edit_with_line_ending_change_is_refused(project):
    install_fixture(project, "crlf", "crlf")
    upgrade(project, "dev")
    lf = (FIXTURES / "crlf/lf/aaaaaaaaaaaa_create.json").read_bytes()
    target(project).write_bytes(lf.replace(b"Answer briefly.", b"Answer at length."))
    before = db_digest(project)
    with pytest.raises(IntegrityError) as caught:
        restamp(project, "dev")
    assert str(caught.value) == f"Migration file was modified after apply: {A}"
    assert db_digest(project) == before


def test_one_refused_row_writes_no_row(project):
    """I20: re-stamping is all or nothing. A line-ending-only row is not re-stamped when a later row is edited."""
    install_fixture(project, "basic", "v0_frozen")
    upgrade(project, "dev")
    swap_line_endings(target(project))
    update = target(project, "bbbbbbbbbbbb_update.json")
    update.write_bytes(update.read_bytes().replace(b"cite sources.", b"cite nothing."))
    before = db_digest(project)
    with pytest.raises(IntegrityError) as caught:
        restamp(project, "dev")
    assert str(caught.value) == f"Migration file was modified after apply: {B}"
    assert db_digest(project) == before


def test_v1_mismatch_is_never_restamped(project):
    created = revision(project, "initial")
    upgrade(project, "dev")
    item = json.loads(created.path.read_bytes())
    created.path.write_text(json.dumps({**item, "message": "edited after apply"}), encoding="utf-8")
    before = db_digest(project)
    with pytest.raises(IntegrityError) as caught:
        restamp(project, "dev")
    assert str(caught.value) == f"Migration file was modified after apply: {created.revision}"
    assert db_digest(project) == before


def test_v1_row_holding_a_line_ending_digest_is_never_restamped(project):
    """A v1 file whose ledger row holds a raw-byte digest of a line-ending variant (a pre-v1 tool) is not accepted."""
    created = revision(project, "initial")
    upgrade(project, "dev")
    with closing(sqlite3.connect(db_path(project))) as db, db:
        db.execute("UPDATE applied_revisions SET checksum=?",
                   (hashlib.sha256(created.path.read_bytes().replace(b"\n", b"\r\n")).hexdigest(),))
    before = db_digest(project)
    with pytest.raises(IntegrityError, match=f"^Migration file was modified after apply: {created.revision}$"):
        restamp(project, "dev")
    assert db_digest(project) == before


@pytest.mark.parametrize("sql,message", [
    ("INSERT INTO applied_revisions(revision, checksum, applied_at) VALUES('cccccccccccc', 'x', 't')",
     "Environment contains more applied revisions than source history"),
    ("UPDATE applied_revisions SET revision='cccccccccccc'", "Applied revisions diverge from source history at index 0"),
])
def test_a_diverging_ledger_is_refused(project, sql, message):
    applied_then_swapped(project)
    with closing(sqlite3.connect(db_path(project))) as db, db:
        db.execute(sql)
    before = db_digest(project)
    with pytest.raises(IntegrityError, match=f"^{message}$"):
        restamp(project, "dev")
    assert db_digest(project) == before


def test_drift_after_restamp_rolls_back(project):
    applied_then_swapped(project)
    with closing(sqlite3.connect(db_path(project))) as db, db:
        db.execute("UPDATE prompts SET config='{}' WHERE name='assistant'")
    before = db_digest(project)
    with pytest.raises(DriftError, match="^Environment drift detected for prompts: assistant$"):
        restamp(project, "dev")
    assert db_digest(project) == before


def test_restamp_does_not_adopt_the_manifest(project):
    """I20: restamp changes ledger checksums only. A legacy project without environments.json keeps it absent."""
    applied_then_swapped(project)
    (pm_dir(project) / "environments.json").unlink()
    assert restamp(project, "dev") == [A]
    assert not (pm_dir(project) / "environments.json").exists()


def test_cli_text_output(project, capsys):
    applied_then_swapped(project)
    assert run_cli(capsys, project, "restamp", "--env", "dev") == (0, f"Restamped 1 revision(s) in dev: {A}\n", "")
    assert run_cli(capsys, project, "restamp", "--env", "dev") == (0, "Restamped 0 revision(s) in dev: (none)\n", "")


def test_cli_json_output(project, capsys):
    applied_then_swapped(project)
    code, out, err = run_cli(capsys, project, "--output", "json", "restamp", "--env", "dev")
    assert (code, err) == (0, "")
    assert json.loads(out) == {"schema": "promptmigrate.output/1", "ok": True, "command": "restamp", "env": "dev",
                               "data": {"restamped": [A]}, "warnings": []}


@pytest.mark.parametrize("prepare,code", [
    (lambda p: None, 0),
    (lambda p: target(p).write_bytes(target(p).read_bytes().replace(b"Answer briefly.", b"Answer at length.")), 4),
])
def test_cli_exit_codes(project, capsys, prepare, code):
    applied_then_swapped(project)
    prepare(project)
    assert run_cli(capsys, project, "restamp", "--env", "dev")[0] == code


def test_cli_undeclared_env_exits_1(project, capsys):
    code, out, err = run_cli(capsys, project, "restamp", "--env", "qa")
    assert (code, out) == (1, "")
    assert "Environment 'qa' is not declared" in err


def test_restamp_defaults_to_dev(project, capsys):
    applied_then_swapped(project)
    assert run_cli(capsys, project, "restamp")[:2] == (0, f"Restamped 1 revision(s) in dev: {A}\n")


def test_core_facade_exports_restamp():
    assert core.restamp is restamp
