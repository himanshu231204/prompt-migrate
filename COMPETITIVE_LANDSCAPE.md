# COMPETITIVE LANDSCAPE & INSPIRATION

> Assessment as of 2026-10-29. Features change: recheck official docs before making public uniqueness claims.

## Direct design inspiration

### Alembic (SQLAlchemy)

- Ordered schema revision files; `revision` and `down_revision` links.
- Commands for revision, upgrade, downgrade, current, history.
- A database records its migration state separately from code.
- Supports branches/merge revisions; we intentionally **do not** implement them in the first MVP.

**We borrow:** migration graph, forward/backward transitions, command ergonomics, recorded environment state.  
**We do not borrow:** SQLAlchemy-specific schema operations or arbitrary Python migration execution.

Official reference: https://alembic.sqlalchemy.org/en/latest/tutorial.html

## Related open-source tools

| Tool | Relevant capabilities already offered | Lesson for PromptMigrate |
|---|---|---|
| **Langfuse** | Versioned prompts, mutable deployment labels, diffs, SDK retrieval and tracing | Don't market ordinary prompt versioning or rollback as unique; design adapters |
| **MLflow Prompt Registry** | Immutable prompt versions, aliases, comparisons, tracing/evaluation ecosystem | Integrate rather than recreate a registry |
| **Agenta** | Prompt variants/branches, immutable versions, environments and deployment history | Multi-environment versions are established; differentiate on migration protocol/coordination |
| **promptctl** | Git-native CLI versioning/testing for prompt templates | CLI + Git alone isn't novel; add environment transition semantics and strict preconditions |
| **Alembic** | Revision DAG and transactional DB migration patterns | Main interaction metaphor and dependency model |

## Proposed differentiation (hypothesis to test)

- **Migration unit:** a set of compatible AI config objects with explicit before/after preconditions; later an immutable release manifest.
- **Reproducible application:** deterministic replay, ordered dependencies, drift checks, fail-closed apply.
- **Environment transition contract:** upgrade/downgrade semantics independent from the prompt registry backend.
- **Safe deployment boundary:** prepare, verify, and activate a release pointer instead of blindly overwriting individual prompts.
- **Local-first + provider-neutral:** simple core that works without hosted accounts.

This differentiation is **not yet validated** against every product/feature. Conduct user interviews and deeper feature comparisons before claiming novelty.

## Build vs integrate

| Capability | Build ourselves | Prefer integration |
|---|---|---|
| Migration planner / revision graph | Yes | — |
| Local SQLite revision ledger | Yes | — |
| Precondition and drift verification | Yes | Future remote inspection adapters |
| Prompt template authoring UI | No | Existing developer editors / registries |
| Tracing and inference observability | No | Langfuse, MLflow, OpenTelemetry |
| LLM evaluators and judge models | Interface/policy integration | Existing evaluation frameworks/providers |
| Provider-specific prompt storage | No | Registry adapters |
| Shared release state/control | Later | Postgres, object storage; external identity/RBAC |

## Research links

- Alembic tutorial: https://alembic.sqlalchemy.org/en/latest/tutorial.html
- Langfuse prompt versioning: https://langfuse.com/docs/prompt-management/features/prompt-version-control
- MLflow Prompt Registry: https://mlflow.org/docs/latest/prompts
- Agenta concepts: https://agenta.ai/docs/prompt-management/overview/
- promptctl: https://github.com/prompt-ctl/prompt-ctl

See [REFERENCES.md](REFERENCES.md) for more URLs.
