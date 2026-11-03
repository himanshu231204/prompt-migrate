"""`history`: list source revisions, oldest first."""

from __future__ import annotations

import argparse
import dataclasses
import warnings
from pathlib import Path

from .. import project, revisions, secretscan
from ..errors import SecretRedactedWarning


def redacted_history(project_dir: Path, load=None) -> tuple[list[revisions.Revision], list[str]]:
    """load_revisions() for display: a secret-like message is replaced by "<redacted:RULE>"; returns the ids redacted."""
    allow = project.load_allowlist(project_dir)
    shown, redacted = [], []
    for r in (load or revisions.load_revisions)(project_dir):
        value, paths = secretscan.redact("(message)", {"message": r.message}, allow)
        if paths:
            r = dataclasses.replace(r, message=value["message"])
            redacted.append(r.revision)
        shown.append(r)
    if redacted:
        warnings.warn(secretscan._REDACTED.format(count=len(redacted)), SecretRedactedWarning, stacklevel=2)
    return shown, redacted


def run(args: argparse.Namespace) -> None:
    shown, _redacted = redacted_history(Path(args.project))
    for r in shown:
        print(f"{r.revision} <- {r.down_revision or 'base'} | {r.message}")
