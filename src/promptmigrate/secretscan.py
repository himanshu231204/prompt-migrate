"""Heuristic secret detection, the fingerprinted allowlist, and output redaction. Pure functions; no I/O.

Detection reduces the chance of a secret entering a new revision or PromptMigrate output. It can miss secrets, and it
does nothing for secrets already in Git history, which must be rotated.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from .errors import SchemaError

VALUE_RULES: dict[str, re.Pattern[str]] = {
    "openai-anthropic-key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "aws-access-key-id": re.compile(r"AKIA[0-9A-Z]{16}"),
    "github-token": re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    "slack-token": re.compile(r"xox[abposr]-[A-Za-z0-9-]{10,}"),
    "private-key-pem": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "bearer-token": re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{20,}"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
}
KEY_RULE = "secret-key-name"
_SECRET_KEY = re.compile(
    r"(?i)^(api[_-]?key|apikey|password|passwd|secret|client[_-]?secret|access[_-]?token|auth[_-]?token|token"
    r"|private[_-]?key)$"
)
RULE_IDS: tuple[str, ...] = (*VALUE_RULES, KEY_RULE)

_FIELDS = ("name", "path", "rule", "fingerprint", "reason")
_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}")


@dataclass(frozen=True)
class Finding:
    """A secret-like value at `path` (a JSON pointer) inside config `name`. Never carries the value."""

    name: str
    path: str
    rule: str


@dataclass(frozen=True)
class AllowEntry:
    name: str
    path: str
    rule: str
    fingerprint: str
    reason: str


def fingerprint(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def pointer(parts: tuple[str | int, ...]) -> str:
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def _strings(config: Any) -> Iterator[tuple[tuple[str | int, ...], str | None, str]]:
    """Each string value in document order, with its path parts and its object key (None inside a list).

    Iterative, so deeply nested legacy configs can't overflow the stack.
    """
    stack: list[tuple[tuple[str | int, ...], str | None, Any]] = [((), None, config)]
    while stack:
        parts, key, value = stack.pop()
        if isinstance(value, dict):
            stack.extend(((*parts, k), k, v) for k, v in reversed(list(value.items())))
        elif isinstance(value, list):
            stack.extend(((*parts, i), None, v) for i, v in reversed(list(enumerate(value))))
        elif isinstance(value, str):
            yield parts, key, value


def _matches(config: Any) -> Iterator[tuple[tuple[str | int, ...], str, str]]:
    """(path parts, rule, matched substring): value rules in table order, then the key rule."""
    for parts, key, text in _strings(config):
        for rule, pattern in VALUE_RULES.items():
            for match in pattern.finditer(text):
                yield parts, rule, match.group(0)
        if key is not None and _SECRET_KEY.search(key) and text and not text.startswith("secret://"):
            yield parts, KEY_RULE, text


def _findings(name: str, config: Any, allow: Iterable[AllowEntry], used: set[AllowEntry] | None):
    allowed = {(e.name, e.path, e.rule, e.fingerprint): e for e in allow}
    found: dict[Finding, tuple[str | int, ...]] = {}
    for parts, rule, matched in _matches(config):
        path = pointer(parts)
        entry = allowed.get((name, path, rule, fingerprint(matched)))
        if entry is not None:
            if used is not None:
                used.add(entry)
            continue
        found.setdefault(Finding(name, path, rule), parts)
    return found


def scan(name: str, config: Any, allow: Iterable[AllowEntry] = (), used: set[AllowEntry] | None = None) -> list[Finding]:
    """Non-allowlisted findings in `config`, one per (path, rule), in document order.

    An allowlist entry suppresses a finding only when name, path, rule and the fingerprint of the exact matched
    substring all match (for the key rule, the matched substring is the whole value). Entries that suppressed
    something are added to `used`.
    """
    return list(_findings(name, config, allow, used))


def redact(name: str, config: Any, allow: Iterable[AllowEntry] = ()) -> tuple[Any, list[str]]:
    """A copy of `config` with each flagged string replaced by "<redacted:RULE>", plus the redacted paths.

    The first finding at a path decides the rule. The input is never mutated; without findings it is returned as is.
    """
    found = _findings(name, config, allow, None)
    if not found:
        return config, []
    copy = json.loads(json.dumps(config))
    paths: list[str] = []
    for finding, parts in found.items():
        if finding.path in paths:
            continue
        paths.append(finding.path)
        target = copy
        for part in parts[:-1]:
            target = target[part]
        target[parts[-1]] = f"<redacted:{finding.rule}>"
    return copy, paths


def parse_allowlist(value: Any, filename: str) -> list[AllowEntry]:
    """Validate a parsed secret-allowlist.json. Errors name entries and rules, never fingerprints."""
    prefix = f"Invalid secret allowlist {filename}"
    if not isinstance(value, dict) or set(value) != {"allow"} or not isinstance(value["allow"], list):
        raise SchemaError(f'{prefix}: the top level must be {{"allow": [...]}}')
    entries = []
    for index, item in enumerate(value["allow"]):
        where = f"{prefix}: entry {index}"
        if not isinstance(item, dict):
            raise SchemaError(f"{where} must be an object")
        unknown = sorted(set(item) - set(_FIELDS))
        if unknown:
            raise SchemaError(f"{where}: unknown key {unknown[0]!r}")
        missing = [field for field in _FIELDS if field not in item]
        if missing:
            raise SchemaError(f"{where}: missing {missing[0]}")
        if not all(isinstance(item[field], str) for field in _FIELDS):
            raise SchemaError(f"{where}: every field must be a string")
        if item["rule"] not in RULE_IDS:
            raise SchemaError(f"{where}: unknown rule {item['rule']!r}")
        if not _FINGERPRINT.fullmatch(item["fingerprint"]):
            raise SchemaError(f"{where}: fingerprint must be 'sha256:' followed by 64 lowercase hex digits")
        if not item["reason"].strip():
            raise SchemaError(f"{where}: reason must not be empty")
        entries.append(AllowEntry(*(item[field] for field in _FIELDS)))
    return entries
