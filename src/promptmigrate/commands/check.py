"""`check`: verify an environment against source history, and warn about secrets in history."""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

from .. import apply, output, project, revisions, secretscan, store
from ..errors import PendingRevisionsError, SchemaError, SecretInHistoryWarning, StaleAllowlistWarning


def check(project_dir: Path, env: str, require_head: bool = False) -> tuple[int, int]:
    env = store.resolve_environment(project_dir, env)
    revisions_ = revisions.load_revisions(project_dir)
    with store.connect_readonly(project_dir, env) as db:
        count = apply._verify(db, revisions_) if db is not None else 0
    if require_head and count != len(revisions_):
        raise PendingRevisionsError(f"Environment is behind head: {len(revisions_) - count} pending revisions")
    return count, len(revisions_)


def audit_secrets(project_dir: Path) -> None:
    """Warn about secret-like values in source history and about allowlist entries that match nothing.

    Warnings only: `check` verifies integrity, not hygiene. Secrets in history stay in Git and must be rotated.
    """
    revisions_ = revisions.load_revisions(project_dir)
    allow = project.load_allowlist(project_dir)
    used: set[secretscan.AllowEntry] = set()
    for r in revisions_:
        seen: list[secretscan.Finding] = []
        seen += [f for f in secretscan.scan("(message)", {"message": r.message}, allow, used) if f not in seen]
        for name, change in r.changes.items():
            for side in ("before", "after"):
                if change[side] is not None:
                    seen += [f for f in secretscan.scan(name, change[side], allow, used) if f not in seen]
        for finding in seen:
            warnings.warn(f"revision {r.revision}: {finding.name} {finding.path} {finding.rule}",
                          SecretInHistoryWarning, stacklevel=2)
    try:
        drafts = project.read_drafts(project_dir)
    except SchemaError:
        return  # an unreadable draft is reported by diff/revision; without drafts, staleness is unknown
    for name, config in drafts.items():
        secretscan.scan(name, config, allow, used)
    for entry in allow:
        if entry not in used:
            warnings.warn(f"secret allowlist entry {entry.name} {entry.path} {entry.rule} matched nothing in drafts "
                          "or history", StaleAllowlistWarning, stacklevel=2)


def execute(args: argparse.Namespace) -> output.Result:
    project_dir = Path(args.project)
    label = store.display_name(project_dir, args.env)
    audit_secrets(project_dir)
    n, total = check(project_dir, args.env, args.require_head)
    data = {"consistent": True, "applied": n, "total": total}
    return output.Result("check", data, f"OK: {label} is consistent ({n}/{total} revisions applied)\n", label)


def run(args: argparse.Namespace) -> None:
    output.emit_result(execute(args), "text", [])
