# PRODUCT REQUIREMENTS DOCUMENT (PRD)

## Product

**PromptMigrate**, working name. Open-source Python CLI plus a migration protocol for reviewable AI configuration changes.

## Objectives

**O1:** Generate immutable-in-practice migration artifacts by comparing developer drafts against reconstructed source head.  
**O2:** Apply/revert revisions in correct order while verifying environment preconditions.  
**O3:** Identify changed-applied history, drift, and incompatible migration chains.  
**O4:** Provide understandable CLI output and machine-readable CI failures.  
**O5 (later):** Promote evaluated, compatible configuration bundles to real environments through an atomic release pointer.

## Personas and jobs to be done

| Persona | Job |
|---|---|
| Backend/AI engineer | “Record and review a safe prompt/config change.” |
| Platform engineer | “Know what each environment has applied and block drift.” |
| Reviewer | “See what will change before merging/deploying.” |
| QA/safety engineer | “Require evaluation evidence before promotion.” (later) |
| Incident responder | “Find the last good release and restore it quickly.” (later) |

## User stories with priority

| ID | Story | Priority | Phase |
|---|---|---|---|
| FR-01 | Initialize project migration workspace | Must | MVP |
| FR-02 | Maintain named JSON agent configurations | Must | MVP |
| FR-03 | Generate revision with parent, message, timestamp, before/after states | Must | MVP |
| FR-04 | Reject no-op revision | Must | MVP |
| FR-05 | Validate unique linear revision chain and preconditions | Must | MVP |
| FR-06 | Preview draft/source changes and revision history | Must | MVP |
| FR-07 | Apply one/multiple pending revisions transactionally in local SQLite | Must | MVP |
| FR-08 | Downgrade to predecessor or base, restoring earlier snapshots | Must | MVP |
| FR-09 | Verify applied-file checksum and detect SQLite config drift | Must | MVP |
| FR-10 | Expose current revision and applied configuration | Must | MVP |
| FR-11 | Dry-run `plan` with deterministic change summary | Must | Next hardening milestone |
| FR-12 | Strict JSON schema, canonical serialization/versioned artifact format | Must | Next hardening milestone |
| FR-13 | Structured CLI JSON output and meaningful errors/exit codes | Should | Next hardening milestone |
| FR-14 | Evaluation gates (golden datasets, structured outputs, policies) | Must | Later |
| FR-15 | PostgreSQL shared state, immutable releases, provider adapters | Must | Later production |
| FR-16 | Approved promotion + release pointer rollback | Must | Later production |
| FR-17 | UI dashboard | Won't | Initial releases |

## Nonfunctional requirements

- **Correctness:** every successful operation leaves ledger and configuration consistent.
- **Safety:** unexpected state must not be overwritten silently; fail closed.
- **Determinism:** migration execution makes no LLM call; replay produces identical logical state.
- **Portability:** Python 3.10+; standard library runtime in initial prototype.
- **Reviewability:** JSON revisions are diff-friendly; Git stores drafts and revisions.
- **Security:** no secrets in revisions; future secret scanning and policy enforcement.
- **Observability:** clear human errors now; JSON output/logging later.
- **Compatibility:** explicit format and API versioning before stable release.

## MVP acceptance criteria

1. `init` creates the expected files in a clean project.
2. Generating a revision from updated drafts correctly computes all additions, updates, and deletions.
3. Second revision references the first revision.
4. Bad/missing parent or branched graph fails with no environment changes.
5. Apply to `dev` does not implicitly modify `staging`.
6. A multi-prompt revision applies atomically within one SQLite connection.
7. Downgrade restores exact logical JSON snapshot and adjusts ledger.
8. Applied migration file tampering is detected on subsequent checks.
9. In-place SQLite config mutation causes drift failure.
10. Invalid env names and malformed config fail before state mutation.
11. Documented CLI examples can be exercised in automated tests.
12. README prominently states local-only behavior and production limitations.

Items 1–10 are **partially evidenced** by seven starter tests; they are **not** a comprehensive acceptance certification. Expand coverage before calling MVP hardened.

## Explicit exclusions from MVP

No web app, auth system, production SaaS, external registry writes, real deployment to Azure/OpenAI/Langfuse, LLM evaluation guarantees, distributed transactions, automated canaries, signed revisions, branch merges, or generalized script execution.

## Release gate

Do not label the tool production-grade solely because basic migration tests pass. The release gate is specified in [TESTING_STRATEGY.md](TESTING_STRATEGY.md) and [SECURITY.md](SECURITY.md).
