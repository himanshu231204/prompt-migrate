"""PR 8 (cycle 2): v1 integrity against an environment ledger (ADR-026, I16).

An env that applied a v1 revision still verifies after the file is re-saved with other line endings, indentation or
key order, and fails closed after any value edit. v0 and v1 revisions can share one history; each ledger row keeps the
checksum of its own format.
"""
import json
import re
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from pmtest import FIXTURES, install_fixture, pm_dir, swap_line_endings, write_revision
from promptmigrate import core
from promptmigrate.core import check, downgrade, get_config, load_revisions, upgrade
from promptmigrate.errors import IntegrityError

A, B, C = "a" * 12, "b" * 12, "c" * 12
CFG1 = {"messages": [{"role": "system", "content": "Answer briefly."}]}
CFG2 = {"messages": [{"role": "system", "content": "Answer briefly and cite sources."}]}
CFG3 = {"messages": [{"role": "system", "content": "Answer briefly, cite sources, stay polite."}]}
PINS = json.loads((FIXTURES / "v0_checksums.json").read_text(encoding="utf-8"))


def ledger(project, env="dev"):
    with closing(sqlite3.connect(pm_dir(project) / "states" / f"{env}.sqlite3")) as db:
        return db.execute("SELECT revision, checksum FROM applied_revisions ORDER BY seq").fetchall()


def reversed_keys(value):
    if isinstance(value, dict):
        return {key: reversed_keys(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [reversed_keys(item) for item in value]
    return value


@pytest.fixture
def applied_v1(project):
    path = write_revision(project, A, None, {"assistant": {"before": None, "after": CFG1}},
                          message="Create assistant", format_version=1)
    upgrade(project, "dev")
    return path


def rewrite(path, **dumps_kwargs):
    path.write_bytes(json.dumps(json.loads(path.read_bytes()), **dumps_kwargs).encode("utf-8"))


RESAVES = {
    "line-endings": swap_line_endings,
    "reindent": lambda path: rewrite(path, indent=4),
    "compact": lambda path: rewrite(path, separators=(",", ":")),
    "reorder-keys": lambda path: path.write_bytes(
        json.dumps(reversed_keys(json.loads(path.read_bytes())), indent=2).encode("utf-8")),
}


@pytest.mark.parametrize("resave", sorted(RESAVES))
def test_resaved_v1_revision_still_verifies(project, applied_v1, resave):
    before = applied_v1.read_bytes()
    RESAVES[resave](applied_v1)
    assert applied_v1.read_bytes() != before
    assert check(project, "dev", require_head=True) == (1, 1)
    assert get_config(project, "dev", "assistant") == CFG1
    assert downgrade(project, "dev", "base") == [A]


EDITS = {
    "message": lambda item: item.update(message="Edited after apply"),
    "created_at": lambda item: item.update(created_at="2026-10-30T00:00:01+00:00"),
    "changes-after": lambda item: item["changes"]["assistant"]["after"]["messages"][0].update(content="Edited."),
    "format_version-removed": lambda item: item.pop("format_version"),
}


@pytest.mark.parametrize("edit", sorted(EDITS))
def test_value_edit_of_applied_v1_revision_is_tamper(project, applied_v1, edit):
    item = json.loads(applied_v1.read_bytes())
    EDITS[edit](item)
    applied_v1.write_text(json.dumps(item, indent=2), encoding="utf-8")
    with pytest.raises(IntegrityError, match=f"^Migration file was modified after apply: {A}$"):
        check(project, "dev")


# --- mixed history: v0 -> v0 -> v1 ----------------------------------------------------------------

@pytest.fixture
def mixed(project):
    install_fixture(project, "basic", "v0_frozen")  # A (create) -> B (update), both v0
    write_revision(project, C, B, {"assistant": {"before": CFG2, "after": CFG3}}, message="Be polite",
                   format_version=1)
    return project


def test_mixed_chain_upgrades_checks_and_downgrades(mixed):
    assert [r.format_version for r in load_revisions(mixed)] == [0, 0, 1]
    assert upgrade(mixed, "dev") == [A, B, C]
    rows = ledger(mixed)
    assert rows[:2] == [(A, PINS["v0_frozen/basic/aaaaaaaaaaaa_create.json"]),
                        (B, PINS["v0_frozen/basic/bbbbbbbbbbbb_update.json"])]
    assert rows[2][0] == C and re.fullmatch(r"v1:[0-9a-f]{64}", rows[2][1])
    assert check(mixed, "dev", require_head=True) == (3, 3)
    assert get_config(mixed, "dev", "assistant") == CFG3
    assert downgrade(mixed, "dev", "base") == [C, B, A]
    assert check(mixed, "dev") == (0, 3)


def test_mixed_chain_line_endings_matter_only_for_v0(mixed):
    upgrade(mixed, "dev")
    versions = pm_dir(mixed) / "versions"
    swap_line_endings(versions / f"{C}.json")
    assert check(mixed, "dev") == (3, 3)
    swap_line_endings(versions / f"{A}_create.json")
    with pytest.raises(IntegrityError) as caught:
        check(mixed, "dev")
    assert str(caught.value) == (f"Migration file was modified after apply: {A} (line endings only; "
                                 "run `promptmigrate restamp --env dev` to accept)")


# --- I16 property: any re-serialization of the same object keeps the v1 checksum -----------------

def shuffled(value, rnd):
    if isinstance(value, dict):
        keys = list(value)
        rnd.shuffle(keys)
        return {key: shuffled(value[key], rnd) for key in keys}
    if isinstance(value, list):
        return [shuffled(item, rnd) for item in value]
    return value


@settings(max_examples=50, derandomize=True, deadline=None)
@given(rnd=st.randoms(use_true_random=False), indent=st.sampled_from([None, 0, 1, 2, 4, "\t"]),
       crlf=st.booleans(), ascii_only=st.booleans())
def test_v1_checksum_survives_any_reserialization(rnd, indent, crlf, ascii_only):
    item = {"format_version": 1, "revision": A, "down_revision": None, "message": "Créer l'assistant",
            "created_at": "2026-10-30T00:00:00+00:00",
            "changes": {"assistant": {"before": None, "after": {**CFG1, "parameters": {"temperature": 0.5}}},
                        "helper": {"before": None, "after": CFG2}}}
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        core.init(project)
        path = pm_dir(project) / "versions" / f"{A}.json"
        path.write_bytes((json.dumps(item, indent=2) + "\n").encode("utf-8"))
        [original] = load_revisions(project)
        text = json.dumps(shuffled(item, rnd), indent=indent, ensure_ascii=ascii_only)
        path.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))
        [resaved] = load_revisions(project)
        assert resaved.checksum == original.checksum
