"""Applied environment state: verify the ledger and rows against source history, and write revisions to them.

Callers own the connection and the transaction (store.connect_readonly / store.connect_write, BEGIN IMMEDIATE).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from . import protocol, revisions
from .errors import DriftError, IntegrityError, StorageError
from .protocol import canonical  # imported by name: tests patch apply.canonical to fail a write without touching same()


def _applied(db: sqlite3.Connection) -> list[tuple[str, str]]:
    return [(rid, checksum) for rid, checksum in db.execute(
        "SELECT revision, checksum FROM applied_revisions ORDER BY seq"
    ).fetchall()]


def _actual(db: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return {name: json.loads(config) for name, config in db.execute(
        "SELECT name, config FROM prompts"
    ).fetchall()}


def _verify(db: sqlite3.Connection, revisions_: list[revisions.Revision]) -> int:
    try:
        applied = _applied(db)
    except sqlite3.Error as exc:
        raise StorageError("Corrupt environment state") from exc
    if len(applied) > len(revisions_):
        raise IntegrityError("Environment contains more applied revisions than source history")
    for index, (rid, checksum) in enumerate(applied):
        source = revisions_[index]
        if rid != source.revision:
            raise IntegrityError(f"Applied revisions diverge from source history at index {index}")
        if checksum != source.checksum:
            raise IntegrityError(f"Migration file was modified after apply: {rid}")
    expected = revisions.replay_revisions(revisions_[:len(applied)])
    try:
        actual = _actual(db)
    except (sqlite3.Error, ValueError, TypeError, RecursionError) as exc:
        raise StorageError("Corrupt environment state") from exc
    names = sorted(name for name in actual.keys() | expected.keys()
                   if not protocol.same(actual.get(name), expected.get(name)))
    if names:
        raise DriftError(f"Environment drift detected for prompts: {', '.join(names)}")
    return len(applied)


def migrate(db: sqlite3.Connection, steps: list[revisions.Revision], *, backward: bool = False) -> None:
    """Write each revision's rows and ledger entry in order, re-checking every precondition as it goes.

    Forward steps write each `after` and append to the ledger; backward steps (already in reverse order) write each
    `before` and remove the ledger row.
    """
    state = _actual(db)
    for r in steps:
        revisions._apply_changes(state, r, backward=backward)
        for name, change in r.changes.items():
            value = change["before"] if backward else change["after"]
            if value is None:
                db.execute("DELETE FROM prompts WHERE name=?", (name,))
            else:
                db.execute(
                    "INSERT INTO prompts(name, config) VALUES(?, ?) "
                    "ON CONFLICT(name) DO UPDATE SET config=excluded.config",
                    (name, canonical(value)),
                )
        if backward:
            db.execute("DELETE FROM applied_revisions WHERE revision=?", (r.revision,))
        else:
            db.execute(
                "INSERT INTO applied_revisions(revision, checksum, applied_at) VALUES(?, ?, ?)",
                (r.revision, r.checksum, datetime.now(timezone.utc).isoformat()),
            )
