"""Command line entry point."""

import argparse
import sqlite3
import sys
import warnings
from .commands import check, current, diff, downgrade, env, get, history, init, plan, revision, upgrade
from .errors import MigrationError, PromptMigrateWarning

COMMANDS = {
    "init": init, "revision": revision, "history": history, "diff": diff, "current": current,
    "upgrade": upgrade, "downgrade": downgrade, "check": check, "get": get, "env": env, "plan": plan,
}


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
    pln = sub.add_parser("plan", help="Preview upgrade/downgrade to a target without changing anything")
    pln.add_argument("--target", default="head", help="head, -1, base or a revision id (default: head)")
    pln.add_argument("--env", default="dev")
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


def _run(args: argparse.Namespace) -> None:
    COMMANDS[args.command].run(args)


if __name__ == "__main__":
    sys.exit(main())
