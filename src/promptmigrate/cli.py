"""Command line entry point."""

import argparse
import json
import sqlite3
import sys
import warnings
from pathlib import Path
from . import store
from .core import (
    MigrationError, audit_secrets, check, downgrade, env_add, env_list, init,
    load_revisions, pretty, redacted_config, redacted_diff, redacted_history, revision, upgrade,
)
from .errors import PromptMigrateWarning


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="promptmigrate", description="Alembic-style prompt configuration migrations")
    p.add_argument("--project", default=".", help="Project directory, default: current directory")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Create .promptmigrate/ scaffold")
    rev = sub.add_parser("revision", help="Generate a migration from draft changes")
    rev.add_argument("-m", "--message", required=True)
    sub.add_parser("history", help="Show source migration revisions")
    sub.add_parser("diff", help="Compare drafts to the latest source revision")
    current = sub.add_parser("current", help="Show applied revision in an environment")
    current.add_argument("--env", default="dev")
    up = sub.add_parser("upgrade", help="Upgrade an environment to head or revision")
    up.add_argument("target", nargs="?", default="head")
    up.add_argument("--env", default="dev")
    down = sub.add_parser("downgrade", help="Revert environment to -1, base or revision")
    down.add_argument("target", nargs="?", default="-1")
    down.add_argument("--env", default="dev")
    chk = sub.add_parser("check", help="Verify no drift or edited-applied migrations")
    chk.add_argument("--env", default="dev")
    chk.add_argument("--require-head", action="store_true", help="Fail if migration(s) pending")
    get = sub.add_parser("get", help="Read a config from a local environment")
    get.add_argument("name")
    get.add_argument("--env", default="dev")
    env = sub.add_parser("env", help="Manage declared local environments")
    env_sub = env.add_subparsers(dest="env_command", required=True)
    add_env = env_sub.add_parser("add", help="Declare a local environment")
    add_env.add_argument("name")
    env_sub.add_parser("list", help="List declared environments and local state files")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    error = None
    unhandled = None
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            _run(args)
        except (MigrationError, OSError, sqlite3.Error) as e:
            error = e
        except BaseException as e:
            # Printing here, while warnings.showwarning is still catch_warnings' own recorder, would make
            # _print_warnings append back onto `caught` while iterating it. Defer to after the `with` exits
            # (which restores showwarning), but still before this propagates.
            unhandled = e
    _print_warnings(caught)
    if unhandled is not None:
        raise unhandled
    if error is not None:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


def _print_warnings(caught: list[warnings.WarningMessage]) -> None:
    """Print each distinct PromptMigrate warning once, in first-seen order; pass other warnings through."""
    seen = set()
    for w in caught:
        if not issubclass(w.category, PromptMigrateWarning):
            warnings.showwarning(w.message, w.category, w.filename, w.lineno)
            continue
        key = (w.category, str(w.message))
        if key not in seen:
            seen.add(key)
            print(f"Warning: {w.message}", file=sys.stderr)


def _environment_label(project: Path, env: str) -> str:
    environments, _existed = store.read_environments(project)
    return next((name for name in environments if name.lower() == env.lower()), env)


def _run(args: argparse.Namespace) -> None:
    project = Path(args.project)
    if args.command == "init":
        print(f"Initialized {init(project)}")
    elif args.command == "revision":
        r = revision(project, args.message)
        print(f"Created {r.revision} (parent: {r.down_revision or 'base'}): {r.path}")
    elif args.command == "history":
        revisions, _redacted = redacted_history(project, load=load_revisions)
        for r in revisions:
            print(f"{r.revision} <- {r.down_revision or 'base'} | {r.message}")
    elif args.command == "diff":
        changes, _redacted = redacted_diff(project)
        print(pretty(changes))
    elif args.command == "current":
        label = _environment_label(project, args.env)
        n, total = check(project, args.env)
        revisions = load_revisions(project)
        print(f"{label}: {revisions[n-1].revision if n else 'base'} ({n}/{total} applied)")
    elif args.command == "upgrade":
        label = _environment_label(project, args.env)
        ids = upgrade(project, args.env, args.target)
        print(f"{label}: applied {len(ids)} revision(s): {', '.join(ids) or '(already current)'}")
    elif args.command == "downgrade":
        label = _environment_label(project, args.env)
        ids = downgrade(project, args.env, args.target)
        print(f"{label}: reverted {len(ids)} revision(s): {', '.join(ids) or '(nothing to revert)'}")
    elif args.command == "check":
        label = _environment_label(project, args.env)
        audit_secrets(project)
        n, total = check(project, args.env, args.require_head)
        print(f"OK: {label} is consistent ({n}/{total} revisions applied)")
    elif args.command == "get":
        config, _paths = redacted_config(project, args.env, args.name)
        print(pretty(config), end="")
    elif args.command == "env":
        if args.env_command == "add":
            env_add(project, args.name)
            print(f"Added environment: {args.name}")
        elif args.env_command == "list":
            for name, has_state in env_list(project):
                print(f"{name}: {'state exists' if has_state else 'no state'}")


if __name__ == "__main__":
    sys.exit(main())
