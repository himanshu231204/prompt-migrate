"""`current`: show the revision an environment is at."""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import output, revisions, store
from . import check


def execute(args: argparse.Namespace) -> output.Result:
    """Run `current` and return its text and JSON result."""
    project_dir = Path(args.project)
    label = store.display_name(project_dir, args.env)
    n, total = check.check(project_dir, args.env)
    revisions_ = revisions.load_revisions(project_dir)
    head = revisions_[n - 1].revision if n else None
    data = {"revision": head, "applied": n, "total": total}
    return output.Result("current", data, f"{label}: {head or 'base'} ({n}/{total} applied)\n", label)


def run(args: argparse.Namespace) -> None:
    """Run `current` and print its text output."""
    output.emit_result(execute(args), "text", [])
