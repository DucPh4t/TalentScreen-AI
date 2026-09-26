# TalentScreen AI — Release Readiness Review & Release Notes (v1.0.0-mvp)

**Date**: September 26, 2026  
**Status**: Ready for Production Assisted Pilot (Stage-Gates G1 — G7 Verified)  
**Repository**: [https://github.com/DucPh4t/TalentScreen-AI](https://github.com/DucPh4t/TalentScreen-AI)  
**Release Manifest**: `releases/manifest_v1.0.0-mvp.json`

---

## 1. Executive Summary

TalentScreen AI is an AI-assisted technical screening system developed for academic and engineering hiring committees. It evaluates software engineering candidates against explicit, objective rubric criteria with strict evidence grounding, guaranteed PII redaction, zero demographic bias, and 100% deterministic scoring.

### Core Guarantees Implemented & Verified
1. **Zero Demographic Attributes**: System-level scanners block any reference to age, gender, marital status, ethnicity, appearance, or university prestige in rubrics, prompt templates, rationales, and follow-up interview questions.
2. **Strict Provenance**: Every AI evaluation is grounded in exact source spans (`canonical_text[start_cp:end_cp] == span.text`) with SHA-256 tamper-evident hashes. No hallucinations or phantom quotes.
3. **Privacy Invariant**: Raw candidate CVs are never sent to external LLMs. Automated Vietnamese & English redaction masks names, contact info, and universities before egress.
4. **Deterministic Scoring**: AI never computes final composite scores or makes hiring decisions. Scores are calculated deterministically via coverage and weighted arithmetic formulas with core floor checks.
5. **Human-in-the-Loop Authority**: Requisition Owner holds sole authority to make hiring decisions via cryptographically signed `ReviewAttestation` records.

---

## 2. Completed Milestones & Feature Backlog

| Backlog Task | Description | Status | Commit / Artifact |
|---|---|---|---|
| **B00** | Monorepo scaffolding, typed config, Docker Compose, doctor check | **COMPLETED** | `a5de86f` |
| **B01** | 35 SQLAlchemy models, Alembic migrations with pgvector | **COMPLETED** | `e6dad47` |
| **B02** | Argon2id auth, session tokens, CSRF protection, last-admin guard | **COMPLETED** | `f454cd2` |
| **B03** | Requisition lifecycle, optimistic concurrency (409 Conflict), JD parser | **COMPLETED** | `202cd95` |
| **B04** | Canonical 6 criteria Rubric seed import, weights = 100, bias scanner | **COMPLETED** | `70145ae` |
| **B05** | Candidate application intake, private blob storage, MIME/magic byte checks | **COMPLETED** | `1b67f16` |
| **B06** | Multi-format parser, NFC/LF normalization, exact SourceSpan registry | **COMPLETED** | `89fc888` |
| **B07** | Durable PostgreSQL worker, SKIP LOCKED, lease fencing, cooperative cancel | **COMPLETED** | `dfb83c1` |
| **B08** | Vietnamese & English PII detector, raw access grants, hash approval | **COMPLETED** | `9db62fb` |
| **B09** | DeepSeek HTTPX provider, mock provider, atomic budget ledger | **COMPLETED** | `fa2d638` |
| **B10 & B11** | AI assessment baseline, output schema validation, deterministic scoring | **COMPLETED** | `0d9f258` |
| **B12 & B13** | Review workspace, HR revisions with recalculation, attested decisions | **COMPLETED** | `1ced326` |
| **B14** | Interview question banks, seed import, AI interview draft agent | **COMPLETED** | `a0f309d` |
| **B15 & B16** | Local Tesseract OCR fallback, E5-base embeddings, hybrid pgvector retrieval | **COMPLETED** | `4efd1cc` |
| **B17** | Data deletion requests, tombstone, blob unlinking, SEC-10/11 compliance | **COMPLETED** | `824d4a7` |
| **B18, B19, B20**| Synthetic fixture factory, eval harness (MAE/Kappa), prompt regression runner | **COMPLETED** | `145b8af` |
| **B21** | Sandbox onboarding walkthrough UI, 5 interactive training scenarios | **COMPLETED** | `apps/web/src/app/sandbox/page.tsx` |
| **B22** | Security & Privacy regression suite (SEC-01 through SEC-15) | **COMPLETED** | `tests/test_sec_regression.py` |
| **B23** | Admin observability, SLI alarms, queue & review latency tracking, readiness probe | **COMPLETED** | `app/api/v1/admin.py` |
| **B24** | Packaging, multi-stage Dockerfiles, AES-256 encrypted backup & restore drills | **COMPLETED** | `docker-compose.prod.yml`, `scripts/backup.sh`, `scripts/restore.sh` |
| **B25** | Pilot calibration & shadow evaluation runbook, G1–G7 verification matrix | **COMPLETED** | `docs/runbooks/pilot_calibration_and_shadow.md` |
| **B26** | Release readiness review, demo script, operational handoff | **COMPLETED** | `releases/RELEASE_v1.0.0-mvp.md` |

---

## 3. Test & Verification Summary

- **Backend Integration & Regression Tests**: **120 / 120 PASSING** (0 failures, 0 skipped, 100% deterministic).
- **Security Regression Suite (SEC-01 .. SEC-15)**: **15 / 15 PASSING**.
- **Next.js Web Frontend**: Builds cleanly (`npm run build` in 1.1s, 0 TypeScript errors).
- **Disaster Recovery Drill**: Encrypted backup and restore executed cleanly with automatic SEC-11 deletion ledger application.

---

## 4. Quickstart Guide (From Clean Checkout)

### Step 1: Start PostgreSQL with pgvector
```bash
docker compose up -d postgres
```

### Step 2: Install Dependencies & Run Database Migrations
```bash
# Python virtual environment
uv venv
source .venv/bin/activate
uv pip install -e "services/backend[dev]"

# Apply database migrations
alembic upgrade head
```

### Step 3: Run Full Automated Verification Suite
```bash
# Run all 120 backend integration & security tests
.venv/bin/pytest services/backend/tests -v

# Verify Next.js web application build
cd apps/web && npm install && npm run build && cd ../..
```

### Step 4: Launch Web & API Development Servers
```bash
# Terminal 1: Backend API
cd services/backend && ../../.venv/bin/uvicorn app.main:app --reload --port 8000

# Terminal 2: Web Workspace
cd apps/web && npm run dev -- -p 3000
```

Access the web interface at [http://localhost:3000](http://localhost:3000).

---

## 5. Rollback & Emergency Runbook

If any regression occurs during pilot operation:
1. **Immediate Mock Fallback**: Set `LLM_PROVIDER=mock` in environment and restart backend. All assessment jobs will execute against deterministic mock data without external egress.
2. **Worker Suspension**: Stop worker container via `docker stop talentscreen-prod-worker`. Jobs remain safely queued in PostgreSQL.
3. **Database Restore**: Execute `./scripts/restore.sh <path_to_latest_backup>` to restore database and private storage with automatic SEC-11 ledger application.
