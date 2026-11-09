"""Revision artifact format versions and canonical artifact hashing.

format_version 0 (the starter / v0 format): the ledger checksum is the raw SHA-256 of the on-disk revision
file bytes. Any byte change — including whitespace-only or CRLF/LF differences — is detected as tampering.

format_version 1 (v1): the ledger checksum is the canonical-artifact SHA-256. The canonical form is the
re-serialized JSON (sorted keys, no whitespace, ensure_ascii=False), so whitespace-only edits do not change
the hash. Only semantically different content changes the hash.

Both formats keep a raw-byte SHA-256 (`Revision.checksum`) on the artifact; v1 additionally carries
`artifact_sha256` (the canonical hash). The ledger stores the hash appropriate to the artifact's format_version.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# The starter / v0 format: no explicit format_version field (absent or 0).
FORMAT_VERSION_V0 = 0
# The v1 format: explicit format_version: 1, canonical artifact hash in the ledger.
FORMAT_VERSION_V1 = 1

KNOWN_FORMAT_VERSIONS = frozenset({FORMAT_VERSION_V0, FORMAT_VERSION_V1})


def canonical_artifact_bytes(obj: Any) -> bytes:
    """Canonical serialization bytes for an artifact: sorted keys, compact separators, UTF-8.

    Strips whitespace and line-ending differences, so two files with the same logical content
    (e.g. LF vs CRLF) produce identical canonical bytes.
    """
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def artifact_hash(raw_bytes: bytes, format_version: int) -> str:
    """Return the hash to store in the ledger for an artifact of the given format version.

    v0: raw SHA-256 of the file bytes.
    v1: SHA-256 of the canonical artifact bytes.
    """
    if format_version == FORMAT_VERSION_V1:
        document = json.loads(raw_bytes)
        return hashlib.sha256(canonical_artifact_bytes(document)).hexdigest()
    # v0 (and any unknown version that made it here): raw bytes.
    return hashlib.sha256(raw_bytes).hexdigest()


def validate_format_version(value: Any, path_name: str) -> int:
    """Validate and return the format_version from a parsed revision artifact.

    Absent or 0 => v0. 1 => v1. Anything else raises SchemaError.
    """
    from ..errors import SchemaError

    if value is None:
        return FORMAT_VERSION_V0
    if not isinstance(value, int) or isinstance(value, bool):
        raise SchemaError(f"Invalid format_version in {path_name}: must be an integer")
    if value not in KNOWN_FORMAT_VERSIONS:
        raise SchemaError(f"Unsupported format_version {value} in {path_name}")
    return value