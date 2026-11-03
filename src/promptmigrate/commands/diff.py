"""`diff`: show drafts compared with the source head, with secret-like values redacted."""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import draftdiff, project


def run(args: argparse.Namespace) -> None:
    changes, _redacted = draftdiff.redacted_diff(Path(args.project))
    print(project.pretty(changes))
