"""Error and warning types. Every handled error is a MigrationError; every warning is a PromptMigrateWarning."""


class MigrationError(Exception):
    """An invalid revision, unexpected environment state, or unsafe operation."""


class InitializationError(MigrationError):
    """The project is not initialized, or is already initialized."""


class SchemaError(MigrationError):
    """A draft, revision file or command input is malformed or breaks a validation rule."""


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
