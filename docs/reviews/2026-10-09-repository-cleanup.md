# Repository cleanup — 9 October 2026

## Scope

Removed 28 obsolete tracked files from the active checkout: the MVP handoff ZIP, root implementation diary, old release note/manifest, obsolete demo/Jev plan, and superseded planning/contract/validator artifacts. Five artifacts from the retired bundle remain at useful locations:

- Three byte-identical optional runtime examples under `fixtures/seeds/`: JD, draft rubric, and draft interview bank.
- Two dated policy proposals under `docs/evaluation/legacy-mvp-*.md`, retained because the legacy benchmark profile cites their thresholds. They are explicitly historical, not current setup instructions or readiness approvals.

Runtime loaders, Docker COPY, synthetic/deployment smoke scripts, and benchmark source references point to the new locations. Generated release manifests now go under ignored `reports/releases/`, not a root release directory. Docker context excludes local worktrees, reports, dependencies, and private data; only the synthetic seed subtree is admitted from fixtures.

Existing README improvements were preserved. Current evaluation fixtures, measured reports, readiness runbooks, migrations, source/tests, and RAG/agent design history remain. No private storage, credentials, ignored run artifacts, or unrelated worktree changes were deleted. This removes files from the checkout; it does not rewrite Git history.

## Verification

- Two runtime-layout seed tests observed failing with `FileNotFoundError` against the old loader, then passing after relocation. A preliminary test had incorrect draft-status expectations; that test was corrected before the meaningful RED run.
- Related isolated PostgreSQL regression: 22 cases passed.
- Full `make test`: **508 backend passed, one opt-in real-E5 skip; 23 frontend passed; Next.js production build/typecheck successful, eight static pages generated**. Existing Starlette 413 deprecation warning remains. No paid provider calls or cloud traces.
- All three relocated examples have identical SHA-256 values before/after cleanup.
- Affected documentation: 68 local links/images/anchors checked; changed Python source compiles; `git diff --check` clean.
- Static prompt checks passed; generated `cleanup-check` manifest was written to ignored `reports/releases/`.
- Docker exclusion smoke passed using the actual `.dockerignore`, copied public seeds, and synthetic markers only. The direct root `COPY .` probe was rejected by automatic review because secrets might enter layers/cache. The safe probe contained no actual `.env`, credentials, CVs, or private reports. Its temporary image was removed. This verifies seed/context filtering, not a full production-image build.

The removed/modified files have a recovery copy outside the repository: `/tmp/talentscreen-cleanup-before-20261009-145342.tar.gz`. Temporary files are not a durable backup; Git retains committed historical content.

No running application's database was migrated and no live provider experiment was repeated. Restart API/worker processes that loaded the old source before using the relocated seed imports. The unrelated dirty RAG-agent worktree remains untouched.
