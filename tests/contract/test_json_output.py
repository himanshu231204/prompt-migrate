"""PR 6: `--output json` prints one stable envelope per command on stdout."""
import json
import re
import warnings

import pytest

from pmtest import fake_key, pm_dir, set_draft
from promptmigrate import cli, errors, revisions

SCHEMA = "promptmigrate.output/1"


def run(capsys, project, *argv, fmt="json"):
    code = cli.main(["--project", str(project), "--output", fmt, *argv])
    out, err = capsys.readouterr()
    return code, out, err


def jrun(capsys, project, *argv):
    code, out, err = run(capsys, project, *argv)
    assert out.endswith("\n") and out.count("\n") == 1, out
    return code, json.loads(out), err


def ok(capsys, project, *argv):
    code, doc, err = jrun(capsys, project, *argv)
    assert (code, err) == (0, ""), (argv, doc, err)
    assert doc["ok"] is True and doc["schema"] == SCHEMA
    assert doc["warnings"] == []
    return doc


def test_init(tmp_path, capsys):
    doc = ok(capsys, tmp_path, "init")
    assert doc["command"] == "init" and doc["env"] is None
    assert doc["data"] == {"path": str((tmp_path / ".promptmigrate").resolve())}


def test_revision_history_diff(project, capsys):
    d = ok(capsys, project, "diff")
    assert d["command"] == "diff" and d["data"]["redacted"] == []
    assert list(d["data"]["changes"]) == ["assistant"]
    doc = ok(capsys, project, "revision", "-m", "initial")
    rid = doc["data"]["revision"]
    assert re.fullmatch(r"[0-9a-f]{12}", rid)
    assert doc["data"]["down_revision"] is None and doc["data"]["message"] == "initial"
    assert doc["data"]["path"].endswith(".json")
    h = ok(capsys, project, "history")
    assert h["data"]["revisions"] == [{"revision": rid, "down_revision": None, "message": "initial"}]
    assert ok(capsys, project, "diff")["data"]["changes"] == {}


def test_env_commands(project, capsys):
    a = ok(capsys, project, "env", "add", "qa")
    assert a["command"] == "env add" and a["data"] == {"name": "qa"}
    ls = ok(capsys, project, "env", "list")
    assert ls["command"] == "env list"
    assert {"name": "qa", "has_state": False} in ls["data"]["environments"]


def test_current_upgrade_check_downgrade_get(project, capsys):
    rid = ok(capsys, project, "revision", "-m", "initial")["data"]["revision"]
    cur = ok(capsys, project, "current")
    assert cur["env"] == "dev"
    assert cur["data"] == {"revision": None, "applied": 0, "total": 1}
    up = ok(capsys, project, "upgrade", "--env", "dev")
    assert up["command"] == "upgrade" and up["env"] == "dev"
    assert up["data"] == {"direction": "up", "target": "head", "revisions": [rid]}
    again = ok(capsys, project, "upgrade", "--env", "dev")
    assert again["data"]["revisions"] == []
    chk = ok(capsys, project, "check", "--env", "dev", "--require-head")
    assert chk["data"] == {"consistent": True, "applied": 1, "total": 1}
    assert ok(capsys, project, "current")["data"]["revision"] == rid
    g = ok(capsys, project, "get", "assistant")
    assert g["data"]["name"] == "assistant" and g["data"]["redacted"] == []
    assert g["data"]["config"]["model"] == "provider/model-id"
    down = ok(capsys, project, "downgrade", "--env", "dev")
    assert down["data"] == {"direction": "down", "target": "-1", "revisions": [rid]}



def test_plan(project, capsys):
    rid = ok(capsys, project, "revision", "-m", "initial")["data"]["revision"]
    up = ok(capsys, project, "plan", "--env", "dev")
    assert up["command"] == "plan" and up["env"] == "dev"
    assert up["data"] == {"direction": "upgrade", "start": None, "target": rid,
                          "steps": [{"revision": rid, "changes": [{"name": "assistant", "kind": "create"}]}]}
    ok(capsys, project, "upgrade", "--env", "dev")
    assert ok(capsys, project, "plan")["data"] == {"direction": "none", "start": rid, "target": rid, "steps": []}
    down = ok(capsys, project, "plan", "--target", "base")
    assert down["data"]["direction"] == "downgrade" and down["data"]["target"] is None
    assert down["data"]["steps"] == [{"revision": rid, "changes": [{"name": "assistant", "kind": "delete"}]}]
    c, doc, err = jrun(capsys, project, "plan", "--target", "ffffffffffff")
    assert (c, err, doc["command"], doc["error"]["code"]) == (1, "", "plan", "error")

