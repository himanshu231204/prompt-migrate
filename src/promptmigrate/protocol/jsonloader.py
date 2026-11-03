"""Strict JSON loading of source files: duplicate keys, non-finite numbers, size limits, symlinks."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from ..errors import SchemaError
from . import limits

_PREFIX = {
    "draft": "Invalid JSON draft",
    "revision": "Unreadable migration",
    "allowlist": "Invalid secret allowlist",
    "environments": "Invalid environments file",
}


class _StrictJSONError(ValueError):
    pass


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise _StrictJSONError(f"duplicate key {key!r}")
        obj[key] = value
    return obj


def _reject_constant(name: str) -> Any:
    raise _StrictJSONError(f"non-finite number {name} is not allowed")


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise _StrictJSONError("number out of range")
    return value


def load_json(path: Path, *, kind: str, root: Path) -> tuple[Any, bytes, list[str]]:
    """Strictly read one source file under root (.promptmigrate/).

    Returns (value, raw bytes, tier-B file rules). Tier-A problems always raise SchemaError. Drafts, the allowlist,
    and the environment manifest raise on symlinks and size; an existing revision returns those rules so that the
    caller can warn.
    """
    prefix = _PREFIX[kind]
    rules: list[str] = []
    try:
        if not path.resolve().is_relative_to(root.resolve()):
            raise SchemaError(f"{prefix} {path.name}: resolves outside .promptmigrate/")
        if path.is_symlink():
            if kind == "draft":
                raise SchemaError(f"{prefix} {path.name}: drafts must not be symlinks")
            if kind in {"allowlist", "environments"}:
                raise SchemaError(f"{prefix} {path.name}: must not be a symlink")
            rules.append("symlink")
        size = path.stat().st_size
        limit = {
            "draft": limits.MAX_DRAFT_BYTES,
            "allowlist": limits.MAX_CONTROL_FILE_BYTES,
            "environments": limits.MAX_CONTROL_FILE_BYTES,
        }.get(kind)
        if limit is not None and size > limit:
            raise SchemaError(f"{prefix} {path.name}: {size} bytes exceeds the {limit}-byte limit")
        raw = path.read_bytes()
    except SchemaError:
        raise
    except RuntimeError as exc:
        # Path.resolve() raises an untyped RuntimeError for a symlink loop on Python 3.10-3.12.
        raise SchemaError(f"{prefix} {path.name}: symlink loop") from exc
    except OSError as exc:
        raise SchemaError(f"{prefix} {path.name}: {exc}") from exc
    if kind == "revision" and len(raw) > limits.MAX_REVISION_BYTES:
        rules.append("revision-size")
    try:
        # Drafts and control files are decoded as UTF-8 text, so a BOM is rejected; revisions are parsed from bytes,
        # so a BOM is accepted. Both are unchanged from the starter (spec §3). A UnicodeDecodeError is a ValueError.
        document = raw if kind == "revision" else raw.decode("utf-8")
        value = json.loads(
            document, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant, parse_float=_finite_float
        )
    except RecursionError as exc:
        raise SchemaError(f"{prefix} {path.name}: nested too deep to parse") from exc
    except ValueError as exc:
        raise SchemaError(f"{prefix} {path.name}: {exc}") from exc
    return value, raw, rules
