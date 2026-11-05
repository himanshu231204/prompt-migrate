"""`downgrade`: revert applied revisions in an environment, to -1, base or a target revision."""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import apply, output, revisions, store
from ..errors import TargetError


def downgrade(project_dir: Path, env: str, target: str = "-1") -> list[str]:
    env = store.resolve_environment(project_dir, env)
    revisions_ = revisions.load_revisions(project_dir)
    targets = [r.revision for r in revisions_]
    with store.connect_write(project_dir, env) as db:
        db.execute("BEGIN IMMEDIATE")
        applied_count = apply._verify(db, revisions_)
        if target == "-1":
            target_count = max(0, applied_count - 1)
        elif target == "base":
            target_count = 0
        elif target in targets:
            target_count = targets.index(target) + 1
        else:
            raise TargetError(f"Unknown target revision: {target}")
        if target_count > applied_count:
            raise TargetError("Downgrade target is ahead of current revision; use upgrade")
        reversed_revisions = list(reversed(revisions_[target_count:applied_count]))
        apply.migrate(db, reversed_revisions, backward=True)
    store.adopt_environments(project_dir)
    return [r.revision for r in reversed_revisions]


def execute(args: argparse.Namespace) -> output.Result:
    project_dir = Path(args.project)
    label = store.display_name(project_dir, args.env)
    ids = downgrade(project_dir, args.env, args.target)
    data = {"direction": "down", "target": args.target, "revisions": ids}
    text = f"{label}: reverted {len(ids)} revision(s): {', '.join(ids) or '(nothing to revert)'}\n"
    return output.Result("downgrade", data, text, label)


def run(args: argparse.Namespace) -> None:
    output.emit_result(execute(args), "text", [])
