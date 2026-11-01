"""PR 4 contract: declared environments, adoption, strict parsing and CLI."""
import importlib
import importlib.util
import json
import os
import warnings
from pathlib import Path

import pytest

from pmtest import nested_config, pm_dir, set_draft, symlink_or_skip, tree_snapshot
from promptmigrate import cli, core, errors, protocol


SYNTAX_MESSAGE = "Environment must be alphanumeric, starting with a letter"


def manifest(project, environments):
    path = pm_dir(project) / "environments.json"
    path.write_text(json.dumps({"environments": environments}), encoding="utf-8")
    return path


def store_api():
    # Assert absent PR4 interfaces at call time: collection must stay usable.
    assert importlib.util.find_spec("promptmigrate.store") is not None, "PR4 environment store is missing"
    return importlib.import_module("promptmigrate.store")


def error_type(name):
    assert hasattr(errors, name), f"PR4 error/warning type {name} is missing"
    return getattr(errors, name)


def core_api(name):
    assert hasattr(core, name), f"PR4 core API {name} is missing"
    return getattr(core, name)


def run_cli(capsys, project, *argv):
    try:
        code = cli.main(["--project", str(project), *argv])
    except SystemExit as exc:
        out, err = capsys.readouterr()
        pytest.fail(f"PR4 CLI command was rejected (exit {exc.code}): {err}")
    out, err = capsys.readouterr()
    return code, out, err


def test_init_declares_exact_defaults(project):
    path = pm_dir(project) / "environments.json"
    assert path.is_file(), "init must write the environment manifest"
    assert json.loads(path.read_text(encoding="utf-8")) == {"environments": {"dev": {}, "staging": {}}}


@pytest.mark.parametrize("name,base", [
    ("EnvironmentNotDeclaredError", errors.MigrationError),
    ("StorageError", errors.MigrationError),
    ("ProductionNameWarning", errors.PromptMigrateWarning),
    ("EnvironmentAdoptionWarning", errors.PromptMigrateWarning),
])
def test_error_type_hierarchy(name, base):
    assert issubclass(error_type(name), base)


def test_undeclared_error_type_carries_env():
    assert error_type("EnvironmentNotDeclaredError")("qa").env == "qa"


@pytest.mark.parametrize("raw", [
    b"{", b'\xef\xbb\xbf{}', b'\xff',
    b'{"environments": {}, "environments": {}}',
    b'{"environments": {"dev": {"x": NaN}}}',
    b'{"environments": {"dev": {"x": Infinity}}}',
    b'{"environments": {"dev": {"x": 1e999}}}',
    b"[" * 2000 + b"]" * 2000,
])
def test_strict_loader_rejects_invalid_json(project, raw):
    path = pm_dir(project) / "environments.json"
    path.write_bytes(raw)
    # The loader kind itself is part of PR4, not an import/collection dependency.
    assert "environments" in protocol._PREFIX, "PR4 strict loader kind is missing"
    with pytest.raises(errors.SchemaError, match="Invalid environments file"):
        protocol.load_json(path, kind="environments", root=pm_dir(project))


def test_strict_loader_valid_json(project):
    path = manifest(project, {"dev": {"owner": "team"}})
    assert "environments" in protocol._PREFIX, "PR4 strict loader kind is missing"
    value, raw, rules = protocol.load_json(path, kind="environments", root=pm_dir(project))
    assert value == {"environments": {"dev": {"owner": "team"}}}
    assert raw == path.read_bytes() and rules == []


def test_manifest_size_limit(project):
    path = manifest(project, {"dev": {"note": "x" * protocol.MAX_CONTROL_FILE_BYTES}})
    assert path.stat().st_size > 1 << 20
    with pytest.raises(errors.SchemaError):
        core.check(project, "dev")


