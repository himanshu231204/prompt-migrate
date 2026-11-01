# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

PromptMigrate is an Alembic-inspired, local-first Python CLI for declarative migrations of AI prompt and agent configuration. It provides ordered JSON revisions with before/after preconditions, per-environment applied state, reversible upgrade/downgrade, and integrity and drift checks. It is not a prompt editor, registry, dashboard, observability tool or agent framework.

Workflow, TDD rules, hard rules and the review report format are in [`AGENTS.md`](AGENTS.md). Follow it.

## Status

- Implemented: `init`, `revision`, `history`, `diff`, `current`, `upgrade`, `downgrade`, `check`, `get`, `env add`, `env list`.
- Current scope: Phase 1, cycle 1, in `docs/ROADMAP.md`.
- `docs/` also describes future modules and commands (`plan`, `eval`, `export`, Postgres, SDK, …). They don't exist yet.
- Test baseline: after PR 4, Windows 11 / Python 3.11.9 reports `461 passed, 16 skipped, 33 warnings`; the original seven unittest tests pass. Skips include symlink and case-collision cases unavailable on this host. Linux/macOS are claimed only after a remote CI run.

## Commands

The runtime is standard-library only (Python ≥ 3.10). Put `src` on the path; installing is optional.

```bash
python -m pip install -e ".[dev]"                            # entry point + pytest, hypothesis, pytest-cov
python -m pytest -q                                          # all tests (CI runs it with -v); pyproject sets pythonpath=src
python -m pytest tests/test_core.py::PromptMigrateTests::test_state_drift_detected   # one test
python -m pytest -k drift                                    # tests matching a name
PYTHONPATH=src python -m unittest discover -s tests -v       # the original unittest suite still runs this way
PYTHONPATH=src python -m promptmigrate --project <dir> history   # CLI from source
```

- `tests/` is not a package. With unittest, select one test with `-k`, not with a dotted path.
- In PowerShell, use `$env:PYTHONPATH='src'`.
- No linter or type checker is configured.

## Architecture

Logic is in `src/promptmigrate/core.py` (public facade, revision parsing, graph, replay and migration transactions), `store.py` (declared environments and SQLite read/write connections), `protocol.py` (strict JSON loading, limits, config validation, `canonical`/`same`), `secretscan.py` (heuristic secret rules, fingerprinted allowlist, redaction; no I/O) and `errors.py` (error and warning types). `cli.py` is a thin argparse dispatcher: it prints any `MigrationError`, `OSError` or `sqlite3.Error` as `Error: …` on stderr and exits 1. It prints captured PromptMigrate warnings once each as `Warning: …` on stderr.

**Four states, kept distinct:**
1. **Drafts:** `.promptmigrate/drafts/<name>.json`, the desired config (one JSON object per name).
2. **Source history:** `.promptmigrate/versions/<12hex>_<slug>.json`. Each revision has `revision`, `down_revision`, `message`, `created_at`, and `changes: {name: {before, after}}`. These are full snapshots, and `null` means the config is absent.
3. **Environment declarations:** `.promptmigrate/environments.json` (Git tracked), with canonical names and metadata. Legacy projects are inferred for reads and adopted on first successful mutation.
4. **Applied env state:** `.promptmigrate/states/<env>.sqlite3` (gitignored), with tables `applied_revisions(seq, revision, checksum, applied_at)` and `prompts(name, config)`. `check`, `current`, and `get` use read-only SQLite; missing state is base, incomplete state is an error.
5. **Runtime state:** not implemented. Nothing connects SQLite state to an application, and `--env prod` is only a local file with an explicit warning.

**Cross-function flow:**
- **`load_revisions()`** runs in almost every command. It parses all version files and enforces one linear chain: one root, no branches, no cycles. It then replays the whole chain from `{}`, so every revision's `before` must match the rebuilt state. Source history validates itself, independent of any env.
- **`draft_diff()` / `revision()`** diff drafts against the replayed source head, never against an env DB. A deleted draft becomes an explicit delete change.
- **`upgrade()` / `downgrade()`**:
  - Open the env DB, run `BEGIN IMMEDIATE`, then call `_verify()`.
  - `_verify()` requires the ledger to be an exact prefix of source history by (id, checksum), and the `prompts` rows to equal `replay(prefix)`. Anything else is drift.
  - `_apply_changes()` then re-checks each precondition while writing.
  - Config rows and the ledger change in one SQLite transaction.
- **Checksums** are SHA-256 of the raw revision file bytes at apply time. Any byte change to an applied revision, including whitespace or CRLF, blocks that env. Don't change checksum or file-format semantics without an explicit format version.
- Downgrade deletes ledger rows. There is no audit or event log yet.
- `core.py` is the public API that tests import. Split it into modules gradually, keeping its exported names and signatures stable.

## Conventions

- Design docs are in `docs/`. Start with `docs/HANDOFF.md`, and record decisions in `docs/DECISIONS.md`.
- `docs/superpowers/` and `graphify-out/` are local-only and gitignored. Never commit them or link to them from tracked files.
- `.gitattributes` forces LF. Fixtures that must keep exact bytes need a `-text` rule.
- Branches are `<type>/<short-description>` (types: feat, fix, refactor, docs, test, chore, perf, build, ci), merged locally into `main` with `--no-ff`; don't push unless asked.
- Commits use Conventional Commits, are authored as the repository owner (repo-local git config), and carry no AI attribution (no `Co-Authored-By`, no "Generated by").
