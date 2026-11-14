"""`restamp`: accept line-ending-only changes to applied v0 revisions by re-stamping their ledger checksums."""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import apply, output, revisions, store


def restamp(project_dir: Path, env: str) -> list[str]:
    """Re-stamp each applied v0 row whose file differs only in line endings (ADR-027); all or nothing.

    Any other mismatch raises the normal IntegrityError and nothing is written. No audit record is kept until the
    cycle-3 events table.
    """
    env = store.resolve_environment(project_dir, env)
    revisions_ = revisions.load_revisions(project_dir)
    if not store._db_path(project_dir, env).exists():
        return []  # base state: nothing is applied, so nothing is re-stamped and no state file is created
    with store.connect_write(project_dir, env) as db:
        db.execute("BEGIN IMMEDIATE")
        stale = apply.line_ending_only(db, revisions_)
        for r in stale:
            db.execute("UPDATE applied_revisions SET checksum=? WHERE revision=?", (r.checksum, r.revision))
        apply._verify(db, revisions_, env)
    return [r.revision for r in stale]


def execute(args: argparse.Namespace) -> output.Result:
    """Run `restamp` and return its text and JSON result."""
    project_dir = Path(args.project)
    label = store.display_name(project_dir, args.env)
    ids = restamp(project_dir, args.env)
    text = f"Restamped {len(ids)} revision(s) in {label}: {', '.join(ids) or '(none)'}\n"
    return output.Result("restamp", {"restamped": ids}, text, label)


def run(args: argparse.Namespace) -> None:
    """Run `restamp` and print its text output."""
    output.emit_result(execute(args), "text", [])
