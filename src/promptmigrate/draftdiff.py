"""Drafts compared with the replayed source head (never with an environment)."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

from . import project, protocol, revisions, secretscan
from .errors import SecretRedactedWarning


def draft_diff(project_dir: Path) -> dict[str, dict[str, Any]]:
    expected = revisions.replay_revisions(revisions.load_revisions(project_dir))
    wanted = project.read_drafts(project_dir)
    return {
        name: {"before": expected.get(name), "after": wanted.get(name)}
        for name in sorted(expected.keys() | wanted.keys())
        if not protocol.same(expected.get(name), wanted.get(name))
    }


def redacted_diff(project_dir: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    """draft_diff() for display: secret-like values replaced by "<redacted:RULE>", plus what was redacted.

    Redacted output is not a config source: never feed it back into a draft or an application.
    """
    allow = project.load_allowlist(project_dir)
    changes, redacted = {}, []
    for name, change in draft_diff(project_dir).items():
        sides = {}
        for side in ("before", "after"):
            value = change[side]
            if value is not None:
                value, paths = secretscan.redact(name, value, allow)
                redacted += [{"name": name, "side": side, "path": path} for path in paths]
            sides[side] = value
        changes[name] = sides
    if redacted:
        warnings.warn(secretscan._REDACTED.format(count=len(redacted)), SecretRedactedWarning, stacklevel=2)
    return changes, redacted
