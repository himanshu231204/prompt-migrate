# IMPLEMENTATION PLAN — How Claude should approach the codebase

## Scope rule

**First review architecture and starter; then harden CLI and migration engine.** Do not build dashboards, deploy a cloud service, or integrate external registries in the first pass. Preserve existing behavior and run tests after each step.

## Workstream 0 — Audit the existing starter

- Read `README.md`, `ARCHITECTURE.md`, `pyproject.toml`, `src/promptmigrate/core.py`, `src/promptmigrate/cli.py`, tests.
- Run baseline unit test suite and capture results.
- List implemented features versus this documentation.
- Identify correctness/security gaps, backward compatibility pitfalls, and refactor priorities.
- Produce an incremental plan before significant changes.

**Deliverable:** short written gap assessment and proposed PR order.

## Workstream 1 — Protocol validation and testing

1. Write formal JSON schema / validation functions for draft and revision objects.
2. Document accepted fields, unknown keys, sizes, null operations, date format.
3. Test graph errors, replay invariants, invalid state, deletion, Unicode.
4. Verify current artifact hash semantics and compatibility.
5. Harden safe filesystem writes and revision ID collisions.

**Done when:** malformed files never reach DB mutation and no existing valid migration changes meaning silently.

## Workstream 2 — Deterministic planner

1. Extract `MigrationPlan` and `PlanStep` domain models.
2. Separate target selection from DB writes.
3. Implement read-only `plan --env ...` output.
4. Add tests proving plan matches actual apply ordering and mutation count.

**Done when:** plan is deterministic and read-only, with actionable errors for invalid target/history/drift.

## Workstream 3 — Transaction executor and error model

1. Move SQLite logic into storage adapter without behavioral drift.
2. Implement targeted error hierarchy and stable CLI handling.
3. Test rollback on failure and concurrent invocations.
4. Add structured JSON output only with stable schemas.

**Done when:** failure never partially updates local configuration and ledger; CLI contract tests pass.

## Workstream 4 — Docs, packaging and CI

1. Make README commands executable smoke tests.
2. Add CI OS/Python matrix appropriate to supported runtimes.
3. Review `.gitignore`, source distribution and wheel inclusion.
4. Add contributor setup instructions and security reporting plan.
5. Document version compatibility and local-only safety prominently.

**Done when:** clean fresh install works, tests pass, and a new developer can reproduce the demo.

## Workstream 5 — Later opt-in evaluation interface

After Phase 1 is stable, propose policy syntax, evaluation evidence formats, baseline comparisons, tool-schema checks, reproducibility limits. Do not block the core on a live LLM provider.

## Workstream 6 — Later release controller / SDK

After evaluation design, formalize manifest/activation protocol, Postgres schema, runtime release pinning, adapter idempotency and reconciliation. Build one rigorous integration rather than many superficial ones.

## PR acceptance checklist

- [ ] Linked PRD requirement/ADR.
- [ ] Tests for happy, invalid, and failure paths.
- [ ] No break to existing revision files without migration path.
- [ ] No secrets/config content leaking into logs.
- [ ] CLI help and docs updated if commands change.
- [ ] Tests executed; actual results included.
- [ ] Local-versus-production claim remains accurate.
- [ ] Complexity justified and no unnecessary dependencies.

## “Do not do” list for Claude

- Do not rewrite code wholesale without regression coverage.
- Do not claim production readiness from seven tests.
- Do not implement remote writes disguised as transactional migration.
- Do not introduce an unrelated AI agent orchestration framework into core.
- Do not silently alter revision artifact or checksum format.
- Do not place runtime credentials or user data in migrations.
- Do not assume an uncommitted or independently generated `prod.sqlite3` reflects a live service.
