"""Public facade: every name the original monolithic core.py exposed, re-exported from the module that defines it.

New code imports from the defining module. Monkeypatching a name here has no effect on behaviour; patch the defining
module instead (see docs/DECISIONS.md, ADR-022).
"""

from __future__ import annotations

from .apply import _actual, _applied, _verify
from .commands.check import audit_secrets, check
from .commands.downgrade import downgrade
from .commands.env import env_add, env_list
from .commands.get import get_config, redacted_config
from .commands.history import redacted_history
from .commands.init import init
from .commands.plan import plan
from .commands.revision import revision
from .commands.upgrade import upgrade
from .draftdiff import draft_diff, redacted_diff
from .errors import (
    DriftError, InitializationError, IntegrityError, LegacyRevisionWarning, MigrationConflictError, MigrationError,
    PendingRevisionsError, RevisionGraphError, SchemaError, SecretDetectedError, SecretInHistoryWarning,
    SecretRedactedWarning, StaleAllowlistWarning, StorageError, TargetError,
)
from .project import ALLOWLIST_FILE, load_allowlist, pretty, read_drafts, require_init, root_dir
from .protocol import canonical, same
from .revisions import _LEGACY, Revision, _apply_changes, _hash, load_revisions, replay_revisions
from .secretscan import _REDACTED
