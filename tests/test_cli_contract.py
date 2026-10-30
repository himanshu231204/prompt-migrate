"""PR 2: pin current CLI text output and exit codes (cli.main)."""
import re

import pytest

from pmtest import set_draft
from promptmigrate import cli


def run(capsys, project, *argv):
    code = cli.main(["--project", str(project), *argv])
    out, err = capsys.readouterr()
    return code, out, err


def test_project_flag_works_from_another_cwd(tmp_path, monkeypatch, capsys):
    project, elsewhere = tmp_path / "proj", tmp_path / "elsewhere"
    project.mkdir()
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert run(capsys, project, "init") == (0, f"Initialized {project.resolve() / '.promptmigrate'}\n", "")

    code, out, err = run(capsys, project, "revision", "-m", "initial assistant")
    match = re.fullmatch(r"Created ([0-9a-f]{12}) \(parent: base\): .+\n", out)
    assert (code, err) == (0, "") and match

    assert run(capsys, project, "history") == (0, f"{match.group(1)} <- base | initial assistant\n", "")
    assert not (elsewhere / ".promptmigrate").exists()


def test_environment_commands_text_output(project, capsys):
    assert run(capsys, project, "current") == (0, "dev: base (0/0 applied)\n", "")
    _, out, _ = run(capsys, project, "revision", "-m", "initial")
    rid = re.search(r"Created ([0-9a-f]{12})", out).group(1)

    assert run(capsys, project, "upgrade", "head", "--env", "dev") == (0, f"dev: applied 1 revision(s): {rid}\n", "")
    assert run(capsys, project, "check", "--env", "dev", "--require-head") == (
        0, "OK: dev is consistent (1/1 revisions applied)\n", "")
    assert run(capsys, project, "current", "--env", "dev") == (0, f"dev: {rid} (1/1 applied)\n", "")
    assert run(capsys, project, "upgrade", "--env", "dev") == (0, "dev: applied 0 revision(s): (already current)\n", "")
    assert run(capsys, project, "downgrade", "--env", "dev") == (0, f"dev: reverted 1 revision(s): {rid}\n", "")
    assert run(capsys, project, "downgrade", "--env", "dev") == (0, "dev: reverted 0 revision(s): (nothing to revert)\n", "")


def test_domain_error_goes_to_stderr_with_exit_1(project, capsys):
    run(capsys, project, "revision", "-m", "initial")
    run(capsys, project, "upgrade", "--env", "dev")
    assert run(capsys, project, "get", "nope", "--env", "dev") == (
        1, "", "Error: No prompt named 'nope' in environment 'dev'\n")


def test_invalid_env_name_exit_1(project, capsys):
    assert run(capsys, project, "check", "--env", "../escape") == (
        1, "", "Error: Environment must be alphanumeric, starting with a letter\n")


def test_unknown_subcommand_exits_2(project):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--project", str(project), "bogus"])
    assert exit_info.value.code == 2


def test_readme_five_minute_example(tmp_path, capsys):
    """Exercises README.md "Five-minute example" in order; every command must exit 0."""
    project = tmp_path
    steps = [
        ["init"],
        ["revision", "-m", "initial assistant prompt"],
        ["history"],
        ["upgrade", "head", "--env", "dev"],
        ["check", "--env", "dev", "--require-head"],
        ["get", "assistant", "--env", "dev"],
    ]
    for argv in steps:
        code, _, err = run(capsys, project, *argv)
        assert (code, err) == (0, ""), argv

    set_draft(project, "assistant", {"messages": [{"role": "system", "content": "Refuse unsafe requests."}]})
    for argv in (
        ["diff"],
        ["revision", "-m", "strengthen refusal instructions"],
        ["upgrade", "head", "--env", "staging"],
        ["current", "--env", "staging"],
        ["downgrade", "-1", "--env", "staging"],
    ):
        code, out, err = run(capsys, project, *argv)
        assert (code, err) == (0, ""), argv
    assert out.startswith("staging: reverted 1 revision(s): ")
