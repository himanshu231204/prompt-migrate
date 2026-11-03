# Security policy

PromptMigrate is pre-1.0 alpha software. Only the latest commit on `main` receives fixes.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub:
[Report a vulnerability](https://github.com/himanshu231204/prompt-migrate/security/advisories/new).
Do not open a public issue, and do not include real credentials in the report. Describe the class of problem and the
smallest reproduction you can.

## What PromptMigrate does and does not protect

The threat model, current controls and their limits (for example, the heuristic secret scanner can miss secrets, and
`--env prod` is only a local SQLite file) are in [`docs/SECURITY.md`](docs/SECURITY.md).
