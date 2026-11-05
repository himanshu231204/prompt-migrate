"""Output rendering and the error -> exit code table.

Commands build a `Result` (a JSON-safe `data` dict plus the exact text they print today) and know nothing about
formats. This module renders it as text or as one JSON envelope and owns the exit-code mapping, so a new command only
needs an `execute(args) -> Result`. Envelope schema: `promptmigrate.output/1` (docs/CLI_SPEC.md).
"""

from __future__ import annotations

import json
import sqlite3
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import errors, store

SCHEMA = "promptmigrate.output/1"
FORMATS = ("text", "json")

# Most specific class first: the first isinstance match wins. (class, exit code, JSON error name)
_TABLE: tuple[tuple[type[BaseException], int, str], ...] = (
    (errors.SchemaError, 3, "schema"),           # includes SecretDetectedError
    (errors.RevisionGraphError, 3, "schema"),
    (errors.DriftError, 4, "conflict"),
    (errors.IntegrityError, 4, "conflict"),
    (errors.MigrationConflictError, 4, "conflict"),
    (errors.StorageError, 5, "storage"),
    (sqlite3.Error, 5, "storage"),
    (OSError, 5, "storage"),
    (errors.MigrationError, 1, "error"),         # uninitialized, undeclared env, target, pending, anything else
)
HANDLED = (errors.MigrationError, OSError, sqlite3.Error)


@dataclass
class Result:
    """What a command produced: `text` is the exact stdout of text mode, `data` the JSON payload."""
    command: str
    data: dict[str, Any]
    text: str = ""
    env: str | None = None


@dataclass
class Warned:
    """A PromptMigrate warning as listed in JSON output."""
    category: str
    message: str


def exit_code_for(exc: BaseException) -> int:
    """The process exit code for a handled error (1, 3, 4 or 5)."""
    for cls, code, _name in _TABLE:
        if isinstance(exc, cls):
            return code
    raise TypeError(f"unhandled exception type: {type(exc).__name__}")


def error_name_for(exc: BaseException) -> str:
    """The `error.code` name used in the JSON envelope for a handled error."""
    for cls, _code, name in _TABLE:
        if isinstance(exc, cls):
            return name
    raise TypeError(f"unhandled exception type: {type(exc).__name__}")


def describe(args: Any) -> tuple[str, str | None]:
    """(command name, environment) of a parsed command line, for an error envelope; `env` has no --env of its own."""
    if getattr(args, "env_command", None):
        return f"env {args.env_command}", None
    env = getattr(args, "env", None)
    if env is not None:
        try:
            env = store.display_name(Path(args.project), env)
        except Exception:  # an unreadable manifest or invalid name was already reported; keep what was typed
            pass
    return args.command, env


def collect_warnings(caught: list[warnings.WarningMessage]) -> list[Warned]:
    """Each distinct PromptMigrate warning once, in first-seen order."""
    seen, result = set(), []
    for w in caught:
        if issubclass(w.category, errors.PromptMigrateWarning):
            key = (w.category, str(w.message))
            if key not in seen:
                seen.add(key)
                result.append(Warned(w.category.__name__, str(w.message)))
    return result


def _dump(doc: dict[str, Any]) -> str:
    """One JSON document on one line, newline-terminated; non-finite numbers are rejected."""
    return json.dumps(doc, ensure_ascii=True, allow_nan=False) + "\n"


def emit_result(result: Result, fmt: str, warned: list[Warned]) -> None:
    """Print a success. In text mode the warnings are the caller's business (stderr)."""
    if fmt == "json":
        sys.stdout.write(_dump({
            "schema": SCHEMA, "ok": True, "command": result.command, "env": result.env,
            "data": result.data, "warnings": [vars(w) for w in warned],
        }))
    else:
        sys.stdout.write(result.text)


def emit_error(exc: BaseException, fmt: str, command: str, env: str | None, warned: list[Warned]) -> int:
    """Print a handled error: `Error: …` on stderr in text mode, an envelope on stdout in JSON mode. Returns the code."""
    code = exit_code_for(exc)
    if fmt == "json":
        sys.stdout.write(_dump({
            "schema": SCHEMA, "ok": False, "command": command, "env": env,
            "error": {"code": error_name_for(exc), "exit_code": code, "message": str(exc)},
            "warnings": [vars(w) for w in warned],
        }))
    else:
        print(f"Error: {exc}", file=sys.stderr)
    return code
