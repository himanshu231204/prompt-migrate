# REFERENCES — Official docs, conceptual inspiration, related open source

> Checked/considered on 2026-10-29. Links may change. Prefer primary documentation over marketing assertions.

## Alembic (primary conceptual inspiration)

- SQLAlchemy Alembic documentation: https://alembic.sqlalchemy.org/en/latest/
- Alembic tutorial (revision files, `down_revision`, upgrade/downgrade): https://alembic.sqlalchemy.org/en/latest/tutorial.html
- Alembic command API: https://alembic.sqlalchemy.org/en/latest/api/commands.html
- Alembic GitHub source: https://github.com/sqlalchemy/alembic

## Existing prompt/versioning platforms

- Langfuse prompt management: https://langfuse.com/docs/prompt-management/overview
- Langfuse version control, labels, rollback: https://langfuse.com/docs/prompt-management/features/prompt-version-control
- Langfuse GitHub: https://github.com/langfuse/langfuse
- MLflow Prompt Registry: https://mlflow.org/docs/latest/prompts
- MLflow GitHub: https://github.com/mlflow/mlflow
- Agenta prompt management: https://agenta.ai/docs/prompt-management/overview/
- Agenta GitHub: https://github.com/Agenta-AI/agenta
- promptctl GitHub: https://github.com/prompt-ctl/prompt-ctl

## Design and verification caution

These tools already solve portions of **prompt versioning, labels, environment deployment, diffs, or prompt tests**. Do not position PromptMigrate as the first tool with any of those capabilities. The differentiation is a **migration transition protocol for interdependent AI configuration**, with explicit preconditions and environment consistency. Validate whether teams actually need it before committing to large infrastructure.

## Project's own existing prototype

- The `promptmigrate-starter` prototype, imported into this repository on 2026-10-30.
- `README.md`, `docs/archive/STARTER_ARCHITECTURE.md`, `src/promptmigrate/core.py`, `src/promptmigrate/cli.py`, `tests/test_core.py`, `pyproject.toml`.
- Test baseline: see `docs/TESTING_STRATEGY.md` (7 OK on Linux 2026-10-29; 2 pass / 5 error on Windows 2026-10-30).

## Architecture techniques (general)

- GitOps-style declarative desired state compared with applied state.
- Append-only migration history and idempotent state transitions.
- Content-addressed immutable release artifacts.
- Transactional compare-and-swap activation pointers.
- Separate eval/policy evidence from migration consistency checks.

The general techniques above are architecture proposals for PromptMigrate; they are not guarantees inherited automatically from any cited tool.
