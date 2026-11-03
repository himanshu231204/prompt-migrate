"""PromptMigrate: declarative, reversible AI prompt configuration migrations."""

__version__ = "0.1.0"

from .core import (  # noqa: E402  (the public facade, after the version so tooling can read it without imports)
    ALLOWLIST_FILE, DriftError, InitializationError, IntegrityError, LegacyRevisionWarning, MigrationConflictError,
    MigrationError, PendingRevisionsError, Revision, RevisionGraphError, SchemaError, SecretDetectedError,
    SecretInHistoryWarning, SecretRedactedWarning, StaleAllowlistWarning, StorageError, TargetError, audit_secrets,
    canonical, check, downgrade, draft_diff, env_add, env_list, get_config, init, load_allowlist, load_revisions,
    pretty, read_drafts, redacted_config, redacted_diff, redacted_history, replay_revisions, require_init, revision,
    root_dir, same, upgrade,
)

__all__ = [
    "ALLOWLIST_FILE", "DriftError", "InitializationError", "IntegrityError", "LegacyRevisionWarning",
    "MigrationConflictError", "MigrationError", "PendingRevisionsError", "Revision", "RevisionGraphError",
    "SchemaError", "SecretDetectedError", "SecretInHistoryWarning", "SecretRedactedWarning", "StaleAllowlistWarning",
    "StorageError", "TargetError", "audit_secrets", "canonical", "check", "downgrade", "draft_diff", "env_add",
    "env_list", "get_config", "init", "load_allowlist", "load_revisions", "pretty", "read_drafts", "redacted_config",
    "redacted_diff", "redacted_history", "replay_revisions", "require_init", "revision", "root_dir", "same", "upgrade",
]
