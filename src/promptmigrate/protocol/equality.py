"""Canonical JSON text and equality by it."""

from __future__ import annotations

import json
from typing import Any


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def same(a: Any, b: Any) -> bool:
    """Equality by canonical JSON, so 1, 1.0 and true are pairwise distinct (Python's == conflates them)."""
    return canonical(a) == canonical(b)
