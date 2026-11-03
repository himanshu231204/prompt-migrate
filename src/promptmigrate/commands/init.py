"""`init`: create the .promptmigrate/ scaffold."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .. import project
from ..errors import InitializationError


def init(project_dir: Path) -> Path:
    root = project.root_dir(project_dir)
    if root.exists():
        raise InitializationError(f"Already exists: {root}")
    (root / "versions").mkdir(parents=True)
    (root / "drafts").mkdir()
    (root / "states").mkdir()
    (root / ".gitignore").write_text("/states/\n", encoding="utf-8")
    (root / "environments.json").write_text(
        json.dumps({"environments": {"dev": {}, "staging": {}}}, indent=2) + "\n", encoding="utf-8"
    )
    starter = {
        "messages": [{"role": "system", "content": "You are a helpful AI assistant."}],
        "model": "provider/model-id",
        "parameters": {"temperature": 0},
        "tools": [],
        "response_schema": None,
    }
    (root / "drafts" / "assistant.json").write_text(project.pretty(starter), encoding="utf-8")
    return root


def run(args: argparse.Namespace) -> None:
    print(f"Initialized {init(Path(args.project))}")
