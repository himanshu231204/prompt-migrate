"""Command line entry point."""

import argparse
import sqlite3
import sys
import warnings
from . import output
from .commands import check, current, diff, downgrade, env, get, history, init, revision, upgrade
from .errors import PromptMigrateWarning

COMMANDS = {
    "init": init, "revision": revision, "history": history, "diff": diff, "current": current,
    "upgrade": upgrade, "downgrade": downgrade, "check": check, "get": get, "env": env,
}


def build_parser() -> argparse.ArgumentParser:
    """The argument parser: global flags, then one subparser per command."""
    p = argparse.ArgumentParser(prog="promptmigrate", description="Alembic-style prompt configuration migrations")
    p.add_argument("--project", default=".", help="Project directory, default: current directory")
    p.add_argument("--output", choices=output.FORMATS, default="text", help="Output format, default: text")
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
    """Parse, run the command, render the result or handled error, and return the exit code."""
    args = build_parser().parse_args(argv)
    result = error = unhandled = None
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            result = COMMANDS[args.command].execute(args)
        except output.HANDLED as e:
            error = e
        except BaseException as e:
            # Printing here, while warnings.showwarning is still catch_warnings' own recorder, would make
            # _print_warnings append back onto `caught` while iterating it. Defer to after the `with` exits
            # (which restores showwarning), but still before this propagates.
            unhandled = e
    as_json = args.output == "json"
    if as_json:
        for w in caught:  # JSON lists PromptMigrate warnings itself; anything else still goes to stderr
            if not issubclass(w.category, PromptMigrateWarning):
                warnings.showwarning(w.message, w.category, w.filename, w.lineno)
    else:
        _print_warnings(caught)
    if unhandled is not None:
        raise unhandled
    warned = output.collect_warnings(caught)
    try:
        if error is not None:
            return output.emit_error(error, args.output, *output.describe(args), warned)
        output.emit_result(result, args.output, warned)
    except OSError as e:  # writing the result failed: a closed pipe or a full destination
        print(f"Error: {e}", file=sys.stderr)
        return 5
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


if __name__ == "__main__":
    sys.exit(main())
