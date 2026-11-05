"""`history`: list source revisions, oldest first."""

from __future__ import annotations

import argparse
import dataclasses
import warnings
from pathlib import Path

from .. import output, project, revisions, secretscan
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


def execute(args: argparse.Namespace) -> output.Result:
    shown, redacted = redacted_history(Path(args.project))
    data = {"revisions": [{"revision": r.revision, "down_revision": r.down_revision, "message": r.message}
                          for r in shown],
            "redacted": redacted}
    text = "".join(f"{r.revision} <- {r.down_revision or 'base'} | {r.message}\n" for r in shown)
    return output.Result("history", data, text)


def run(args: argparse.Namespace) -> None:
    output.emit_result(execute(args), "text", [])
