# Contributing to PromptMigrate

Thanks for helping. PromptMigrate is a small, local-first CLI for declarative migrations of AI prompt and agent
configuration. Before proposing a feature, read [`docs/PROJECT.md`](docs/PROJECT.md) and the non-goals in
[`docs/ROADMAP.md`](docs/ROADMAP.md): it is not a prompt editor, registry, dashboard, observability tool or agent
framework.

## Set up

Python 3.10 or newer. The runtime uses only the standard library; the dev extras add `pytest`, `hypothesis` and
`pytest-cov`.

```bash
python -m venv .venv
source .venv/bin/activate                        # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -q                              # the whole suite
PYTHONPATH=src python -m unittest discover -s tests -v   # the original seven tests (PowerShell: $env:PYTHONPATH='src')
python -m promptmigrate --project /tmp/demo init # the CLI
```

Every command after the activation runs in the virtual environment. Activate it again in each new shell.

## How work is done here

The rules are in [`AGENTS.md`](AGENTS.md); they apply to human and AI contributors alike. In short:

- **Test first.** Write the failing test, watch it fail for the right reason, make it pass, then run the *whole*
  suite. A known but unfixed bug is pinned as `@pytest.mark.xfail(strict=True)` with a reason that names the fix.
- **No behaviour change without docs.** Update `docs/CLI_SPEC.md`, `docs/MIGRATION_PROTOCOL.md`, `docs/DECISIONS.md`
  and `CHANGELOG.md` in the same pull request.
- **Never change the revision file format or checksum semantics** without an explicit format version.
- **No secrets in revisions, logs or fixtures.** Tests build token-shaped values at runtime from fragments, e.g.
  `"sk-" + "0" * 24`. Never commit a token-shaped literal.
- **No new runtime dependencies.**

Branches are named `<type>/<short-description>` (`feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`,
`build`, `ci`). Commits use [Conventional Commits](https://www.conventionalcommits.org/).

## Where does X live?

Each concept has one module (ADR-022 in [`docs/DECISIONS.md`](docs/DECISIONS.md)). Imports only point down this list,
and `tests/unit/test_module_layout.py` enforces that.

| You are changing… | Look in |
|---|---|
| An error or warning type | `src/promptmigrate/errors.py` |
| Strict JSON loading, size/depth limits, canonical equality, name or config rules | `src/promptmigrate/protocol/` |
| Secret detection, the allowlist format, redaction | `src/promptmigrate/secretscan.py` |
| The `.promptmigrate/` layout, reading drafts or the allowlist | `src/promptmigrate/project.py` |
| Parsing revision files, the revision graph, replay | `src/promptmigrate/revisions.py` |
| Declared environments, adoption, locking, SQLite connections | `src/promptmigrate/store/` |
| Drafts compared with the source head | `src/promptmigrate/draftdiff.py` |
| Verifying or writing an environment's applied state | `src/promptmigrate/apply.py` |
| What one CLI verb does and prints | `src/promptmigrate/commands/<verb>.py` |
| Argument parsing, warning capture, error printing | `src/promptmigrate/cli.py` |

`core.py` only re-exports the public API. Inside the package, call collaborators through their module
(`project.read_drafts(...)`). In tests, patch the module that defines a function, never `core` or `cli`.

Tests are grouped by suite: `tests/unit/`, `tests/integration/`, `tests/contract/` and `tests/security/` (see
[`docs/TESTING_STRATEGY.md`](docs/TESTING_STRATEGY.md)). Shared helpers go in `tests/pmtest.py`.

## Pull requests

Fill in the pull request template. Paste the real output of `python -m pytest -q` from your machine, and say which OS
and Python version you ran it on. Linux and macOS behaviour is only claimed once CI has run.

## Reporting problems

Use the issue templates for bugs and feature requests. Report security problems privately, as described in
[`SECURITY.md`](SECURITY.md).

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
