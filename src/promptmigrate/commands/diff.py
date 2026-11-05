"""`diff`: show drafts compared with the source head, with secret-like values redacted."""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import draftdiff, output, project


def execute(args: argparse.Namespace) -> output.Result:
    """Run `diff` and return its text and JSON result."""
    changes, redacted = draftdiff.redacted_diff(Path(args.project))
    return output.Result("diff", {"changes": changes, "redacted": redacted}, project.pretty(changes) + "\n")


def run(args: argparse.Namespace) -> None:
    """Run `diff` and print its text output."""
    output.emit_result(execute(args), "text", [])
