# Changelog

All notable changes to PromptMigrate are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/). Before 1.0, CLI and file contracts may change; such changes are marked **Contract**.

---

## [Unreleased]

### Documentation
- **ADR-030 `rebase`** — accepted the design for `promptmigrate rebase` (#15): re-parent an unapplied branch after a Git merge with new ids, written as v1, refusing applied revisions and conflicting prompts; docs only, `rebase` is not implemented
- **README** — explain recovery from line-ending drift (#104)

- **Roadmap** — records that `promptmigrate-cli` 0.1.0 is published on PyPI (#55); the documented upgrade policy (#56) remains open
- **README badge and install** — adds a PyPI version badge, a quick `pip install promptmigrate-cli` line near the top, and a CI example that installs the published package instead of the Git repository

---

## [0.1.0] - 2026-11-19

### Added

- **PyPI release workflow** — `.github/workflows/release.yml` publishes to PyPI with trusted publishing (OIDC, no stored token) when a `v*` tag is pushed; it checks the tag against the `pyproject.toml` version, builds, runs the package smoke test, then publishes from the `pypi` environment (#55)
- **`promptmigrate-cli` distribution name** — the PyPI distribution is renamed because `promptmigrate` is taken; the import package and the `promptmigrate` command are unchanged, and `--version` reads the new name
- **`validate` command** — `promptmigrate validate [--strict] [--drafts-clean]` is a source-only check for CI: it audits history, drafts, the environment manifest and the allowlist, and never touches `states/`; Tier-A errors exit 3, warnings exit 0 (3 under `--strict`) (#10, ADR-028). **Contract:** new command
- **`restamp` command** — `promptmigrate restamp --env <env>` re-stamps the ledger checksum of applied v0 revisions whose file changed only in line endings; all-or-nothing, UTF-8 files only, and `check`, `current`, `get`, `plan`, `upgrade` and `downgrade` now name it when they fail such a row (exit 4) (ADR-027). **Contract:** new command
- **`plan` command** — `promptmigrate plan [--env E] [--target head|-1|base|<revision>]` is a read-only preview of what `upgrade` or `downgrade` would do; target resolution is shared with both commands (ADR-023). **Contract:** new command
- **`--output json`** — **Contract:** global `--output {text,json}` prints one `promptmigrate.output/1` envelope for every command, success or handled error, with warnings listed in it; text output is unchanged (ADR-024)
- **`--version`** — prints the installed package version and exits 0 (#16)
- **Declared environments** — **Contract:** `init` declares `dev` and `staging` in `.promptmigrate/environments.json`; `env add <name>` adds a declaration atomically and `env list` shows each name and whether its SQLite file exists; names resolve case-insensitively, and legacy projects are adopted on the first mutation with one warning
- **Protocol v1** — **Contract:** revision files with `"format_version": 1` use a `v1:`-tagged SHA-256 of the canonical parsed object, so line endings, whitespace and key order no longer count; `revision` now writes v1 with LF on every OS. Any other `format_version`, or an unknown key in a v1 file, is a `SchemaError` (ADR-026). PromptMigrate versions without v1 support treat these files as v0, so use one version per environment; mixing them fails closed with "Migration file was modified after apply"
- **Secret safeguard** — **Contract:** `revision` refuses secret-like values in new `after` values or messages (`SecretDetectedError`, naming path and rule only); `diff`, `get` and `history` redact flagged strings as `<redacted:RULE>`; `check` warns about secrets in history; false positives go in the fingerprinted `.promptmigrate/secret-allowlist.json`. Detection is heuristic
- **Append-only `events` table** — `upgrade`, `downgrade` and `restamp` append one event per applied, reverted or re-stamped revision in the same SQLite transaction as the ledger; triggers reject `UPDATE`, `DELETE` and `seq` reuse; older state DBs gain the table on their first mutation; there is no command to read events yet (#14, ADR-029)
- **Atomic revision writes** — `project.write_new_file` writes a hidden temp file, fsyncs it and publishes it with a hard link that never overwrites; filesystems without hard links fall back to an exclusive create that is no-clobber but not crash-atomic
- **Static type checking** — mypy runs over `src/` in lenient mode in a `type-check` CI job on Python 3.10, 3.12 and 3.13; `mypy` is a dev-only dependency capped at `>=2.4,<2.5` (#20)
- **Advisory AI review** — a pull request review workflow using Open CodeReview, pinned by commit, with a primary and a fallback model on NVIDIA's free endpoint (override with `OCR_LLM_MODEL` and `OCR_LLM_FALLBACK_MODEL`); it only comments and is not part of the merge gate
- **`uv.lock`** — pins the dev dependencies for `uv run --extra dev`; the runtime stays stdlib-only
- **`dev` extra** — `pytest`, `hypothesis` and `pytest-cov`; pytest now finds `src/` without `PYTHONPATH`
- **Python classifiers** — 3.10, 3.12 and 3.13 in `pyproject.toml`, matching the CI matrix
- **`examples/multi-agent-basic/`** — two agent drafts and a cross-platform `run.py` that walks the full lifecycle
- **Community files** — `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), a root `SECURITY.md` (private reporting through GitHub), and issue and pull request templates

### Changed

- **Package author** — the `pyproject.toml` author is now Himanshu Kumar instead of "PromptMigrate contributors"
- **Exit codes** — **Contract:** handled errors exit by type: 3 for schema and source errors, 4 for drift, integrity and conflicts, 5 for storage, `sqlite3` and `OSError` failures; other handled errors still exit 1 and usage errors 2. Scripts testing for exactly 1 must change
- **Strict parsing** — **Contract:** duplicate keys, `NaN`/`Infinity`, number literals that overflow to infinity, JSON nested too deep, and files resolving outside `.promptmigrate/` (including a symlinked `versions/` or `drafts/`) are rejected everywhere (tier A)
- **Canonical equality** — **Contract:** configs compare by canonical JSON, so `1`, `1.0` and `true` are distinct; a `1` → `true` draft edit produces a revision, bool/int drift in an env DB is detected, and a hand-edited revision that relied on the old conflation fails with `unexpected current value`
- **Hygiene and limits** — **Contract:** drafts and new revisions are rejected for wrong reserved-field types, config depth above 64, drafts over 1 MiB or symlinked, draft names equal case-insensitively, and revision files over 16 MiB (tier B); existing revision files that break these still load with a stderr warning
- **Typed errors** — handled failures raise `MigrationError` subclasses (`InitializationError`, `SchemaError`, `RevisionGraphError`, `MigrationConflictError`, `DriftError`, `IntegrityError`, `TargetError`, `PendingRevisionsError`), plus `StrictValidationError` for `validate --strict`; an OS error reading a revision file reports `Unreadable migration <file>: …`
- **Read-only state reads** — **Contract:** `check`, `current` and `get` use read-only SQLite connections; missing state is the empty base and reads never create or repair files; incomplete or corrupt DBs, WAL-mode DBs and state symlinks fail as storage errors; production-like environment names warn that state stays local SQLite
- **`revision` collision handling** — runs under the project lock, never overwrites an existing file (`Revision file already exists: <name>`, exit 5), regenerates a colliding id up to 5 times, and leaves no partial `.json` or `.tmp` on a reported failure
- **Package layout** — `protocol/` and `store/` are packages, `core.py` is a re-export facade, each CLI verb lives in `commands/<verb>.py`, and tests are grouped into `unit`, `integration`, `contract` and `security`; no CLI, file-format or checksum change, and tests now patch the defining module (ADR-022)
- **CI** — runs 7 jobs per PR instead of 12: `docker-all-in-one` merges the Docker and smoke jobs, `native-test` covers Windows on 3.10 and 3.13 and macOS on 3.13, the other legs run weekly, and `ci-pass` is the single required check
- **Merge gate** — requires green CI on every OS/Python job, a branch up to date with `main`, resolved review threads and real test output in the PR; it needs no approval while there is one maintainer

### Fixed

- **SQLite connection leaks** — every command now closes its connection; leaked connections kept `states/<env>.sqlite3` locked and 5 of 7 tests errored on Windows
- **Raw `sqlite3.Error` in `apply.migrate`** — the `prompts` read now raises `StorageError("Corrupt environment state")` like `_verify` (exit 5 unchanged) (#93)
- **Lock and file-mode follow-ups** — `restamp` checks the env DB under the re-entrant project lock (a nested `flock` deadlocked on Linux and macOS), a Windows mutex failure raises a typed `StorageError`, and writing files no longer reads or restores the process umask (#79)
- **CRLF false tamper for new revisions** — fixed by writing v1 revisions with LF
- **Unpaired surrogates in v1 revisions** — now a `SchemaError` (exit 3) instead of a traceback
- **README CI example** — installs PromptMigrate from its Git repository and replays revisions into a throwaway `dev` environment before `check --require-head`
- **Package smoke import guard** — verifies namespace package portions through `__path__` instead of crashing on a missing `__file__`
- **CI cancellation** — superseded runs on non-`main` refs are cancelled through a workflow-level group; every `main` run always runs
- **Copilot instructions link** — pointed to the missing `.github/AGENTS.md`

### Testing

- **Fault-injection suite for `apply.py`** — raises an exception or `sqlite3` error at every read, write and commit point of `upgrade` and `downgrade` (35 cases); the ledger and `prompts` rows stay unchanged and a retry succeeds (#12)
- **Concurrent `upgrade` test** — two real processes run `upgrade head` on one environment; exactly one applies both revisions and the other sees nothing to do or fails closed (#11)
- **Package-install smoke tests** — build wheel and sdist into a fresh temporary directory, install them into separate venvs outside the checkout, verify import origins, run a full draft round trip, and run `validate` through the console script (#13, #87)
- **README quick-start smoke test** — runs the README commands against an empty temporary project on every OS (#21)
- **Characterization tests and legacy fixtures** — pin graph errors, target rules, CLI text output and exit codes, with strict xfails naming their fixing PR
- **v1 integrity tests** — re-saved v1 revisions still verify, value edits fail closed, mixed v0 → v1 histories work, plus a property test over random re-serializations
- **Example test** — `tests/contract/test_examples.py` runs `examples/multi-agent-basic` on every test run
- **Cross-OS CI** — the suite runs on Ubuntu, Windows and macOS with pytest

### Documentation

- **Release guide** — `docs/RELEASING.md` is a maintainer guide for publishing `promptmigrate-cli` to PyPI: how the tag-triggered workflow runs, the one-time PyPI and `pypi` environment setup (tag rule `v*`), the pre-tag checklist, tagging and verification, and recovery when a release fails; `CONTRIBUTING.md` and `docs/HANDOFF.md` link to it
- **README** — rewritten for contributors with badges, a Mermaid flow diagram, an SVG banner and a social preview image; the install section now points at `promptmigrate-cli`; the stale claim that a local Windows run gates merges is removed
- **Integrity guidance** — applied v0 revisions are checked by raw bytes, v1 revisions by canonical parsed content; the v0 CRLF risk is documented, and ADR-025 freezes v0 semantics
- **Design docs** — `ROADMAP.md`, `PRD.md`, `LOW_LEVEL_DESIGN.md`, `CLI_SPEC.md` and `HANDOFF.md` follow the shipped commands, exit codes, JSON output and strict loader; the verified test baseline is refreshed
- **Changelog format** — this file follows Keep a Changelog, and `AGENTS.md` names the format

### Internal

- **`AGENTS.md`** — restructured as the single source of truth for AI agent rules: critical rules, commands, code style, issue and PR rules, Working style, Boundaries and a "Before every commit" rule; `CLAUDE.md`, `CODEX.md`, `GEMINI.md`, `HERMES.md` and `.github/copilot-instructions.md` only point to it
- **CodeRabbit configuration** — reviews draft pull requests, and its workflow rule no longer forbids host-side CI jobs (#73)
