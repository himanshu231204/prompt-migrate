"""Pure migration planning: resolve a target against source history and the applied count. No I/O.

`upgrade`, `downgrade` and `plan` all resolve targets here, so a preview cannot disagree with what is applied.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import protocol
from .errors import TargetError
from .revisions import Revision


@dataclass(frozen=True)
class Step:
    """One revision to apply (or revert) and the config changes it makes, as sorted (name, kind) pairs."""
    revision: str
    changes: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class MigrationPlan:
    """direction is "upgrade", "downgrade" or "none"; start and target are revision ids, None meaning base."""
    direction: str
    start: str | None
    target: str | None
    steps: tuple[Step, ...]


def _unknown(target: str) -> TargetError:
    return TargetError(f"Unknown target revision: {target}")


def upgrade_count(revisions: list[Revision], target: str) -> int:
    ids = [r.revision for r in revisions]
    if target == "head":
        return len(ids)
    if target not in ids:
        raise _unknown(target)
    return ids.index(target) + 1


def upgrade_steps(revisions: list[Revision], applied: int, target_count: int) -> list[Revision]:
    if applied > target_count:
        raise TargetError("Upgrade target is behind current revision; use downgrade")
    return revisions[applied:target_count]


def downgrade_count(revisions: list[Revision], applied: int, target: str) -> int:
    ids = [r.revision for r in revisions]
    if target == "-1":
        return max(0, applied - 1)
    if target == "base":
        return 0
    if target in ids:
        return ids.index(target) + 1
    raise _unknown(target)


def downgrade_steps(revisions: list[Revision], applied: int, target_count: int) -> list[Revision]:
    if target_count > applied:
        raise TargetError("Downgrade target is ahead of current revision; use upgrade")
    return list(reversed(revisions[target_count:applied]))


def _kind(old, new) -> str:
    if old is None:
        return "create" if new is not None else "unchanged"
    if new is None:
        return "delete"
    return "unchanged" if protocol.same(old, new) else "update"


def _step(revision: Revision, backward: bool) -> Step:
    old, new = ("after", "before") if backward else ("before", "after")
    return Step(revision.revision, tuple(
        (name, _kind(change[old], change[new])) for name, change in sorted(revision.changes.items())
    ))


def _id(revisions: list[Revision], count: int) -> str | None:
    return revisions[count - 1].revision if count else None


def build(revisions: list[Revision], applied: int, target: str) -> MigrationPlan:
    """Plan the move from `applied` revisions to `target`; the direction follows from where the target lies.

    `head` and later revisions upgrade; `-1`, `base` and earlier revisions downgrade; the current position is a no-op.
    """
    if target == "head":
        count = len(revisions)
    elif target in ("-1", "base"):
        count = downgrade_count(revisions, applied, target)
    else:
        count = upgrade_count(revisions, target)
    start = _id(revisions, applied)
    if count > applied:
        steps = tuple(_step(r, False) for r in upgrade_steps(revisions, applied, count))
        return MigrationPlan("upgrade", start, _id(revisions, count), steps)
    if count < applied:
        steps = tuple(_step(r, True) for r in downgrade_steps(revisions, applied, count))
        return MigrationPlan("downgrade", start, _id(revisions, count), steps)
    return MigrationPlan("none", start, start, ())
