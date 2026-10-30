"""Command line entry point."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from .core import (
    MigrationError, check, downgrade, draft_diff, get_config, init,
    load_revisions, pretty, revision, upgrade,
)


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
    return p


def main(argv: list[str] | None = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    project = Path(args.project)
    try:
        if args.command == "init":
            print(f"Initialized {init(project)}")
        elif args.command == "revision":
            r = revision(project, args.message)
            print(f"Created {r.revision} (parent: {r.down_revision or 'base'}): {r.path}")
        elif args.command == "history":
            for r in load_revisions(project):
                print(f"{r.revision} <- {r.down_revision or 'base'} | {r.message}")
        elif args.command == "diff":
            print(pretty(draft_diff(project)))
        elif args.command == "current":
            n, total = check(project, args.env)
            revisions = load_revisions(project)
            print(f"{args.env}: {revisions[n-1].revision if n else 'base'} ({n}/{total} applied)")
        elif args.command == "upgrade":
            ids = upgrade(project, args.env, args.target)
            print(f"{args.env}: applied {len(ids)} revision(s): {', '.join(ids) or '(already current)'}")
        elif args.command == "downgrade":
            ids = downgrade(project, args.env, args.target)
            print(f"{args.env}: reverted {len(ids)} revision(s): {', '.join(ids) or '(nothing to revert)'}")
        elif args.command == "check":
            n, total = check(project, args.env, args.require_head)
            print(f"OK: {args.env} is consistent ({n}/{total} revisions applied)")
        elif args.command == "get":
            print(pretty(get_config(project, args.env, args.name)), end="")
        return 0
    except (MigrationError, OSError, sqlite3.Error) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
