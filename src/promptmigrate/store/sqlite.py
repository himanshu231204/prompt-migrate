"""Environment SQLite state: database paths and the read-only and read/write connection lifecycles.

Connection helpers accept the canonical environment name; the migration layer owns BEGIN IMMEDIATE and replay.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
from urllib.parse import quote

from .. import project, protocol
from ..errors import StorageError
from . import lock


def _is_linklike(path: Path) -> bool:
    if path.is_symlink():
        return True
    if os.name == "nt":
        try:
            return bool(path.stat(follow_symlinks=False).st_file_attributes & 0x400)
        except FileNotFoundError:
            return False
    return False


def _states_dir(project_dir: Path) -> Path:
    path = project.require_init(project_dir) / "states"
    if _is_linklike(path):
        raise StorageError("Invalid environment state: states directory is a symbolic link or junction")
    if path.exists() and not path.is_dir():
        raise StorageError("Invalid environment state: states path is not a directory")
    return path


def _sqlite_uri(path: Path) -> str:
    """Build a read-only SQLite URI without treating a Windows UNC host as authority."""
    if path.drive.startswith("\\\\"):
        return "file://" + quote(path.as_posix(), safe="/") + "?mode=ro"
    return path.as_uri() + "?mode=ro"


def _wal_mode(path: Path) -> bool:
    try:
        with path.open("rb") as database:
            header = database.read(20)
    except OSError as exc:
        raise StorageError(f"Cannot inspect environment state: {exc}") from exc
    return header.startswith(b"SQLite format 3\0") and len(header) >= 20 and 2 in header[18:20]


def _db_path(project_dir: Path, env: str) -> Path:
    protocol.rules.validate_environment_name(env)
    path = _states_dir(project_dir) / f"{env}.sqlite3"
    if _is_linklike(path):
        raise StorageError(f"Invalid environment state {env!r}: database path is a symbolic link")
    return path


@contextmanager
def connect_readonly(project_dir: Path, env: str) -> Iterator[sqlite3.Connection | None]:
    """Yield base state for an absent DB, otherwise a checked, read-only connection."""
    path = _db_path(project_dir, env)
    if not path.exists():
        if _is_linklike(path):
            raise StorageError(f"Invalid environment state {env!r}: database path is a dangling symbolic link")
        yield None
        return
    connection = None
    try:
        try:
            if _wal_mode(path):
                raise StorageError(f"Invalid environment state {env!r}: WAL journal mode is unsupported for read-only inspection")
            connection = sqlite3.connect(_sqlite_uri(path), uri=True, timeout=10)
            # One read transaction for the whole inspection: the ledger and prompts must come from the same snapshot,
            # or a concurrent upgrade committing between the two reads would look like drift.
            connection.execute("BEGIN")
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"applied_revisions", "prompts"} <= tables:
                raise StorageError(f"Invalid environment state {env!r}: missing required tables")
        except sqlite3.Error as exc:
            raise StorageError(f"Cannot read environment state {env!r}: {exc}") from exc
        yield connection
    finally:
        if connection is not None:
            connection.close()


@contextmanager
def connect_write(project_dir: Path, env: str) -> Iterator[sqlite3.Connection]:
    """Initialize writable storage, commit on success, roll back on error, always close."""
    connection = None
    with lock._project_lock(project_dir):
        path = _db_path(project_dir, env)
        path.parent.mkdir(exist_ok=True)
        existed = path.exists()
        connection = None
        try:
            connection = sqlite3.connect(path, timeout=10)
            connection.execute("PRAGMA busy_timeout=10000")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            if existed:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"applied_revisions", "prompts"} <= tables:
                    raise StorageError(f"Invalid environment state {env!r}: missing required tables")
            else:
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS applied_revisions (
                        seq INTEGER PRIMARY KEY AUTOINCREMENT,
                        revision TEXT UNIQUE NOT NULL,
                        checksum TEXT NOT NULL,
                        applied_at TEXT NOT NULL
                    )
                """)
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS prompts (
                        name TEXT PRIMARY KEY,
                        config TEXT NOT NULL
                    )
                """)
            connection.commit()
        except BaseException:
            try:
                if connection is not None:
                    try:
                        connection.rollback()
                    finally:
                        connection.close()
            finally:
                if not existed:
                    for suffix in ("", "-wal", "-shm"):
                        Path(f"{path}{suffix}").unlink(missing_ok=True)
            raise
        assert connection is not None
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
