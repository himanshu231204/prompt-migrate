"""`get`: read one config from an environment, with secret-like values redacted for display."""

from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path
from typing import Any

from .. import apply, output, project, revisions, secretscan, store
from ..errors import SecretRedactedWarning, TargetError


def get_config(project_dir: Path, env: str, name: str) -> dict[str, Any]:
    env = store.resolve_environment(project_dir, env)
    revisions_ = revisions.load_revisions(project_dir)
    with store.connect_readonly(project_dir, env) as db:
        if db is None:
            row = None
        else:
            apply._verify(db, revisions_, env)
            row = db.execute("SELECT config FROM prompts WHERE name=?", (name,)).fetchone()
    if not row:
        raise TargetError(f"No prompt named {name!r} in environment {env!r}")
    return json.loads(row[0])


def redacted_config(project_dir: Path, env: str, name: str) -> tuple[dict[str, Any], list[str]]:
    """get_config() for display: secret-like values replaced by "<redacted:RULE>", plus the redacted paths."""
    config, paths = secretscan.redact(name, get_config(project_dir, env, name), project.load_allowlist(project_dir))
    if paths:
        warnings.warn(secretscan._REDACTED.format(count=len(paths)), SecretRedactedWarning, stacklevel=2)
    return config, paths


def execute(args: argparse.Namespace) -> output.Result:
    """Run `get` and return its text and JSON result."""
    project_dir = Path(args.project)
    label = store.display_name(project_dir, args.env)
    config, paths = redacted_config(project_dir, args.env, args.name)
    data = {"name": args.name, "config": config, "redacted": paths}
    return output.Result("get", data, project.pretty(config), label)


def run(args: argparse.Namespace) -> None:
    """Run `get` and print its text output."""
    output.emit_result(execute(args), "text", [])
