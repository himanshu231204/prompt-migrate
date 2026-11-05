"""`env add` / `env list`: manage declared local environments."""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import output, project, store


def env_add(project_dir: Path, name: str) -> Path:
    project.require_init(project_dir)
    return store.add_environment(project_dir, name)


def env_list(project_dir: Path) -> list[tuple[str, bool]]:
    project.require_init(project_dir)
    return store.list_environments(project_dir)


def execute(args: argparse.Namespace) -> output.Result:
    """Run `env` and return its text and JSON result."""
    project_dir = Path(args.project)
    if args.env_command == "add":
        env_add(project_dir, args.name)
        return output.Result("env add", {"name": args.name}, f"Added environment: {args.name}\n")
    listed = env_list(project_dir)
    data = {"environments": [{"name": name, "has_state": has_state} for name, has_state in listed]}
    text = "".join(f"{name}: {'state exists' if has_state else 'no state'}\n" for name, has_state in listed)
    return output.Result("env list", data, text)


def run(args: argparse.Namespace) -> None:
    """Run `env` and print its text output."""
    output.emit_result(execute(args), "text", [])
