# PromptMigrate architecture and production roadmap

## Thesis

Prompt **versioning** answers: “What changed in the text?”

Prompt **migration control** answers: “Which revision is active in each environment, what else did it depend on, was it tested, and can it be deployed/rolled back deterministically?”

The goal is **GitOps for a complete agent configuration bundle**, not another standalone prompt editor.

## Revision state machine

```text
Draft configs (Git) -> revision generator -> reviewed linear history
                                                 |
                      +--------------------------+--------------------+
                      |                          |                    |
                     dev                       staging                prod
                   r003                         r002                  r001
```

- Source history: immutable-in-practice JSON migration files in Git, each with `revision` and `down_revision`.
- Desired source state: replay the revision chain in order.
- Environment state: persistent applied revision ledger plus actual named prompt configuration values.
- Migration: verify source integrity and environmental drift; apply all changed objects + revision ledger together.
- Downgrade: verify current state then restore exact `before` snapshots, reverse order.
- Failure: fail closed and do not write any migration changes when preconditions are unsatisfied.

## Production architecture (not implemented in starter)

```text
                                  +---------------------+
                                  |  Git repo + PR flow |
                                  |  reviewed revisions |
                                  +----------+----------+
                                             |
                                      CI eval gates
                                             |
                                      Release controller
                                             |
                 +---------------------------+-----------------------+
                 |                           |                       |
           Postgres ledger             Blob/object store          Audit/logs
          revisions, releases         signed JSON bundles        eval evidence
                 |                           |
           desired state +--------- validated release manifest
                                             |
                   +-------------------------+------------------+
                   |                                            |
              staging runtime                                  prod runtime
           resolve active release                           resolve active release
                   |                                            |
          Provider adapters/SDKs                         Provider adapters/SDKs
```

The **release manifest** versions the compatible set of system/developer prompts, model identifiers, inference parameters, tool contracts, output schema, safety policy references, and eval-suite IDs. Prompts should be validated as a bundle to prevent accidental cross-version mismatches.

For remote providers, avoid pretending provider API calls form a distributed ACID transaction. Instead: (1) prepare immutable remote assets, (2) verify content and policy gates, (3) publish a release manifest, (4) atomically switch one environment's *active manifest pointer*, (5) monitor, (6) switch back if necessary. Use idempotent adapters, outbox, timeouts, and reconciliation for partial failures. Runtime caches need explicit invalidation or bounded TTL, and the SDK should fail closed on unknown release IDs.

## Threat model / production acceptance criteria

1. **Integrity:** migration content hashes and optional digital signatures are verified, revision IDs cannot be reused.
2. **Concurrency:** a shared environment may have only one active migration transaction; use advisory locks or a per-environment lease.
3. **Drift:** external edits to active prompt assets are detected against canonical snapshots.
4. **Safety:** eval suites check golden datasets, output contracts, tool permissions, prompt-injection robustness and critical regressions.
5. **Governance:** production promotions require approvals separate from revision authors, and are fully audited.
6. **Reproducibility:** every request log records an immutable release ID, model ID and relevant prompt/template identifiers (without leaking user data).
7. **Rollback:** activation pointer can move back quickly; rollback does not undo already-executed AI actions or external side effects.
8. **Secrecy:** migration files contain no API keys or production secrets; use secret-store references.
9. **Availability:** services can resolve a cached verified release even if the migration controller is temporarily unavailable.
10. **Testing:** multi-provider integration tests, concurrency/failure injection, interrupted rollout recovery, and load tests pass before production adoption.

## Scope boundary

The v0.1 prototype intentionally builds only the local migration core. It makes no claim of safe production rollout or automatic model evaluation. Production adapters, signed artifacts, central environment coordination, rollout policies, and dashboard belong in later milestones.

## First three milestones

- **Milestone A (shipped prototype):** Python CLI, Git-tracked declarative migrations, local SQLite environment state, deterministic upgrade/downgrade, checksum/drift enforcement, unit tests.
- **Milestone B:** pluggable evaluators, `plan` output, signed policy results, JSON CI reports, check for unresolved draft changes, enforce approval hooks.
- **Milestone C:** Postgres coordination, provider adapters, release manifest activation pointer, Python SDK, audit and repair commands, staging-to-production promotion.
