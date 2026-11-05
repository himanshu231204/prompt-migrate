"""`plan`: read-only preview of what `upgrade` or `downgrade` would do to an environment."""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import apply, revisions, store
from .. import plan as planning
from ..plan import MigrationPlan


def plan(project_dir: Path, env: str, target: str = "head") -> MigrationPlan:
    """Resolve `target` against the environment's verified applied state. Writes nothing."""
    env = store.resolve_environment(project_dir, env)
    revisions_ = revisions.load_revisions(project_dir)
    if target not in ("head", "-1", "base"):
        planning.upgrade_count(revisions_, target)  # like `upgrade`, reject an unknown id before reading the env
    with store.connect_readonly(project_dir, env) as db:
        applied = apply._verify(db, revisions_) if db is not None else 0
    return planning.build(revisions_, applied, target)


def render(label: str, result: MigrationPlan) -> str:
    """The plan as the text `promptmigrate plan` prints."""
    if result.direction == "none":
        return f"{label}: nothing to do (at {result.start or 'base'})\n"
    verb = "apply" if result.direction == "upgrade" else "revert"
    lines = [f"{label}: would {verb} {len(result.steps)} revision(s) ({result.start or 'base'} -> {result.target or 'base'})"]
    for step in result.steps:
        lines.append(f"  {step.revision}")
        lines.extend(f"    {name} ({kind})" for name, kind in step.changes)
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> None:
    """Print the plan for `args.env` and `args.target`."""
    project_dir = Path(args.project)
    label = store.display_name(project_dir, args.env)
    print(render(label, plan(project_dir, args.env, args.target)), end="")
