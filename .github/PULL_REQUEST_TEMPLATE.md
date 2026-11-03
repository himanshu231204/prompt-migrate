## What and why

<!-- One or two sentences. Link the issue or roadmap item. -->

## Checklist (see AGENTS.md)

- [ ] Tests were written first and seen failing for the right reason.
- [ ] Known but unfixed bugs are pinned as `xfail(strict=True)` with a reason naming the fix.
- [ ] Behaviour changes update `docs/CLI_SPEC.md`, `docs/MIGRATION_PROTOCOL.md`, `docs/DECISIONS.md` and `CHANGELOG.md`.
- [ ] No change to the revision file format or checksum semantics (or an explicit format version is added).
- [ ] No token-shaped literal in code, tests or fixtures; fake secrets are built at runtime from fragments.
- [ ] No new runtime dependency.

## Test output

<!-- Paste the real output of `python -m pytest -q` and name the OS and Python version you ran it on. -->

```text
```
