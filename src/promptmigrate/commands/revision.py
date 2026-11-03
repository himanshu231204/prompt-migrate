"""`revision`: write a new revision file from the drafts' difference to the source head."""

from __future__ import annotations

import argparse
import os
import re
import uuid
import warnings
from datetime import datetime, timezone
from pathlib import Path

from .. import draftdiff, project, protocol, revisions, secretscan
from ..errors import LegacyRevisionWarning, SchemaError, SecretDetectedError, SecretInHistoryWarning


def revision(project_dir: Path, message: str) -> revisions.Revision:
    if not message.strip():
        raise SchemaError("Revision message cannot be empty")
    all_revisions = revisions.load_revisions(project_dir)
    changes = draftdiff.draft_diff(project_dir)
    if not changes:
        raise SchemaError("No changes between drafts and migration head")
    rid = uuid.uuid4().hex[:12]
    parent = all_revisions[-1].revision if all_revisions else None
    for name, change in changes.items():
        if change["after"] is not None:
            found = protocol.config_violations(name, change["after"])
            if found:
                raise SchemaError(f"New revision would be invalid: {', '.join(found)}")
    allow = project.load_allowlist(project_dir)
    findings = [finding for name, change in changes.items() if change["after"] is not None
                for finding in secretscan.scan(name, change["after"], allow)]
    findings += secretscan.scan("(message)", {"message": message.strip()}, allow)
    if findings:
        raise SecretDetectedError(findings)
    item = {
        "revision": rid,
        "down_revision": parent,
        "message": message.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "changes": changes,
    }
    text = project.pretty(item)
    # write_text translates "\n" to os.linesep, so this is the exact size of the file it writes.
    size = len(text.replace("\n", os.linesep).encode("utf-8"))
    if size > protocol.limits.MAX_REVISION_BYTES:
        raise SchemaError(f"New revision would be {size} bytes; the limit is {protocol.limits.MAX_REVISION_BYTES}")
    for name, change in changes.items():
        if change["before"] is not None:
            carried = protocol.config_violations(name, change["before"])
            if carried:
                warnings.warn(f"revision {rid}: {name} before carries {', '.join(carried)} from history "
                              "(copied for compatibility)", LegacyRevisionWarning, stacklevel=2)
    for name, change in changes.items():
        if change["before"] is not None:
            for finding in secretscan.scan(name, change["before"], allow):
                warnings.warn(f"{finding.name} {finding.path} {finding.rule} copied from history into before; "
                              "the credential must be rotated", SecretInHistoryWarning, stacklevel=2)
    root = project.require_init(project_dir)
    path = root / "versions" / f"{rid}_{re.sub(r'[^a-z0-9]+', '_', message.lower()).strip('_')[:50] or 'revision'}.json"
    path.write_text(text, encoding="utf-8")
    return revisions.load_revisions(project_dir)[-1]


def run(args: argparse.Namespace) -> None:
    r = revision(Path(args.project), args.message)
    print(f"Created {r.revision} (parent: {r.down_revision or 'base'}): {r.path}")