@pytest.mark.parametrize("outside", [False, True])
def test_manifest_symlink_rejected(project, tmp_path, outside):
    path = pm_dir(project) / "environments.json"
    path.unlink(missing_ok=True)
    target = (tmp_path if outside else pm_dir(project)) / "shared.json"
    target.write_text('{"environments": {"dev": {}}}', encoding="utf-8")
    symlink_or_skip(path, target)
    with pytest.raises(errors.SchemaError):
        core.check(project, "dev")


@pytest.mark.parametrize("value", [
    {}, [], None, {"environments": {}, "extra": 1},
    {"environments": []}, {"environments": None},
    {"environments": {"dev": []}}, {"environments": {"dev": None}},
    {"environments": {"dev": {}, "DEV": {}}},
    {"environments": {"../escape": {}}},
    {"environments": {"dev": nested_config(65)}},
])
def test_manifest_schema_rejected(project, value):
    path = pm_dir(project) / "environments.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    before = tree_snapshot(project)
    with pytest.raises(errors.SchemaError):
        core.check(project, "dev")
    assert tree_snapshot(project) == before


def test_unknown_metadata_is_retained(project):
    metadata = {"owner": "team", "future": {"regions": ["local"]}}
    manifest(project, {"dev": metadata})
    assert store_api().read_environments(project) == ({"dev": metadata}, True)


@pytest.mark.parametrize("name", ["", "../escape", "1qa", "a.b", "a/b", "a\\b", "a b", "équipe", "a" * 65])
def test_invalid_name_before_manifest_parsing(project, name):
    from test_read_only_env import snapshot

    (pm_dir(project) / "environments.json").write_text("{", encoding="utf-8")
    before = snapshot(project)
    with pytest.raises(errors.SchemaError) as exc:
        core.check(project, name)
    assert str(exc.value) == SYNTAX_MESSAGE
    assert snapshot(project) == before


@pytest.mark.parametrize("name", ["a", "Qa_2-local", "a" * 64])
def test_env_add_valid_names_and_metadata(project, name):
    path = manifest(project, {"dev": {"owner": "team"}})
    assert core_api("env_add")(project, name) == path
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "environments": {"dev": {"owner": "team"}, name: {}}}


@pytest.mark.parametrize("name", ["DEV", "Dev", "dev"])
def test_env_add_duplicate_rejected(project, name):
    manifest(project, {"dev": {"note": "keep"}})
    before = tree_snapshot(project)
    with pytest.raises(errors.SchemaError):
        core_api("env_add")(project, name)
    assert tree_snapshot(project) == before


@pytest.mark.parametrize("name", ["../escape", "1bad", "a" * 65])
def test_env_add_invalid_name(project, name):
    before = tree_snapshot(project)
    with pytest.raises(errors.SchemaError, match=SYNTAX_MESSAGE):
        core_api("env_add")(project, name)
    assert tree_snapshot(project) == before


@pytest.mark.parametrize("fail", [False, True])
def test_env_add_atomic_replace_and_cleanup(project, monkeypatch, fail):
    path = manifest(project, {"dev": {"owner": "team"}})
    before = tree_snapshot(project)
    calls = []
    real_replace = os.replace

    def replace(source, destination):
        source, destination = Path(source), Path(destination)
        assert source.parent == path.parent and source != path
        assert destination == path
        assert path.read_bytes() == before[".promptmigrate/environments.json"]
        assert json.loads(source.read_text(encoding="utf-8"))["environments"]["qa"] == {}
        calls.append((source, destination))
        if fail:
            raise OSError("injected manifest replacement failure")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", replace)
    add = core_api("env_add")
    if fail:
        with pytest.raises((OSError, errors.MigrationError)):
            add(project, "qa")
        assert tree_snapshot(project) == before
    else:
        add(project, "qa")
        assert json.loads(path.read_text(encoding="utf-8"))["environments"] == {"dev": {"owner": "team"}, "qa": {}}
        assert set(tree_snapshot(project)) == set(before)
    assert len(calls) == 1
    assert not calls[0][0].exists()


