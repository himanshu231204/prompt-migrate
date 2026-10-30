# PROJECT — PromptMigrate

## 1. Elevator pitch

**PromptMigrate is an open-source, Alembic-inspired CLI that treats AI prompts and agent configuration as migratable infrastructure.** Developers generate revision files, review diffs, validate dependencies and expected state, apply them to environments, and roll back reversibly. Later, it will deploy immutable configuration *bundles* through controlled release activation and evaluation gates.

One sentence: **“Alembic-style change control for production AI behavior configuration.”**

## 2. Origin of the idea

The initiating observation is that backend engineers use tools like **Alembic** to version database schema changes, yet production AI teams often alter prompts as ordinary files, environment variables, or mutable registry entries without equivalent migration discipline.

The inspiration is **not** to copy Alembic's SQL/ORM behavior. It is to adopt its mental model:

- An ordered chain of revisions (`revision`, `down_revision`).
- An environment records what was applied, not merely what exists in Git.
- Upgrade/downgrade are deliberate operations with preconditions.
- Reversible changes and drift/conflict checks are part of operating the system.
- CI and approvals can block unsafe changes.

The project is informed by existing prompt platforms such as Langfuse, MLflow Prompt Registry, Agenta, and CLI tools such as promptctl. They already offer substantial prompt versioning/deployment capabilities; see [COMPETITIVE_LANDSCAPE.md](COMPETITIVE_LANDSCAPE.md).

## 3. Who it serves

1. **AI/backend engineers** owning prompts and agents in applications written with FastAPI, Python, Node, LangGraph, etc.
2. **Platform/DevOps engineers** needing reproducible dev → staging → production configuration promotion.
3. **AI quality and safety engineers** needing evidence that revisions passed tests before activation.
4. **Open-source maintainers** who want local-first, reviewable prompt history without operating a proprietary platform.

## 4. Why existing approaches fall short for this specific goal

- **Hardcoded prompts:** source history shows changes but not which prompt bundle is active in a given environment.
- **Individual prompt registry labels:** convenient for switching one prompt, but compatible multi-agent changes and migration dependency rules may require a separate coordination layer.
- **Ad hoc environment variables:** mutable and difficult to audit/reproduce.
- **Manual rollback:** error-prone; partial deployments can mix prompt/tool/schema versions.
- **Git-only diffs:** do not automatically check state drift or guarantee a valid ordered transition.

These are **problem scenarios**, not claims that all existing competitors lack every feature. Evaluate integration opportunities first.

## 5. Product promise

A developer can answer:

- What is the source migration head?
- What exact configuration is applied in dev/staging/production?
- What changed between two revisions?
- Is the environment consistent with its declared history?
- Which migrations will be applied, in what order, and what can break?
- Can we restore the previous known-good configuration safely?
- Eventually: which complete release (agents, prompts, tools, schemas, models) handled a given request?

## 6. Example

A company operates `planner`, `sql_agent`, and `reviewer` agents. A developer modifies `sql_agent` to disallow destructive SQL and also changes `reviewer`'s output schema. Both changes must be compatible and reviewed together. A revision records both `before` and `after` snapshots. After validation it can be applied in one local database transaction. Later, production release activation should make the **entire compatible bundle** live, not update agents one by one.

## 7. Product principles

1. **Migration-first, not UI-first.** CLI and protocol are the product foundation.
2. **Git-native reviewability.** Declarative text revisions can be code-reviewed.
3. **Fail closed.** Unknown state, missing dependencies, corrupted history, or drift block writes.
4. **Deterministic state transitions.** Same inputs, same expected state; no LLM calls during migration execution.
5. **Explicit runtime integration.** The CLI must not pretend to update external models or hardcoded prompts.
6. **Bundles over isolated strings.** Version full compatible agent configuration in future releases.
7. **Provider-neutral interfaces.** Adapters complement registries rather than replace them.
8. **Security by default.** No credential values in migrations; secret references only.
9. **Honest boundaries.** Rollback of configuration cannot undo already-performed agent actions.
10. **Low adoption cost.** Small local core, no daemon/server required for MVP.

## 8. What it is not

- Not LLM weight/model checkpoint version control.
- Not guaranteed deterministic LLM outputs.
- Not a prompt playground, tracing platform, model gateway, RAG database, or evaluation dashboard.
- Not automatic prompt optimization or magic regression detection.
- Not a substitute for Git, SDLC review, access controls, or observability.
- Not a distributed database transaction manager.

## 9. Success metrics (proposed)

**Local MVP:** a new developer can initialize and complete revision → upgrade → drift check → downgrade without a provider account; migrations replay deterministically; mutation failures leave local state unchanged; documentation matches real CLI semantics.

**Later production:** 100% of activated releases have immutable IDs and auditable approvals; no partial bundle becomes active; interrupted publish can be reconciled; deployment rollback means active release reference switches back safely; runtime logs show the immutable release ID.

## 10. Positioning

**Migrations and policy-controlled activation for AI configuration** is the differentiation. Competitors' immutable versions and aliases are an opportunity for adapter integrations, not proof we are first to version prompts.
