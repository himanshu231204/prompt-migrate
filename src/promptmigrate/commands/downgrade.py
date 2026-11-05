"""`downgrade`: revert applied revisions in an environment, to -1, base or a target revision."""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import apply, plan, revisions, store


def downgrade(project_dir: Path, env: str, target: str = "-1") -> list[str]:
    env = store.resolve_environment(project_dir, env)
    revisions_ = revisions.load_revisions(project_dir)
    with store.connect_write(project_dir, env) as db:
        db.execute("BEGIN IMMEDIATE")
        applied_count = apply._verify(db, revisions_)
        target_count = plan.downgrade_count(revisions_, applied_count, target)
        reversed_revisions = plan.downgrade_steps(revisions_, applied_count, target_count)
        apply.migrate(db, reversed_revisions, backward=True)
    store.adopt_environments(project_dir)
    return [r.revision for r in reversed_revisions]


def run(args: argparse.Namespace) -> None:
    project_dir = Path(args.project)
    label = store.display_name(project_dir, args.env)
    ids = downgrade(project_dir, args.env, args.target)
    print(f"{label}: reverted {len(ids)} revision(s): {', '.join(ids) or '(nothing to revert)'}")