def test_env_list_state_flags_without_creating_databases(project):
    manifest(project, {"staging": {}, "dev": {}, "Qa": {}})
    core.upgrade(project, "dev")
    before = tree_snapshot(project)
    assert core_api("env_list")(project) == [("dev", True), ("Qa", False), ("staging", False)]
    assert tree_snapshot(project) == before


@pytest.mark.parametrize("existing", [False, True])
def test_legacy_discovery_is_in_memory(project, existing):
    (pm_dir(project) / "environments.json").unlink(missing_ok=True)
    if existing:
        core.upgrade(project, "dev")
        (pm_dir(project) / "environments.json").unlink(missing_ok=True)
    before = tree_snapshot(project)
    expected = {"dev": {}} if existing else {"dev": {}, "staging": {}}
    assert store_api().read_environments(project) == (expected, False)
    assert core_api("env_list")(project) == [(name, existing) for name in expected]
    assert tree_snapshot(project) == before


@pytest.mark.parametrize("stem", ["1bad", "a" * 65])
def test_legacy_invalid_stems_rejected(project, stem):
    (pm_dir(project) / "environments.json").unlink(missing_ok=True)
    (pm_dir(project) / "states" / f"{stem}.sqlite3").touch()
    with pytest.raises(errors.SchemaError):
        store_api().read_environments(project)


def test_legacy_case_colliding_stems_rejected(project):
    (pm_dir(project) / "environments.json").unlink(missing_ok=True)
    first = pm_dir(project) / "states" / "Qa.sqlite3"
    second = first.with_name("qa.sqlite3")
    first.touch()
    if second.exists():
        pytest.skip("case-insensitive filesystem: Qa.sqlite3 and qa.sqlite3 are one file")
    second.touch()
    with pytest.raises(errors.SchemaError):
        store_api().read_environments(project)


@pytest.mark.parametrize("operation", ["upgrade", "downgrade", "env_add"])
@pytest.mark.parametrize("existing", [False, True])
def test_first_mutation_adopts_once(project, operation, existing):
    path = pm_dir(project) / "environments.json"
    if existing:
        core.upgrade(project, "dev")
    path.unlink(missing_ok=True)
    mutate = core_api(operation)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        mutate(project, "qa" if operation == "env_add" else "dev")
        assert path.exists(), "first mutation must persist inferred declarations"
        expected = {"dev": {}} if existing else {"dev": {}, "staging": {}}
        if operation == "env_add":
            expected["qa"] = {}
        assert json.loads(path.read_text(encoding="utf-8")) == {"environments": expected}
        mutate(project, "qb" if operation == "env_add" else "dev")
    adoption = error_type("EnvironmentAdoptionWarning")
    assert sum(issubclass(w.category, adoption) for w in caught) == 1


@pytest.mark.parametrize("operation", ["check", "get_config", "upgrade", "downgrade"])
def test_undeclared_name_is_typed_error(project, operation):
    manifest(project, {"dev": {}})
    before = tree_snapshot(project)
    expected = error_type("EnvironmentNotDeclaredError")
    with pytest.raises(expected) as exc:
        getattr(core, operation)(project, "prdo", *(["assistant"] if operation == "get_config" else []))
    assert exc.value.env == "prdo"
    assert tree_snapshot(project) == before


def test_canonical_case_resolution_uses_same_database(project):
    manifest(project, {"Qa": {}})
    set_draft(project, "assistant", {"model": "example"})
    core.revision(project, "initial")
    core.upgrade(project, "Qa")
    before = tree_snapshot(project)
    assert core.check(project, "qa") == (1, 1)
    assert core.get_config(project, "qA", "assistant") == {"model": "example"}
    assert store_api().resolve_environment(project, "QA") == "Qa"
    assert tree_snapshot(project) == before


