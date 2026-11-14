"""Applied environment state: verify the ledger and rows against source history, and write revisions to them.

Callers own the connection and the transaction (store.connect_readonly / store.connect_write, BEGIN IMMEDIATE).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
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


def _ledger_rows(db: sqlite3.Connection, revisions_: list[revisions.Revision]) -> Iterator[tuple[revisions.Revision, str]]:
    """Yield each ledger row as (source revision, stored checksum), in order, while its id matches source history."""
    try:
        applied = _applied(db)
    except sqlite3.Error as exc:
        raise StorageError("Corrupt environment state") from exc
    if len(applied) > len(revisions_):
        raise IntegrityError("Environment contains more applied revisions than source history")
    for index, (rid, checksum) in enumerate(applied):
        if rid != revisions_[index].revision:
            raise IntegrityError(f"Applied revisions diverge from source history at index {index}")
        yield revisions_[index], checksum


def _verify(db: sqlite3.Connection, revisions_: list[revisions.Revision], env: str | None = None) -> int:
    count = 0
    for source, checksum in _ledger_rows(db, revisions_):
        if checksum != source.checksum:
            if checksum in source.line_ending_checksums:
                # Diagnosis only: the row still fails closed until `restamp` accepts it (ADR-027).
                raise IntegrityError(f"Migration file was modified after apply: {source.revision} (line endings only; "
                                     f"run `promptmigrate restamp --env {env or '<env>'}` to accept)")
            raise IntegrityError(f"Migration file was modified after apply: {source.revision}")
        count += 1
    expected = revisions.replay_revisions(revisions_[:count])
    try:
        actual = _actual(db)
    except (sqlite3.Error, ValueError, TypeError, RecursionError) as exc:
        raise StorageError("Corrupt environment state") from exc
    names = sorted(name for name in actual.keys() | expected.keys()
                   if not protocol.same(actual.get(name), expected.get(name)))
    if names:
        raise DriftError(f"Environment drift detected for prompts: {', '.join(names)}")
    return count


def line_ending_only(db: sqlite3.Connection, revisions_: list[revisions.Revision]) -> list[revisions.Revision]:
    """The applied v0 revisions whose ledger checksum matches their file only after a line-ending change (ADR-027).

    Any other mismatch, a v1 row included, raises the IntegrityError `_verify` would raise for it.
    """
    stale = []
    for source, checksum in _ledger_rows(db, revisions_):
        if checksum == source.checksum:
            continue
        if source.format_version != 0 or checksum not in source.line_ending_checksums:
            raise IntegrityError(f"Migration file was modified after apply: {source.revision}")
        stale.append(source)
    return stale


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
