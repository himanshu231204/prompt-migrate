"""Config validation: tier-A rules enforced everywhere, tier-B rules enforced on new content."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from ..errors import SchemaError
from . import limits

RESERVED_TYPES: dict[str, tuple[type, ...]] = {
    "model": (str,),
    "parameters": (dict,),
    "tools": (list,),
    "response_schema": (dict, type(None)),
}

_NAME = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{0,127}")
_ENV_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")


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
    if config_depth(value) > limits.MAX_CONFIG_DEPTH:
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


def validate_environment_name(name: str) -> None:
    if not isinstance(name, str) or not _ENV_NAME.fullmatch(name):
        raise SchemaError("Environment must be alphanumeric, starting with a letter")
    if re.fullmatch(r"(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", name):
        raise SchemaError("Environment name is reserved on Windows")
