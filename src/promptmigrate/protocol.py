"""Source-file protocol: strict JSON loading, limits and config validation."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .errors import SchemaError

# Module globals, read at call time so tests can patch them.
MAX_DRAFT_BYTES = 1 << 20  # 1 MiB per draft file
MAX_REVISION_BYTES = 16 << 20  # 16 MiB per revision file
MAX_CONFIG_DEPTH = 64  # nesting depth of one config: a draft's root, or one before/after value

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


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise _StrictJSONError("number out of range")
    return value


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
    except SchemaError:
        raise
    except RuntimeError as exc:
        # Path.resolve() raises an untyped RuntimeError for a symlink loop on Python 3.10-3.12.
        raise SchemaError(f"{prefix} {path.name}: symlink loop") from exc
    except OSError as exc:
        raise SchemaError(f"{prefix} {path.name}: {exc}") from exc
    if kind == "revision" and len(raw) > MAX_REVISION_BYTES:
        rules.append("revision-size")
    try:
        # Drafts are decoded as UTF-8 text, so a BOM is rejected; revisions are parsed from bytes, so a BOM is
        # accepted. Both are unchanged from the starter (spec §3). A UnicodeDecodeError is a ValueError.
        document = raw.decode("utf-8") if kind == "draft" else raw
        value = json.loads(
            document, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant, parse_float=_finite_float
        )
    except RecursionError as exc:
        raise SchemaError(f"{prefix} {path.name}: nested too deep to parse") from exc
    except ValueError as exc:
        raise SchemaError(f"{prefix} {path.name}: {exc}") from exc
    return value, raw, rules


RESERVED_TYPES: dict[str, tuple[type, ...]] = {
    "model": (str,),
    "parameters": (dict,),
    "tools": (list,),
    "response_schema": (dict, type(None)),
}

_NAME = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{0,127}")


def validate_config(name: str, value: Any) -> None:
    """Tier-A config rules, enforced everywhere."""
    if not _NAME.fullmatch(name):
        raise SchemaError(f"Invalid prompt name: {name!r}")
    if not isinstance(value, dict):
        raise SchemaError(f"Prompt {name!r} must contain a JSON object")
    # Minimal structural validation; intentionally no framework-specific constraints.
    if "messages" in value:
        msgs = value["messages"]
        if not isinstance(msgs, list) or any(
            not isinstance(msg, dict)
            or not isinstance(msg.get("role"), str)
            or not isinstance(msg.get("content"), str)
            for msg in msgs
        ):
            raise SchemaError(f"Prompt {name!r} has invalid messages")


def config_depth(value: Any) -> int:
    """Nesting depth of JSON containers: a scalar is 0, {} or [] is 1. Iterative, so deep input can't overflow."""
    deepest, stack = 0, [(value, 1)]
    while stack:
        item, depth = stack.pop()
        if isinstance(item, dict):
            children = list(item.values())
        elif isinstance(item, list):
            children = item
        else:
            continue
        deepest = max(deepest, depth)
        stack.extend((child, depth + 1) for child in children)
    return deepest


def config_violations(name: str, value: dict[str, Any]) -> list[str]:
    """Tier-B rules for one config, as rule ids plus subject. Enforced on new content, warned about in history."""
    found = []
    if config_depth(value) > MAX_CONFIG_DEPTH:
        found.append(f"config-depth {name}")
    for field, types in RESERVED_TYPES.items():
        if field in value and not isinstance(value[field], types):
            found.append(f"reserved-field-type {name}.{field}")
    return found


def case_collisions(names: Iterable[str]) -> list[str]:
    """Each group of names that are equal case-insensitively, as 'A/a'."""
    groups: dict[str, list[str]] = {}
    for name in names:
        groups.setdefault(name.lower(), []).append(name)
    return sorted("/".join(sorted(group)) for group in groups.values() if len(group) > 1)
