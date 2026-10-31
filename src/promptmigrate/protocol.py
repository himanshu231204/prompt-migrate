"""Source-file protocol: strict JSON loading, limits and config validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import SchemaError

# Module globals, read at call time so tests can patch them.
MAX_DRAFT_BYTES = 1 << 20  # 1 MiB per draft file
MAX_REVISION_BYTES = 16 << 20  # 16 MiB per revision file

_PREFIX = {"draft": "Invalid JSON draft", "revision": "Unreadable migration"}


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def same(a: Any, b: Any) -> bool:
    """Equality by canonical JSON, so 1, 1.0 and true are pairwise distinct (Python's == conflates them)."""
    return canonical(a) == canonical(b)


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


def load_json(path: Path, *, kind: str, root: Path) -> tuple[Any, bytes, list[str]]:
    """Strictly read one source file of `kind` ("draft" or "revision") that lives under `root` (.promptmigrate/).

    Returns (value, raw bytes, tier-B file rules). Tier-A problems always raise SchemaError. A draft also raises on the
    tier-B file rules (symlink, size); an existing revision returns them so that the caller can warn.
    """
    prefix = _PREFIX[kind]
    rules: list[str] = []
    try:
        if not path.resolve().is_relative_to(root.resolve()):
            raise SchemaError(f"{prefix} {path.name}: resolves outside .promptmigrate/")
        if path.is_symlink():
            if kind == "draft":
                raise SchemaError(f"{prefix} {path.name}: drafts must not be symlinks")
            rules.append("symlink")
        size = path.stat().st_size
        if kind == "draft" and size > MAX_DRAFT_BYTES:
            raise SchemaError(f"{prefix} {path.name}: {size} bytes exceeds the {MAX_DRAFT_BYTES}-byte limit")
        raw = path.read_bytes()
    except OSError as exc:
        raise SchemaError(f"{prefix} {path.name}: {exc}") from exc
    if kind == "revision" and len(raw) > MAX_REVISION_BYTES:
        rules.append("revision-size")
    try:
        # Drafts are decoded as UTF-8 text, so a BOM is rejected; revisions are parsed from bytes, so a BOM is
        # accepted. Both are unchanged from the starter (spec §3). A UnicodeDecodeError is a ValueError.
        document = raw.decode("utf-8") if kind == "draft" else raw
        value = json.loads(document, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
    except RecursionError as exc:
        raise SchemaError(f"{prefix} {path.name}: nested too deep to parse") from exc
    except ValueError as exc:
        raise SchemaError(f"{prefix} {path.name}: {exc}") from exc
    return value, raw, rules
