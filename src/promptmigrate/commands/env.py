"""`env add` / `env list`: manage declared local environments."""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import project, store


def env_add(project_dir: Path, name: str) -> Path:
    project.require_init(project_dir)
    return store.add_environment(project_dir, name)


def env_list(project_dir: Path) -> list[tuple[str, bool]]:
    project.require_init(project_dir)
    return store.list_environments(project_dir)


def run(args: argparse.Namespace) -> None:
    project_dir = Path(args.project)
    if args.env_command == "add":
        env_add(project_dir, args.name)
        print(f"Added environment: {args.name}")
    elif args.env_command == "list":
        for name, has_state in env_list(project_dir):
            print(f"{name}: {'state exists' if has_state else 'no state'}")
