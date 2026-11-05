"""`upgrade`: apply pending revisions to an environment, up to head or a target revision."""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import apply, plan, revisions, store


def upgrade(project_dir: Path, env: str, target: str = "head") -> list[str]:
    env = store.resolve_environment(project_dir, env)
    revisions_ = revisions.load_revisions(project_dir)
    target_count = plan.upgrade_count(revisions_, target)
    with store.connect_write(project_dir, env) as db:
        db.execute("BEGIN IMMEDIATE")
        applied_count = apply._verify(db, revisions_)
        steps = plan.upgrade_steps(revisions_, applied_count, target_count)
        apply.migrate(db, steps)
    store.adopt_environments(project_dir)
    return [r.revision for r in steps]


def run(args: argparse.Namespace) -> None:
    project_dir = Path(args.project)
    label = store.display_name(project_dir, args.env)
    ids = upgrade(project_dir, args.env, args.target)
    print(f"{label}: applied {len(ids)} revision(s): {', '.join(ids) or '(already current)'}")
