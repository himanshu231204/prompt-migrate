"""`upgrade`: apply pending revisions to an environment, up to head or a target revision."""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import apply, output, revisions, store
from ..errors import TargetError


def upgrade(project_dir: Path, env: str, target: str = "head") -> list[str]:
    env = store.resolve_environment(project_dir, env)
    revisions_ = revisions.load_revisions(project_dir)
    targets = [r.revision for r in revisions_]
    if target != "head" and target not in targets:
        raise TargetError(f"Unknown target revision: {target}")
    target_count = len(revisions_) if target == "head" else targets.index(target) + 1
    with store.connect_write(project_dir, env) as db:
        db.execute("BEGIN IMMEDIATE")
        applied_count = apply._verify(db, revisions_)
        if applied_count > target_count:
            raise TargetError("Upgrade target is behind current revision; use downgrade")
        apply.migrate(db, revisions_[applied_count:target_count])
    store.adopt_environments(project_dir)
    return targets[applied_count:target_count]


def execute(args: argparse.Namespace) -> output.Result:
    """Run `upgrade` and return its text and JSON result."""
    project_dir = Path(args.project)
    label = store.display_name(project_dir, args.env)
    ids = upgrade(project_dir, args.env, args.target)
    data = {"direction": "up", "target": args.target, "revisions": ids}
    text = f"{label}: applied {len(ids)} revision(s): {', '.join(ids) or '(already current)'}\n"
    return output.Result("upgrade", data, text, label)


def run(args: argparse.Namespace) -> None:
    """Run `upgrade` and print its text output."""
    output.emit_result(execute(args), "text", [])
