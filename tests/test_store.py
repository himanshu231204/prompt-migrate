"""Direct PR4 store contracts, independent of core/CLI integration."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import warnings

import pytest

from pmtest import nested_config, pm_dir, symlink_or_skip
from promptmigrate import errors, protocol
from test_environments import manifest, store_api, SYNTAX_MESSAGE
from test_read_only_env import snapshot


@pytest.mark.parametrize("value", [
    {}, [], None, {"environments": {}, "extra": 1},
    {"environments": []}, {"environments": None},
    {"environments": {"dev": []}}, {"environments": {"dev": None}},
    {"environments": {"dev": {}, "DEV": {}}},
    {"environments": {"../escape": {}}},
    {"environments": {"dev": nested_config(65)}},
])
def test_store_manifest_schema(project, value):
    api = store_api()
    path = pm_dir(project) / "environments.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    before = snapshot(project)
    with pytest.raises(errors.SchemaError):
        api.read_environments(project)
    assert snapshot(project) == before


@pytest.mark.parametrize("raw", [
    b"{", b'\xef\xbb\xbf{}', b'\xff',
    b'{"environments": {}, "environments": {}}',
    b'{"environments": {"dev": {"x": NaN}}}',
])
def test_store_strict_manifest(project, raw):
    api = store_api()
    (pm_dir(project) / "environments.json").write_bytes(raw)
    with pytest.raises(errors.SchemaError, match="Invalid environments file"):
        api.read_environments(project)


def test_store_manifest_size_boundary(project):
    api = store_api()
    path = manifest(project, {"dev": {}})
    raw = path.read_bytes()
    path.write_bytes(raw + b" " * (protocol.MAX_CONTROL_FILE_BYTES - len(raw)))
    assert api.read_environments(project) == ({"dev": {}}, True)
    with path.open("ab") as file:
        file.write(b" ")
    with pytest.raises(errors.SchemaError, match="limit"):
        api.read_environments(project)


def test_store_add_cannot_write_an_oversized_manifest(project):
    api = store_api()
    path = manifest(project, {"dev": {"note": ""}})
    overhead = path.stat().st_size
    manifest(project, {"dev": {"note": "x" * (protocol.MAX_CONTROL_FILE_BYTES - overhead)}})
    before = snapshot(project)
    with pytest.raises(errors.SchemaError, match="limit"):
        api.add_environment(project, "qa")
    assert snapshot(project) == before


def test_store_metadata_retained_at_depth_limit(project):
    api = store_api()
    metadata = nested_config(64)
    manifest(project, {"dev": metadata})
    assert api.read_environments(project) == ({"dev": metadata}, True)
    api.add_environment(project, "Qa")
    assert api.read_environments(project) == ({"dev": metadata, "Qa": {}}, True)


def test_store_manifest_symlink(project):
    api = store_api()
    target = pm_dir(project) / "shared.json"
    target.write_text('{"environments": {"dev": {}}}', encoding="utf-8")
    symlink_or_skip(pm_dir(project) / "environments.json", target)
    with pytest.raises(errors.SchemaError):
        api.read_environments(project)


@pytest.mark.parametrize("stems,expected", [
    ([], {"dev": {}, "staging": {}}),
    (["Zulu", "alpha", "Qa"], {"alpha": {}, "Qa": {}, "Zulu": {}}),
])
def test_store_legacy_discovery_is_in_memory(project, stems, expected):
    api = store_api()
    (pm_dir(project) / "environments.json").unlink(missing_ok=True)
    for stem in stems:
        (pm_dir(project) / "states" / f"{stem}.sqlite3").touch()
    before = snapshot(project)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        data, existed = api.read_environments(project)
    assert (data, existed) == (expected, False)
    assert list(data) == list(expected)
    assert caught == [] and snapshot(project) == before


def test_store_invalid_legacy_stem_is_rejected(project):
    api = store_api()
    (pm_dir(project) / "environments.json").unlink()
    (pm_dir(project) / "states" / "1bad.sqlite3").touch()
    with pytest.raises(errors.SchemaError):
        api.read_environments(project)


def test_store_colliding_legacy_stems_are_rejected(project):
    api = store_api()
    (pm_dir(project) / "environments.json").unlink()
    states = pm_dir(project) / "states"
    (states / "Qa.sqlite3").touch()
    (states / "qa.sqlite3").touch()
    if len(list(states.glob("*.sqlite3"))) != 2:
        pytest.skip("case-insensitive filesystem: legacy stems cannot coexist")
    with pytest.raises(errors.SchemaError):
        api.read_environments(project)


@pytest.mark.parametrize("name", ["", "../escape", "1qa", "a.b", "a/b", "a\\b", "a b", "équipe", "a" * 65])
@pytest.mark.parametrize("operation", ["resolve_environment", "add_environment"])
def test_store_syntax_precedes_manifest_parsing(project, name, operation):
    api = store_api()
    (pm_dir(project) / "environments.json").write_text("{", encoding="utf-8")
    before = snapshot(project)
    with pytest.raises(errors.SchemaError) as exc:
        getattr(api, operation)(project, name)
    assert str(exc.value) == SYNTAX_MESSAGE
    assert snapshot(project) == before


@pytest.mark.parametrize("name", ["CON", "prn", "AUX", "nul", "COM1", "lpt9"])
@pytest.mark.parametrize("operation", ["resolve_environment", "add_environment"])
def test_store_rejects_windows_reserved_environment_names(project, name, operation):
    api = store_api()
    manifest(project, {"dev": {}})
    before = snapshot(project)
    with pytest.raises(errors.SchemaError):
        if operation == "resolve_environment":
            api.resolve_environment(project, name)
        else:
            api.add_environment(project, name)
    assert snapshot(project) == before


def test_store_canonical_resolution_and_undeclared_no_adoption(project):
    api = store_api()
    manifest(project, {"Qa": {}})
    before = snapshot(project)
    assert api.resolve_environment(project, "qA") == "Qa"
    assert snapshot(project) == before
    (pm_dir(project) / "environments.json").unlink()
    before = snapshot(project)
    with pytest.raises(errors.EnvironmentNotDeclaredError) as exc:
        api.resolve_environment(project, "prdo", mutating=True)
    assert exc.value.env == "prdo" and snapshot(project) == before


def test_store_rejected_mutations_create_no_files(project):
    api = store_api()
    manifest(project, {"dev": {}})
    before = snapshot(project)
    with pytest.raises(errors.EnvironmentNotDeclaredError):
        api.resolve_environment(project, "prdo", mutating=True)
    assert snapshot(project) == before
    with pytest.raises(errors.SchemaError):
        api.add_environment(project, "DEV")
    assert snapshot(project) == before
    assert not (pm_dir(project) / "states" / ".environments.lock").exists()


@pytest.mark.parametrize("name", ["a", "Qa_2-local", "a" * 64])
def test_store_add_valid_name(project, name):
    api = store_api()
    path = manifest(project, {"dev": {"owner": "team"}})
    assert api.add_environment(project, name) == path
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "environments": {"dev": {"owner": "team"}, name: {}}}


@pytest.mark.parametrize("name", ["dev", "DEV", "Dev"])
def test_store_add_duplicate_does_not_write(project, name):
    api = store_api()
    manifest(project, {"dev": {}})
    before = snapshot(project)
    with pytest.raises(errors.SchemaError):
        api.add_environment(project, name)
    assert snapshot(project) == before


@pytest.mark.parametrize("fail", [False, True])
def test_store_add_atomic_replace_and_temp_cleanup(project, monkeypatch, fail):
    api = store_api()
    path = manifest(project, {"dev": {"owner": "team"}})
    before = snapshot(project)
    sources = []
    real_replace = os.replace

    def replace(source, destination):
        source = Path(source)
        assert source.parent == path.parent and source != path
        assert Path(destination) == path
        assert snapshot(project)[0][".promptmigrate/environments.json"] == before[0][".promptmigrate/environments.json"]
        assert json.loads(source.read_text(encoding="utf-8")) == {
            "environments": {"dev": {"owner": "team"}, "qa": {}}}
        sources.append(source)
        if fail:
            raise OSError("injected replace failure")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", replace)
    if fail:
        with pytest.raises((OSError, errors.MigrationError)):
            api.add_environment(project, "qa")
        assert snapshot(project) == before
    else:
        api.add_environment(project, "qa")
        assert api.read_environments(project) == ({"dev": {"owner": "team"}, "qa": {}}, True)
        assert set(snapshot(project)[0]) == set(before[0])
    assert len(sources) == 1 and not sources[0].exists()


def test_store_concurrent_additions_preserve_both_declarations(project, monkeypatch):
    api = store_api()
    manifest(project, {"dev": {}})
    original_read = api.read_environments
    original_write = api._write_environments
    first_read = threading.Event()
    second_read = threading.Event()
    count = 0
    guard = threading.Lock()

    def read(*args, **kwargs):
        nonlocal count
        result = original_read(*args, **kwargs)
        with guard:
            count += 1
            current = count
        if current == 1:
            first_read.set()
            second_read.wait(0.2)
        elif current == 2:
            second_read.set()
        return result

    def write(*args, **kwargs):
        first_read.wait(1)
        return original_write(*args, **kwargs)

    monkeypatch.setattr(api, "read_environments", read)
    monkeypatch.setattr(api, "_write_environments", write)
    failures = []

    def add(name):
        try:
            api.add_environment(project, name)
        except BaseException as exc:
            failures.append(exc)

    threads = [threading.Thread(target=add, args=(name,)) for name in ("qa", "qb")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(3)
    assert not any(thread.is_alive() for thread in threads)
    assert failures == []
    assert api.read_environments(project) == ({"dev": {}, "qa": {}, "qb": {}}, True)


def test_store_list_state_flags_without_writes(project):
    api = store_api()
    manifest(project, {"staging": {}, "Qa": {}, "dev": {}})
    (pm_dir(project) / "states" / "dev.sqlite3").touch()
    before = snapshot(project)
    assert api.list_environments(project) == [("dev", True), ("Qa", False), ("staging", False)]
    assert snapshot(project) == before


@pytest.mark.parametrize("operation", ["resolve", "add"])
@pytest.mark.parametrize("legacy_state", [False, True])
def test_store_adoption_warning_only_first_successful_mutation(project, operation, legacy_state):
    api = store_api()
    (pm_dir(project) / "environments.json").unlink()
    if legacy_state:
        (pm_dir(project) / "states" / "dev.sqlite3").touch()
    before = snapshot(project)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        api.resolve_environment(project, "dev")
        api.list_environments(project)
        assert snapshot(project) == before and caught == []
        if operation == "resolve":
            api.resolve_environment(project, "DEV", mutating=True)
            api.resolve_environment(project, "dev", mutating=True)
        else:
            api.add_environment(project, "qa")
            api.add_environment(project, "qb")
    expected = {"dev": {}} if legacy_state else {"dev": {}, "staging": {}}
    if operation == "add":
        expected.update({"qa": {}, "qb": {}})
    assert api.read_environments(project) == (expected, True)
    assert [w.category for w in caught] == [errors.EnvironmentAdoptionWarning]


def test_store_failed_adoption_does_not_warn_or_leave_temp(project, monkeypatch):
    api = store_api()
    (pm_dir(project) / "environments.json").unlink()
    before = snapshot(project)

    def fail(*args):
        raise OSError("injected replacement failure")

    monkeypatch.setattr(os, "replace", fail)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises((OSError, errors.MigrationError)):
            api.resolve_environment(project, "dev", mutating=True)
    assert caught == [] and snapshot(project) == before


@pytest.mark.parametrize("name", ["prod", "PRODUCTION", "Live", "dev", "production-test", "lively"])
def test_store_production_warning_exact_names(project, name):
    api = store_api()
    manifest(project, {name: {}})
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert api.resolve_environment(project, name.swapcase()) == name
    expected = [f"'{name}' is local SQLite state only; PromptMigrate does not deploy anything."] if name.lower() in {
        "prod", "production", "live"} else []
    assert [str(w.message) for w in caught] == expected
    assert all(w.category is errors.ProductionNameWarning for w in caught)


def test_store_readonly_uri_escaping_and_close_on_body_failure(project, monkeypatch):
    api = store_api()
    special = project / "space and # fragment"
    # Only storage directories are needed by the connection layer.
    (pm_dir(special) / "versions").mkdir(parents=True)
    (pm_dir(special) / "drafts").mkdir()
    with api.connect_write(special, "Qa") as db:
        db.execute("INSERT INTO prompts VALUES ('assistant', '{}')")
    before = snapshot(special)
    real_connect = sqlite3.connect
    calls = []

    def connect(database, *args, **kwargs):
        calls.append((str(database), kwargs))
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect)
    with pytest.raises(RuntimeError, match="body failure"):
        with api.connect_readonly(special, "Qa") as db:
            assert db.execute("SELECT config FROM prompts").fetchall() == [("{}",)]
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                db.execute("DELETE FROM prompts")
            raise RuntimeError("body failure")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        db.execute("SELECT 1")
    assert len(calls) == 1
    uri, kwargs = calls[0]
    assert uri.startswith("file:") and "mode=ro" in uri and "%20" in uri and "%23" in uri
    assert kwargs["uri"] is True
    assert snapshot(special) == before


@pytest.mark.parametrize("missing", ["prompts", "applied_revisions", "both", "corrupt"])
def test_store_readonly_rejects_unusable_db_without_repair_and_closes(project, monkeypatch, missing):
    api = store_api()
    path = pm_dir(project) / "states" / "dev.sqlite3"
    if missing == "corrupt":
        path.write_bytes(b"not a SQLite database")
    else:
        with api.connect_write(project, "dev") as db:
            for table in (["prompts", "applied_revisions"] if missing == "both" else [missing]):
                db.execute(f"DROP TABLE {table}")
    before = snapshot(project)
    real_connect = sqlite3.connect
    opened = []

    def connect(*args, **kwargs):
        db = real_connect(*args, **kwargs)
        opened.append(db)
        return db

    monkeypatch.setattr(sqlite3, "connect", connect)
    with pytest.raises(errors.StorageError):
        with api.connect_readonly(project, "dev"):
            pytest.fail("must not yield an unusable database")
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")
    assert snapshot(project) == before
    path.unlink()  # Windows detects leaked handles here too.


def test_store_readonly_rejects_dangling_database_symlink(project):
    api = store_api()
    path = pm_dir(project) / "states" / "dev.sqlite3"
    symlink_or_skip(path, pm_dir(project) / "states" / "missing-target.sqlite3")
    with pytest.raises(errors.StorageError):
        with api.connect_readonly(project, "dev"):
            pytest.fail("dangling state link must not be reported as base state")


def test_store_rejects_symlinked_states_directory(project, tmp_path):
    api = store_api()
    outside = tmp_path / "outside-states"
    outside.mkdir()
    with closing(sqlite3.connect(outside / "dev.sqlite3")) as db:
        db.execute("CREATE TABLE prompts (name TEXT PRIMARY KEY, config TEXT NOT NULL)")
        db.execute("CREATE TABLE applied_revisions (seq INTEGER PRIMARY KEY, revision TEXT, checksum TEXT, applied_at TEXT)")
    states = pm_dir(project) / "states"
    states.rmdir()
    symlink_or_skip(states, outside)
    with pytest.raises(errors.StorageError):
        with api.connect_readonly(project, "dev"):
            pytest.fail("state directory link must not redirect outside the project")


def test_store_write_rejects_incomplete_existing_db_without_repair(project):
    api = store_api()
    path = pm_dir(project) / "states" / "dev.sqlite3"
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE prompts (name TEXT PRIMARY KEY, config TEXT NOT NULL)")
    before = snapshot(project)
    with pytest.raises(errors.StorageError):
        with api.connect_write(project, "dev"):
            pytest.fail("must not repair an existing incomplete database")
    assert snapshot(project) == before


@pytest.mark.parametrize("fail", [False, True])
def test_store_write_commits_or_rolls_back_and_always_closes(project, fail):
    api = store_api()
    with api.connect_write(project, "dev") as db:
        db.execute("INSERT INTO prompts VALUES ('existing', '{}')")
    try:
        with api.connect_write(project, "dev") as db:
            assert not db.in_transaction  # core owns BEGIN IMMEDIATE.
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO prompts VALUES ('new', '{}')")
            db.execute("INSERT INTO applied_revisions (revision, checksum, applied_at) VALUES ('abc', 'sum', 'now')")
            if fail:
                raise KeyboardInterrupt("injected transaction failure")
    except KeyboardInterrupt:
        assert fail
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        db.execute("SELECT 1")
    with closing(sqlite3.connect(pm_dir(project) / "states" / "dev.sqlite3")) as check:
        assert check.execute("SELECT name FROM prompts ORDER BY name").fetchall() == (
            [("existing",)] if fail else [("existing",), ("new",)])
        assert check.execute("SELECT revision FROM applied_revisions").fetchall() == ([] if fail else [("abc",)])


def test_store_write_setup_failure_closes(project, monkeypatch):
    api = store_api()
    real_connect = sqlite3.connect
    opened = []

    class FailingConnection(sqlite3.Connection):
        def execute(self, sql, *args):
            if sql == "PRAGMA synchronous=FULL":
                raise sqlite3.OperationalError("injected setup failure")
            return super().execute(sql, *args)

    def connect(*args, **kwargs):
        db = real_connect(*args, **kwargs, factory=FailingConnection)
        opened.append(db)
        return db

    monkeypatch.setattr(sqlite3, "connect", connect)
    with pytest.raises(sqlite3.OperationalError, match="setup failure"):
        with api.connect_write(project, "dev"):
            pytest.fail("setup failure must not yield")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")


def test_store_concurrent_first_writes_initialize_schema_once(project, monkeypatch):
    api = store_api()
    path = pm_dir(project) / "states" / "dev.sqlite3"
    real_connect = sqlite3.connect
    barrier = threading.Barrier(2)

    def connect(database, *args, **kwargs):
        if Path(database) == path:
            barrier.wait(timeout=2)
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect)
    failures = []

    def open_write():
        try:
            with api.connect_write(project, "dev"):
                pass
        except BaseException as exc:
            failures.append(exc)

    threads = [threading.Thread(target=open_write) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(4)
    assert not any(thread.is_alive() for thread in threads)
    assert failures == []
    with closing(real_connect(path)) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"applied_revisions", "prompts"} <= tables
