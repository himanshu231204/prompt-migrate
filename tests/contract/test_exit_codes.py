"""PR 6: typed errors map to exit codes 0-5; warnings never change the exit code."""
import inspect
import json
import sqlite3

import pytest

from pmtest import create, pm_dir, set_draft, write_revision
from promptmigrate import cli, errors, output, revisions, store

EXPECTED = {
    errors.MigrationError: (1, "error"),
    errors.InitializationError: (1, "error"),
    errors.EnvironmentNotDeclaredError: (1, "error"),
    errors.TargetError: (1, "error"),
    errors.PendingRevisionsError: (1, "error"),
    errors.SchemaError: (3, "schema"),
    errors.SecretDetectedError: (3, "schema"),
    errors.RevisionGraphError: (3, "schema"),
    errors.DriftError: (4, "conflict"),
    errors.IntegrityError: (4, "conflict"),
    errors.MigrationConflictError: (4, "conflict"),
    errors.StorageError: (5, "storage"),
    sqlite3.Error: (5, "storage"),
    OSError: (5, "storage"),
}


def make(cls):
    if cls is errors.EnvironmentNotDeclaredError:
        return cls("x")
    if cls is errors.SecretDetectedError:
        return cls([])
    return cls("boom")


def run(capsys, project, *argv):
    code = cli.main(["--project", str(project), *argv])
    out, err = capsys.readouterr()
    return code, out, err


def all_error_classes():
    return [c for _, c in inspect.getmembers(errors, inspect.isclass)
            if issubclass(c, errors.MigrationError)]


@pytest.mark.parametrize("cls", list(EXPECTED))
def test_error_class_to_code_table(cls):
    code, name = EXPECTED[cls]
    assert output.exit_code_for(make(cls)) == code
    assert output.error_name_for(make(cls)) == name


def test_every_migration_error_subclass_is_in_the_table():
    assert set(all_error_classes()) <= set(EXPECTED)


def test_exit_codes_are_within_0_to_5():
    assert {c for c, _ in EXPECTED.values()} <= {1, 3, 4, 5}


def applied_project(project, capsys):
    run(capsys, project, "revision", "-m", "initial")
    run(capsys, project, "upgrade", "--env", "dev")
    return project


def test_success_is_0(project, capsys):
    assert run(capsys, project, "history")[0] == 0


def test_usage_error_is_2(project):
    for argv in (["bogus"], ["--output", "xml", "history"], ["upgrade", "--bad-flag"]):
        with pytest.raises(SystemExit) as e:
            cli.main(["--project", str(project), *argv])
        assert e.value.code == 2


def test_uninitialized_project_is_1(tmp_path, capsys):
    assert run(capsys, tmp_path, "history")[0] == 1


def test_unknown_target_is_1(project, capsys):
    assert run(capsys, project, "upgrade", "ffffffffffff")[0] == 1


def test_pending_revisions_under_require_head_is_1(project, capsys):
    run(capsys, project, "revision", "-m", "initial")
    assert run(capsys, project, "check", "--require-head")[0] == 1


def test_no_changes_to_revise_is_3(project, capsys):
    run(capsys, project, "revision", "-m", "initial")
    assert run(capsys, project, "revision", "-m", "again")[0] == 3


def test_invalid_environment_name_is_3(project, capsys):
    assert run(capsys, project, "check", "--env", "../escape")[0] == 3


def test_malformed_revision_file_is_3(project, capsys):
    (pm_dir(project) / "versions" / "bad.json").write_text("{not json", encoding="utf-8")
    assert run(capsys, project, "history")[0] == 3


def test_edited_applied_revision_is_4(project, capsys):
    applied_project(project, capsys)
    path = next((pm_dir(project) / "versions").glob("*.json"))
    path.write_text(json.dumps({**json.loads(path.read_bytes()), "message": "edited after apply"}), encoding="utf-8")
    assert run(capsys, project, "check", "--env", "dev")[0] == 4


def test_state_drift_is_4(project, capsys):
    applied_project(project, capsys)
    db = sqlite3.connect(pm_dir(project) / "states" / "dev.sqlite3")
    db.execute("DELETE FROM prompts")
    db.commit()
    db.close()
    assert run(capsys, project, "check", "--env", "dev")[0] == 4


def test_corrupt_state_file_is_5(project, capsys):
    applied_project(project, capsys)
    (pm_dir(project) / "states" / "dev.sqlite3").write_bytes(b"this is not a database" * 50)
    assert run(capsys, project, "check", "--env", "dev")[0] == 5


def test_oserror_is_5(project, capsys, monkeypatch):
    def boom(_project):
        raise OSError("disk on fire")
    monkeypatch.setattr(revisions, "load_revisions", boom)
    assert run(capsys, project, "history") == (5, "", "Error: disk on fire\n")


def test_warnings_never_change_exit_code(project, capsys, monkeypatch):
    import warnings
    from promptmigrate.errors import LegacyRevisionWarning

    def noisy(_project):
        warnings.warn("careful", LegacyRevisionWarning)
        return []
    monkeypatch.setattr(revisions, "load_revisions", noisy)
    assert run(capsys, project, "history") == (0, "", "Warning: careful\n")

    def noisy_failing(_project):
        warnings.warn("careful", LegacyRevisionWarning)
        raise errors.DriftError("drifted")
    monkeypatch.setattr(revisions, "load_revisions", noisy_failing)
    assert run(capsys, project, "history") == (4, "", "Warning: careful\nError: drifted\n")


class BrokenStdout:
    def write(self, _text):
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self):
        pass


@pytest.mark.parametrize("fmt", ["text", "json"])
def test_stdout_write_failure_is_a_storage_error(project, capsys, monkeypatch, fmt):
    import sys
    monkeypatch.setattr(sys, "stdout", BrokenStdout())
    code = cli.main(["--project", str(project), "--output", fmt, "history"])
    assert code == 5
    assert capsys.readouterr().err.startswith("Error: ")


@pytest.mark.parametrize("value", [0, 2, True, 1.0, "1"])
def test_unsupported_format_version_is_3(project, capsys, value):
    write_revision(project, "a" * 12, None, {"assistant": create()}, format_version=value)
    code, _, err = run(capsys, project, "history")
    assert (code, err) == (3, "Error: Unsupported format_version in aaaaaaaaaaaa.json\n")


def test_unknown_v1_top_level_key_is_3(project, capsys):
    path = write_revision(project, "a" * 12, None, {"assistant": create()}, format_version=1)
    path.write_text(json.dumps({**json.loads(path.read_bytes()), "author": "x"}), encoding="utf-8")
    code, _, err = run(capsys, project, "check", "--env", "dev")
    assert (code, err) == (3, "Error: Unknown top-level key in aaaaaaaaaaaa.json: author\n")
