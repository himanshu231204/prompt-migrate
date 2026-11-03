"""`current`: show the revision an environment is at."""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import revisions, store
from . import check


def run(args: argparse.Namespace) -> None:
    project_dir = Path(args.project)
    label = store.display_name(project_dir, args.env)
    n, total = check.check(project_dir, args.env)
    revisions_ = revisions.load_revisions(project_dir)
    print(f"{label}: {revisions_[n-1].revision if n else 'base'} ({n}/{total} applied)")
