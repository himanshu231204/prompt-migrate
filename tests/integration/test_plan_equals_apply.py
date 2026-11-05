"""Property: for random histories, positions and targets, `plan` predicts exactly what upgrade/downgrade apply."""
import tempfile
from contextlib import closing
from pathlib import Path

from hypothesis import given, settings, strategies as st

from pmtest import pm_dir, tree_snapshot, write_revision
from promptmigrate import core, store

NAMES = ["a", "b", "c"]


def config(n):
    return {"messages": [{"role": "system", "content": f"v{n}"}]}


@st.composite
def histories(draw):
    """A valid linear history: each change's `before` equals the replayed state."""
    state, result, counter = {}, [], 0
    for _ in range(draw(st.integers(1, 5))):
        picked = draw(st.lists(st.sampled_from(NAMES), min_size=1, max_size=2, unique=True))
        changes = {}
        for name in picked:
            counter += 1
            if name not in state:
                action = "create"
            else:
                action = draw(st.sampled_from(["update", "delete"]))
            before = state.get(name)
            after = None if action == "delete" else config(counter)
            changes[name] = {"before": before, "after": after}
            if after is None:
                state.pop(name)
            else:
                state[name] = after
        result.append(changes)
    return result


def rows(project, env="dev"):
    with store.connect_readonly(project, env) as db:
        return {} if db is None else core._actual(db)


@settings(max_examples=60, derandomize=True, deadline=None)
@given(data=st.data(), history=histories())
def test_plan_equals_apply(data, history):
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        core.init(project)
        ids = []
        for index, changes in enumerate(history):
            rid = f"{index + 1:012x}"
            write_revision(project, rid, ids[-1] if ids else None, changes)
            ids.append(rid)
        applied = data.draw(st.integers(0, len(ids)))
        if applied:
            core.upgrade(project, "dev", ids[applied - 1])
        target = data.draw(st.sampled_from(["head", "base", "-1", *ids]))

        before_tree, before_rows = tree_snapshot(project), rows(project)
        planned = core.plan(project, "dev", target)
        assert tree_snapshot(project) == before_tree  # plan wrote nothing

        steps = [s.revision for s in planned.steps]
        if planned.direction == "upgrade":
            actual = core.upgrade(project, "dev", target)
        else:  # downgrade, or a no-op that either command leaves alone
            actual = core.downgrade(project, "dev", target) if target in ("-1", "base") or planned.direction == "downgrade" \
                else core.upgrade(project, "dev", target)
        assert steps == actual

        after_rows = rows(project)
        changed = {n for n in before_rows.keys() | after_rows.keys() if before_rows.get(n) != after_rows.get(n)}
        planned_names = {name for s in planned.steps for name, _ in s.changes}
        assert changed <= planned_names
        if len(steps) == 1:
            assert changed == planned_names
