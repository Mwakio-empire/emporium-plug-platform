# Phase 0 release-candidate evidence — 16 August 2026

## Scope and status

Release branch: `codex/delivery-quotes-controlled-stacking`

Release SHA: **pending intentional commit and push**

Exit gate: **NOT PASSED** until GitHub Actions is green on the exact release
commit and that SHA is recorded. All local gates currently pass.

## Evidence summary

| Gate | Result | Evidence |
|---|---|---|
| Business context and audit reviewed | Pass | Full 372-paragraph document and five tables reviewed; current re-audit reconciled. |
| Working tree/scope | Pass | Changes reviewed individually; no unrelated user change was overwritten. |
| Environment-key parity | Pass | `.env` and `.env.example` each contain 74 keys; no missing/extra keys and no values printed. |
| Secret-file exclusion | Pass | `.env` and `.env.docker.local` are ignored; only safe examples are tracked. |
| Django checks | Pass | Zero issues. |
| Migration drift | Pass | No changes detected on SQLite and PostgreSQL profiles. |
| Compilation/dependencies | Pass | `compileall` and `pip check` pass. |
| Vulnerability/static scans | Pass | `pip-audit`: no known vulnerabilities; npm production audit: zero; Bandit medium/high: exit 0. |
| Frontend/static assets | Pass | Production asset build passes; `collectstatic` copied 10, retained 175 and post-processed 482 files. |
| SQLite regression | Pass | 718 tests, zero failures, one expected row-lock skip. |
| PostgreSQL regression | Pass | PostgreSQL 17.10; 718 tests, zero failures, zero skips. |
| Focused critical flows | Pass | 31 PostgreSQL tests for final-unit locking, payment idempotency/polling and stock restoration; zero failures/skips. |
| Redis | Pass | Authenticated Compose Redis 7 service healthy; used by the release profile. |
| Production media default | Pass locally | Deployed settings select Cloudinary default media storage; hosted persistence is a later staging gate. |
| Demo-data safety | Pass locally | Both demo catalogue and review seed commands are blocked in production. |
| GitHub Actions | Pending | Workflow now provisions PostgreSQL 17 and Redis 7; pushed exact-SHA run not yet available. |

Initial pushed run `32122998782` on SHA
`38fafb65a0e6cd85e12c160ea34cd6757dbd2b7b` failed correctly at the dependency
audit after four 2026 vulnerabilities were reported for `sqlparse==0.5.5`.
The release was not promoted and the dependency is being upgraded to the fixed
`0.6.0` release. A new exact-SHA run is required; the failed run is retained as
evidence that the security gate is working.

## Migration risk review

No migration file changed and no migration is pending. Fresh-database migration
and the current database migration plan complete on PostgreSQL.

Historical migrations contain `AlterField`, bounded `RunPython` data conversion,
one old `DeleteModel`, and several intentionally no-op reverse functions. There
is no new destructive or table-rewrite operation in this release. The operational
consequence is that database rollback must not assume every historical migration
is reversible: take a verified backup before production migration, prefer a
forward corrective migration, and restore into an isolated target when rollback
requires reversing a data conversion.

## Production-surface review

- Payment callback routes point to implemented handlers; no placeholder lambda
  is present in production URL configuration.
- Provider integrations remain environment-selected and production settings
  reject unsafe sandbox/console combinations where required. Provider
  certification remains a later phase and is not claimed here.
- The Sentry exception trigger is an authenticated super-admin diagnostic, not a
  public debug endpoint; anonymous users are redirected and non-admin users get
  403 responses under regression tests.
- Demo commands are manual development/staging tools and now fail before mutation
  when production mode is active.

## Remaining Phase 0 actions

1. Review final diff and secret scan.
2. Commit intentionally and push the selected release branch.
3. Require GitHub Actions to pass on that exact commit.
4. Record the release SHA and CI run evidence, then mark Phase 0 PASS.