@pytest.mark.parametrize("name", ["prod", "PRODUCTION", "Live"])
def test_production_name_warning_exact_message(project, name):
    manifest(project, {name: {}})
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        core.check(project, name)
    category = error_type("ProductionNameWarning")
    selected = [w for w in caught if issubclass(w.category, category)]
    assert [str(w.message) for w in selected] == [
        f"'{name}' is local SQLite state only; PromptMigrate does not deploy anything."]


@pytest.mark.parametrize("name", ["dev", "production-test", "lively"])
def test_nonproduction_names_do_not_warn(project, name):
    manifest(project, {name: {}})
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        core.check(project, name)
    assert caught == []


def test_cli_env_add_list_and_state_flags(project, capsys):
    manifest(project, {"staging": {}, "dev": {}})
    assert run_cli(capsys, project, "env", "add", "Qa") == (0, "Added environment: Qa\n", "")
    core.upgrade(project, "dev")
    assert run_cli(capsys, project, "env", "list") == (
        0, "dev: state exists\nQa: no state\nstaging: no state\n", "")


@pytest.mark.parametrize("name", ["DEV", "../escape"])
def test_cli_env_add_errors(project, capsys, name):
    manifest(project, {"dev": {}})
    code, out, err = run_cli(capsys, project, "env", "add", name)
    assert code == 1 and out == "" and err.startswith("Error: ")
    if name == "../escape":
        assert err == f"Error: {SYNTAX_MESSAGE}\n"


def test_cli_env_help(project, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--project", str(project), "env", "--help"])
    out, err = capsys.readouterr()
    assert exc.value.code == 0 and "add" in out and "list" in out and err == ""


def test_cli_adoption_notice_once_and_production_warning_before_error(project, capsys):
    core.upgrade(project, "dev")
    (pm_dir(project) / "environments.json").unlink(missing_ok=True)
    code, out, err = run_cli(capsys, project, "upgrade", "--env", "dev")
    assert code == 0 and err.count("Warning: ") == 1
    assert run_cli(capsys, project, "upgrade", "--env", "dev")[2] == ""
    manifest(project, {"prod": {}})
    code, out, err = run_cli(capsys, project, "get", "missing", "--env", "prod")
    assert (code, out) == (1, "")
    assert err == (
        "Warning: 'prod' is local SQLite state only; PromptMigrate does not deploy anything.\n"
        "Error: No prompt named 'missing' in environment 'prod'\n")


@pytest.mark.parametrize("case", ["size", "outside-root"])
def test_strict_loader_control_file_boundaries(project, tmp_path, case):
    path = manifest(project, {"dev": {}})
    if case == "size":
        path.write_bytes(b" " * (protocol.MAX_CONTROL_FILE_BYTES + 1))
    else:
        path = tmp_path / "outside.json"
        path.write_text("{}", encoding="utf-8")
    assert "environments" in protocol._PREFIX, "PR4 strict loader kind is missing"
    with pytest.raises(errors.SchemaError, match="Invalid environments file"):
        protocol.load_json(path, kind="environments", root=pm_dir(project))


def test_empty_environment_manifest_is_valid(project):
    manifest(project, {})
    assert core_api("env_list")(project) == []


def test_metadata_at_depth_limit_is_accepted(project):
    metadata = nested_config(64)
    manifest(project, {"dev": metadata})
    assert store_api().read_environments(project) == ({"dev": metadata}, True)


@pytest.mark.parametrize("operation", ["upgrade", "downgrade"])
def test_mutations_use_canonical_environment_spelling(project, operation):
    manifest(project, {"Qa": {}})
    core.revision(project, "initial")
    if operation == "downgrade":
        core.upgrade(project, "Qa")
    getattr(core, operation)(project, "qa")
    paths = list((pm_dir(project) / "states").glob("*.sqlite3"))
    assert [p.name for p in paths] == ["Qa.sqlite3"]
    assert core.check(project, "QA") == ((1, 1) if operation == "upgrade" else (0, 1))