@pytest.mark.parametrize("argv,code,name", [
    (["upgrade", "ffffffffffff"], 1, "error"),
    (["revision", "-m", "x"], 3, "schema"),
])
def test_error_envelope(project, capsys, argv, code, name):
    if argv[0] == "revision":
        ok(capsys, project, "revision", "-m", "initial")
    c, doc, err = jrun(capsys, project, *argv)
    assert (c, err) == (code, "")
    assert doc["ok"] is False and doc["schema"] == SCHEMA and doc["command"] == argv[0]
    assert doc["error"]["code"] == name and doc["error"]["exit_code"] == code
    assert isinstance(doc["error"]["message"], str) and doc["error"]["message"]
    assert "data" not in doc


def test_error_envelope_for_env_commands_has_env(project, capsys):
    c, doc, _ = jrun(capsys, project, "check", "--env", "../escape")
    assert c == 3 and doc["command"] == "check"


def test_warnings_go_in_the_list_not_stderr(project, capsys, monkeypatch):
    def noisy(_project):
        warnings.warn("careful", errors.LegacyRevisionWarning)
        warnings.warn("careful", errors.LegacyRevisionWarning)
        return []
    monkeypatch.setattr(revisions, "load_revisions", noisy)
    code, doc, err = jrun(capsys, project, "history")
    assert (code, err) == (0, "")
    assert doc["warnings"] == [{"category": "LegacyRevisionWarning", "message": "careful"}]


def test_warnings_included_in_error_envelope(project, capsys, monkeypatch):
    def noisy(_project):
        warnings.warn("careful", errors.LegacyRevisionWarning)
        raise errors.DriftError("drifted")
    monkeypatch.setattr(revisions, "load_revisions", noisy)
    code, doc, err = jrun(capsys, project, "history")
    assert (code, err) == (4, "")
    assert doc["error"] == {"code": "conflict", "exit_code": 4, "message": "drifted"}
    assert doc["warnings"] == [{"category": "LegacyRevisionWarning", "message": "careful"}]


def test_text_is_default_and_has_no_json(project, capsys):
    default = cli.main(["--project", str(project), "history"])
    d_out = capsys.readouterr()
    explicit = run(capsys, project, "history", fmt="text")
    assert (default, d_out.out, d_out.err) == explicit


def test_secrets_stay_redacted_in_json(project, capsys):
    secret = fake_key("7")
    set_draft(project, "assistant", {"messages": [{"role": "system", "content": "k " + secret}]})
    code, out, err = run(capsys, project, "diff")
    assert code == 0 and secret not in out + err
    assert json.loads(out)["data"]["redacted"]
    code, out, err = run(capsys, project, "revision", "-m", "leak")
    assert code == 3 and secret not in out + err


def test_secrets_in_history_redacted_in_json(project, capsys, monkeypatch):
    from pmtest import write_revision, create
    secret = fake_key("5")
    write_revision(project, "a" * 12, None, {"assistant": create({"messages": [{"role": "system", "content": "x"}]})},
                   message="m " + secret)
    code, out, err = run(capsys, project, "history")
    assert code == 0 and secret not in out + err
    doc = json.loads(out)
    assert doc["warnings"] and "<redacted:" in doc["data"]["revisions"][0]["message"]


def test_env_uses_declared_spelling_on_success_and_error(project, capsys):
    ok(capsys, project, "revision", "-m", "initial")
    ok(capsys, project, "upgrade", "--env", "dev")
    assert ok(capsys, project, "get", "assistant", "--env", "DEV")["env"] == "dev"
    assert ok(capsys, project, "current", "--env", "DEV")["env"] == "dev"
    code, doc, _ = jrun(capsys, project, "get", "nope", "--env", "DEV")
    assert code == 1 and doc["env"] == "dev"


def test_error_envelope_keeps_the_given_spelling_when_resolution_fails(project, capsys):
    code, doc, _ = jrun(capsys, project, "check", "--env", "../escape")
    assert code == 3 and doc["env"] == "../escape"
    code, doc, _ = jrun(capsys, project, "check", "--env", "Nope")
    assert code == 1 and doc["env"] == "Nope"
