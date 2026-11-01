"""PR4: reads preserve file bytes and mtimes and use SQLite mode=ro."""
from contextlib import closing
import sqlite3

import pytest

from pmtest import CFG, create, fake_key, pm_dir, tree_snapshot, write_revision
from promptmigrate import core, errors
from test_environments import error_type, manifest, run_cli, store_api


def snapshot(project):
    return tree_snapshot(project), {
        p.relative_to(project).as_posix(): p.stat().st_mtime_ns
        for p in project.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize("command", ["check", "current", "get"])
@pytest.mark.parametrize("legacy", [False, True])
def test_missing_database_is_base_without_files(project, capsys, command, legacy):
    manifest(project, {"dev": {}, "staging": {}})
    core.revision(project, "initial")
    if legacy:
        (pm_dir(project) / "environments.json").unlink()
    before = snapshot(project)
    argv = [command, *(["assistant"] if command == "get" else []), "--env", "dev"]
    result = run_cli(capsys, project, *argv)
    expected = {
        "check": (0, "OK: dev is consistent (0/1 revisions applied)\n", ""),
        "current": (0, "dev: base (0/1 applied)\n", ""),
        "get": (1, "", "Error: No prompt named 'assistant' in environment 'dev'\n"),
    }
    assert result == expected[command]
    assert snapshot(project) == before


def test_missing_database_require_head_does_not_write(project):
    core.revision(project, "initial")
    before = snapshot(project)
    with pytest.raises(errors.PendingRevisionsError):
        core.check(project, "dev", require_head=True)
    assert snapshot(project) == before


@pytest.mark.parametrize("command", ["check", "current", "get", "env-list"])
@pytest.mark.parametrize("legacy", [False, True])
def test_existing_history_secret_audit_preserves_bytes_and_mtimes(project, capsys, command, legacy):
    manifest(project, {"dev": {}, "staging": {}})
    write_revision(project, "a" * 12, None, {"assistant": create({**CFG, "note": fake_key()})})
    core.upgrade(project, "dev")
    if legacy:
        (pm_dir(project) / "environments.json").unlink()
    before = snapshot(project)
    argv = ["env", "list"] if command == "env-list" else [
        command, *(["assistant"] if command == "get" else []), "--env", "dev"]
    code, out, err = run_cli(capsys, project, *argv)
    assert code == 0
    assert fake_key() not in out + err
    if command == "check":
        assert "Warning: revision " + "a" * 12 + ": assistant /note openai-anthropic-key\n" in err
    assert snapshot(project) == before


@pytest.mark.parametrize("name", ["prdo", "../escape"])
def test_invalid_environment_check_preserves_bytes_and_mtimes(project, capsys, name):
    manifest(project, {"dev": {}})
    before = snapshot(project)
    code, out, err = run_cli(capsys, project, "check", "--env", name)
    assert (code, out) == (1, "") and err.startswith("Error: ")
    assert snapshot(project) == before


@pytest.mark.parametrize("table", ["prompts", "applied_revisions"])
@pytest.mark.parametrize("command", ["check", "current", "get"])
def test_missing_required_table_is_storage_error_without_repair(project, capsys, table, command):
    manifest(project, {"dev": {}})
    core.upgrade(project, "dev")
    path = pm_dir(project) / "states" / "dev.sqlite3"
    with closing(sqlite3.connect(path)) as db, db:
        db.execute(f"DROP TABLE {table}")
    before = snapshot(project)
    # Assert core's typed error separately from the CLI's handled-error contract.
    expected = error_type("StorageError")
    with pytest.raises(expected):
        if command == "get":
            core.get_config(project, "dev", "assistant")
        else:
            core.check(project, "dev")
    assert snapshot(project) == before
    argv = [command, *(["assistant"] if command == "get" else [])]
    code, out, err = run_cli(capsys, project, *argv)
    assert code == 1 and out == "" and err.startswith("Error: ")
    assert snapshot(project) == before


@pytest.mark.parametrize("corruption", ["applied_columns", "invalid_json", "null_config"])
@pytest.mark.parametrize("command", ["check", "current", "get"])
def test_corrupt_state_reads_are_storage_errors_without_repair(project, capsys, corruption, command):
    manifest(project, {"dev": {}})
    core.revision(project, "initial")
    core.upgrade(project, "dev")
    path = pm_dir(project) / "states" / "dev.sqlite3"
    with closing(sqlite3.connect(path)) as db, db:
        if corruption == "applied_columns":
            db.execute("ALTER TABLE applied_revisions RENAME TO old_applied_revisions")
            db.execute("CREATE TABLE applied_revisions (invalid_column TEXT)")
            db.execute("DROP TABLE old_applied_revisions")
        elif corruption == "invalid_json":
            db.execute("UPDATE prompts SET config='not-json' WHERE name='assistant'")
        else:
            db.execute("DROP TABLE prompts")
            db.execute("CREATE TABLE prompts (name TEXT PRIMARY KEY, config TEXT)")
            db.execute("INSERT INTO prompts VALUES ('assistant', NULL)")
    before = snapshot(project)
    with pytest.raises(errors.StorageError):
        if command == "get":
            core.get_config(project, "dev", "assistant")
        else:
            core.check(project, "dev")
    assert snapshot(project) == before
    argv = [command]
    if command == "get":
        argv.append("assistant")
    argv.extend(["--env", "dev"])
    code, out, err = run_cli(capsys, project, *argv)
    assert code == 1 and out == "" and err.startswith("Error: ")
    assert snapshot(project) == before


@pytest.mark.parametrize("command", ["check", "current", "get"])
def test_reads_open_escaped_sqlite_uri_mode_ro(tmp_path, monkeypatch, capsys, command):
    project = tmp_path / "space and # fragment"
    project.mkdir()
    core.init(project)
    core.revision(project, "initial")
    core.upgrade(project, "dev")
    before = snapshot(project)
    calls = []
    real_connect = sqlite3.connect

    def connect(database, *args, **kwargs):
        calls.append((str(database), kwargs.copy()))
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect)
    code, _, err = run_cli(capsys, project, command, *(["assistant"] if command == "get" else []))
    assert (code, err) == (0, "")
    assert calls, "existing state must be read through SQLite"
    for uri, kwargs in calls:
        assert uri.startswith("file:") and "mode=ro" in uri
        assert "%20" in uri and "%23" in uri and kwargs.get("uri") is True
    assert snapshot(project) == before


def test_store_readonly_missing_database_does_not_create_parent(project):
    manifest(project, {"dev": {}})
    (pm_dir(project) / "states").rmdir()
    before = snapshot(project)
    with store_api().connect_readonly(project, "dev") as db:
        assert db is None
    assert snapshot(project) == before
    assert not (pm_dir(project) / "states").exists()


def test_store_readonly_connection_rejects_writes_and_closes(project):
    manifest(project, {"dev": {}})
    core.upgrade(project, "dev")
    before = snapshot(project)
    with store_api().connect_readonly(project, "dev") as db:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            db.execute("CREATE TABLE forbidden (x)")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        db.execute("SELECT 1")
    assert snapshot(project) == before


def test_store_write_connection_initializes_schema_and_closes(project):
    manifest(project, {"dev": {}})
    with store_api().connect_write(project, "dev") as db:
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"applied_revisions", "prompts"} <= names
        assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 10000
        assert db.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        db.execute("SELECT 1")
