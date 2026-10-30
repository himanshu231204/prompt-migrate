"""PR 1: every command closes its SQLite connection, on success and on failure."""
import sqlite3

import pytest

from promptmigrate import core
from promptmigrate.core import MigrationError, check, downgrade, get_config, init, revision, upgrade


@pytest.fixture
def project(tmp_path):
    init(tmp_path)
    revision(tmp_path, "initial")
    upgrade(tmp_path, "dev")
    return tmp_path


@pytest.fixture
def opened(project, monkeypatch):
    """Record every connection the library opens after the project has been set up."""
    connections = []
    real_connect = sqlite3.connect

    def tracking_connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(core.sqlite3, "connect", tracking_connect)
    return connections


def state_file(project, env="dev"):
    return project / ".promptmigrate" / "states" / f"{env}.sqlite3"


def assert_all_closed(connections):
    assert connections, "expected the command to open at least one connection"
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")


COMMANDS = {
    "check": lambda p: check(p, "dev"),
    "upgrade": lambda p: upgrade(p, "dev"),
    "downgrade": lambda p: downgrade(p, "dev"),
    "get": lambda p: get_config(p, "dev", "assistant"),
}


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_command_closes_connection(project, opened, command):
    COMMANDS[command](project)
    assert_all_closed(opened)


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_state_file_deletable_after_command(project, opened, command):
    COMMANDS[command](project)
    state_file(project).unlink()  # raises PermissionError on Windows if a handle leaked
    assert not state_file(project).exists()


def test_connection_closed_when_command_fails(project, opened):
    revision_file = next((project / ".promptmigrate" / "versions").glob("*.json"))
    revision_file.write_bytes(revision_file.read_bytes() + b"\n")  # tamper after apply
    with pytest.raises(MigrationError, match="modified after apply"):
        check(project, "dev")
    assert_all_closed(opened)
    state_file(project).unlink()


def test_failed_upgrade_rolls_back_every_write(tmp_path, monkeypatch):
    init(tmp_path)
    revision(tmp_path, "one")
    draft = tmp_path / ".promptmigrate" / "drafts" / "assistant.json"
    draft.write_text('{"messages": [{"role": "system", "content": "two"}]}', encoding="utf-8")
    revision(tmp_path, "two")

    real_canonical = core.canonical
    calls = []

    def fail_on_second_write(obj):
        calls.append(obj)
        if len(calls) == 2:  # revision one is written; fail while writing revision two
            raise RuntimeError("injected write failure")
        return real_canonical(obj)

    monkeypatch.setattr(core, "canonical", fail_on_second_write)
    with pytest.raises(RuntimeError, match="injected write failure"):
        upgrade(tmp_path, "dev")
    monkeypatch.undo()

    assert len(calls) == 2  # the failure happened mid-transaction, after a real write
    assert check(tmp_path, "dev") == (0, 2)  # ledger unchanged
    with pytest.raises(MigrationError, match="No prompt named"):
        get_config(tmp_path, "dev", "assistant")  # config table unchanged
