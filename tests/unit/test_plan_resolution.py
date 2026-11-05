"""plan.py: pure target resolution shared by upgrade, downgrade and plan."""
from pathlib import Path

import pytest

from promptmigrate import plan
from promptmigrate.errors import TargetError
from promptmigrate.revisions import Revision

CFG = {"messages": [{"role": "system", "content": "A"}]}
CFG2 = {"messages": [{"role": "system", "content": "B"}]}


def rev(rid, parent, changes):
    return Revision(rid, parent, "m", "2026-10-30T00:00:00+00:00", changes, "c" * 64, Path(rid + ".json"))


HISTORY = [
    rev("a" * 12, None, {"x": {"before": None, "after": CFG}, "y": {"before": None, "after": CFG}}),
    rev("b" * 12, "a" * 12, {"x": {"before": CFG, "after": CFG2}}),
    rev("c" * 12, "b" * 12, {"y": {"before": CFG, "after": None}}),
]
A, B, C = (r.revision for r in HISTORY)


def ids(steps):
    return [s.revision for s in steps]


def test_upgrade_head_from_base_plans_every_revision_in_order():
    result = plan.build(HISTORY, 0, "head")
    assert (result.direction, result.start, result.target) == ("upgrade", None, C)
    assert ids(result.steps) == [A, B, C]


def test_upgrade_to_revision_stops_at_it():
    result = plan.build(HISTORY, 0, B)
    assert ids(result.steps) == [A, B] and result.target == B


def test_upgrade_from_middle():
    result = plan.build(HISTORY, 1, "head")
    assert (result.start, ids(result.steps)) == (A, [B, C])


def test_downgrade_minus_one_reverts_newest_first():
    result = plan.build(HISTORY, 3, "-1")
    assert (result.direction, result.start, result.target) == ("downgrade", C, B)
    assert ids(result.steps) == [C]


def test_downgrade_base_reverts_everything_newest_first():
    result = plan.build(HISTORY, 3, "base")
    assert ids(result.steps) == [C, B, A] and result.target is None


def test_downgrade_to_earlier_revision():
    result = plan.build(HISTORY, 3, A)
    assert (result.direction, ids(result.steps), result.target) == ("downgrade", [C, B], A)


@pytest.mark.parametrize("applied, target", [(3, "head"), (2, B), (0, "base"), (0, "-1")])
def test_nothing_to_do(applied, target):
    result = plan.build(HISTORY, applied, target)
    assert result.direction == "none" and result.steps == ()


def test_unknown_target_message_matches_upgrade_and_downgrade():
    with pytest.raises(TargetError, match="^Unknown target revision: zzz$"):
        plan.build(HISTORY, 1, "zzz")


def test_upgrade_resolver_rejects_target_behind_current():
    with pytest.raises(TargetError, match="Upgrade target is behind current revision; use downgrade"):
        plan.upgrade_steps(HISTORY, 3, plan.upgrade_count(HISTORY, A))


def test_downgrade_resolver_rejects_target_ahead_of_current():
    with pytest.raises(TargetError, match="Downgrade target is ahead of current revision; use upgrade"):
        plan.downgrade_steps(HISTORY, 1, plan.downgrade_count(HISTORY, 1, C))


def test_downgrade_resolver_unknown_target():
    with pytest.raises(TargetError, match="^Unknown target revision: zzz$"):
        plan.downgrade_count(HISTORY, 1, "zzz")


def test_change_kinds_forward():
    steps = plan.build(HISTORY, 0, "head").steps
    assert steps[0].changes == (("x", "create"), ("y", "create"))
    assert steps[1].changes == (("x", "update"),)
    assert steps[2].changes == (("y", "delete"),)


def test_change_kinds_backward_are_inverted():
    steps = plan.build(HISTORY, 3, "base").steps
    assert steps[0].changes == (("y", "create"),)
    assert steps[1].changes == (("x", "update"),)
    assert steps[2].changes == (("x", "delete"), ("y", "delete"))


def test_names_are_sorted_for_determinism():
    r = rev(A, None, {"zeta": {"before": None, "after": CFG}, "alpha": {"before": None, "after": CFG}})
    assert [n for n, _ in plan.build([r], 0, "head").steps[0].changes] == ["alpha", "zeta"]


def test_plan_is_immutable():
    result = plan.build(HISTORY, 0, "head")
    with pytest.raises(Exception):
        result.direction = "x"
