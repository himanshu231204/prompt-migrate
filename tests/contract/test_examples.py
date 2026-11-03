"""Shipped examples run end to end and leave their own directory untouched."""
import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from pmtest import tree_snapshot
from promptmigrate import secretscan

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
SRC = Path(importlib.import_module("promptmigrate").__file__).resolve().parents[1]


def run_example(tmp_path, name):
    example = tmp_path / name
    shutil.copytree(EXAMPLES / name, example)
    before = tree_snapshot(example)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [str(SRC), os.environ.get("PYTHONPATH")])))
    result = subprocess.run([sys.executable, str(example / "run.py"), str(tmp_path / "project")],
                            capture_output=True, text=True, env=env, timeout=120)
    return result, before, tree_snapshot(example)


def test_multi_agent_basic_walks_the_whole_lifecycle(tmp_path):
    result, before, after = run_example(tmp_path, "multi-agent-basic")
    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout
    expected = [
        "Initialized ",
        "Created ",
        "dev: applied 1 revision(s): ",
        "OK: dev is consistent (1/1 revisions applied)",
        "Created ",
        "dev: applied 1 revision(s): ",
        "OK: dev is consistent (2/2 revisions applied)",
        "dev: reverted 1 revision(s): ",
        "OK: dev is consistent (1/2 revisions applied)",
    ]
    position = 0
    for line in expected:
        position = out.index(line, position) + len(line)
    assert '"temperature": 0.2' in out  # `get researcher` after the second upgrade shows the edited draft
    assert "Warning:" not in result.stderr and "Error:" not in result.stderr
    assert after == before


def test_multi_agent_basic_drafts_hold_no_secret_like_values():
    paths = sorted((EXAMPLES / "multi-agent-basic" / "drafts").glob("*.json"))
    assert [p.name for p in paths] == ["planner.json", "researcher.json"]
    for path in paths:
        config = json.loads(path.read_text(encoding="utf-8"))
        assert secretscan.scan(path.stem, config, []) == [], path.name
