"""Error and warning types. Every handled error is a MigrationError; every warning is a PromptMigrateWarning."""


class MigrationError(Exception):
    """An invalid revision, unexpected environment state, or unsafe operation."""


class InitializationError(MigrationError):
    """The project is not initialized, or is already initialized."""


class SchemaError(MigrationError):
    """A draft, revision file or command input is malformed or breaks a validation rule."""


class SecretDetectedError(SchemaError):
    """New revision content holds a secret-like value that is not allowlisted. Carries findings, never values."""

    def __init__(self, findings) -> None:
        self.findings = [{"name": f.name, "path": f.path, "rule": f.rule} for f in findings]
        listed = "; ".join(f"{f['name']} {f['path']} {f['rule']}" for f in self.findings)
        super().__init__(f"Secret-like values in new revision content: {listed}. "
                         "No file was written; remove them or allowlist a reviewed false positive.")


class RevisionGraphError(MigrationError):
    """Source history is not one linear chain: duplicate id, several roots, missing parent, branch or cycle."""


class MigrationConflictError(MigrationError):
    """A change's precondition does not match the state it is applied to."""


class DriftError(MigrationError):
    """An environment's stored configs differ from the replay of its applied revisions."""


class IntegrityError(MigrationError):
    """An environment's ledger does not match source history: an edited, missing or diverging revision."""


class TargetError(MigrationError):
    """The requested revision target or config name does not exist, or is in the wrong direction."""


class PendingRevisionsError(MigrationError):
    """The environment is behind head where head was required."""


class PromptMigrateWarning(UserWarning):
    """Base class of every warning PromptMigrate emits."""


class LegacyRevisionWarning(PromptMigrateWarning):
    """An existing revision file breaks a tier-B rule; it is accepted for compatibility."""


class SecretRedactedWarning(PromptMigrateWarning):
    """Secret-like values were redacted from this command's output."""


class SecretInHistoryWarning(PromptMigrateWarning):
    """A secret-like value is in committed history; it stays in Git and must be rotated."""


class StaleAllowlistWarning(PromptMigrateWarning):
    """A secret allowlist entry matched nothing in drafts or history."""
