# Pilot gate rehearsal — 2026-09-27

This is a technical/product review by an AI assistant. It is **not** an HR blind label, an IT/HR approval, a real-candidate shadow run, or a G1–G7 signature. Keep all gates pending until the named human owner checks the dated evidence.

## Rubric review (draft JD-BACKEND-PYTHON-001 / RUBRIC-BACKEND-PYTHON-001)

**Rehearsal verdict:** usable to test the software's evidence and scoring contract; not approved for recruitment. Six criteria map to six quoted JD requirements, weights sum to 100, and the distinction between score 0 and missing evidence is clear. Source quotes and the no-auto-rejection rule are appropriate controls.

Open decisions for HR owner and IT lead before approving G2:

1. Confirm that this draft JD describes the actual vacancy, responsibilities, and minimum requirements. The sample JD explicitly lacks employer-specific terms and has not been published by the school.
2. Calibrate the `>=70` comparable-score threshold and core floors (`python_backend`, `api_design`, `sql_data` each `>=2`) on development cases with independent reviewers. Six ordinary score-2 criteria yield only 50/100; the proposed threshold may under-flag suitable junior–middle applicants. Do not tune on the frozen holdout.
3. `require_full_coverage=true` sends every sparse CV to `needs_clarification`. Measure its coverage and workload by language; do not turn missing evidence into a rejection. HR should decide whether a missing security/privacy or operations detail can be asked at interview instead.
4. Review anchors 3–4 for the actual level of the vacancy. CVs often omit trade-offs, rollback, and incident detail even when applicants performed them. The score measures *documented evidence*, not verified skill.
5. Verify that the sanitized CV retains task, action, and result spans while removing identity, school names, age proxies, and prestige cues. A lost technical span changes the score and requires a privacy-pipeline correction, not a score override.

For each criterion, the reviewer should first record a source quote and one of `assessed`, `insufficient_evidence`, or `conflicting_evidence`; only then choose anchor 0–4 where applicable. A second reviewer should score without seeing either the first rating or the AI result. Record disagreement resolution separately from the original labels. No score supplied by this AI assistant is to be stored as `hr_blind`.

**Advisor spot-check on fictional cases, before any DeepSeek output:** these are reading checks, not benchmark labels. In `rehearsal_04`, all six criteria are `insufficient_evidence`: “Kỹ năng: Python, FastAPI, PostgreSQL, pytest, Docker, Git, bảo mật API” is only a tool list, while “không mô tả tác vụ cá nhân” confirms absent attribution. In `rehearsal_18`, `python_backend` is `conflicting_evidence` because “I alone implemented the Python payment endpoint” and “I did not write any Python or backend code” refer to the same project without a timeline. In `rehearsal_28`, the previous frontend-only work and later Python endpoint are **not** contradictory; `python_backend` has narrow documented work (anchor 1), while the single missing-fields test supports `testing_debugging` anchor 1. In `rehearsal_29`, the Vietnamese and English descriptions explicitly describe one FastAPI task; count it once. In `rehearsal_30`, the portfolio URL must not be fetched or used to invent missing evidence. These checks expose the decision rules HR should confirm in calibration.

## Data source search and eligibility

| Source | What it can support | Why it cannot fill the real-shadow gate |
|---|---|---|
| [Hiring-Bias](https://github.com/re-cinq/hiring-bias), [data license](https://github.com/re-cinq/hiring-bias/blob/main/DATA-LICENSE) | One author-owned real software-engineer baseline CV, CC BY 4.0; useful for a local parser/fairness probe with attribution. | One family, from outside this university's vacancy; generated variants are not independent applicants. |
| [ssbML/resumes](https://huggingface.co/datasets/ssbML/resumes) | 4,817 English structured records, described as a mixture of anonymized real and synthetic CVs under MIT; possible exploratory parser corpus after provenance/PII inspection. | No per-record real/synthetic origin field or university-specific application context. Do not call a sampled row a verified real applicant. |
| [opensporks/resumes](https://huggingface.co/datasets/opensporks/resumes) | Over 2,400 LiveCareer résumé examples, including an `INFORMATION-TECHNOLOGY` category, declared CC0 on the mirror; possible local-only parser stress corpus after source-rights and PII review. | Mirror license alone does not establish original applicant consent or rights to relicense the source CVs. The examples are not applications to this vacancy and have no six-criterion HR labels. Do not bulk send them to DeepSeek. |
| [OpenResume](https://zenodo.org/records/14726170) | Anonymized research trajectories after access approval. | Files are restricted; use is research-only and records are trajectories, not full JD-groundable CVs. Do not download or use for operational hiring. |
| [Synthetic IT parser corpus](https://huggingface.co/datasets/sukhrobnurali/resume-parsing-vision) | 1,000 CC BY 4.0 fictional IT CVs for parser/layout robustness. | It is explicitly synthetic and English-only. |

The checked-in `fixtures/holdout_rehearsal/` has 30 **unlabeled synthetic** families: 10 `vi`, 10 `en`, 10 `mixed`. It is separate from 12 development families, hash-frozen in `manifest.json`, and useful for a workflow rehearsal. It is **not** an independent HR benchmark or the real shadow batch.

To create a real-shadow batch, collect actual applications for one approved vacancy into private storage, obtain the school's recruitment-data authorization for this exact flow, record source/version hashes, and withhold AI output until HR and IT reviewers submit their first ratings. Keep raw CVs, labels, and AI predictions out of Git. If fewer than 30 real families arrive, report the actual number; never fill the shortfall with copied, translated, or synthetic variants while claiming G5 pass.

## DeepSeek and operations review

- As checked on 2026-09-27, no key was present in the process environment or common repo `.env` paths. An ignored, mode-600 repo `.env` template was created locally for the user to edit; it is not committed. `LLM_PROVIDER=deepseek`, `DEEPSEEK_API_KEY=...`, and `DEEPSEEK_MODEL=deepseek-flash` are needed before `PYTHONPATH=services/backend .venv/bin/python scripts/run_provider_probe.py` can make a *synthetic-only* live call.
- The [current DeepSeek Chat Completions documentation](https://api-docs.deepseek.com/api/create-chat-completion/) lists `deepseek-flash` and `deepseek-v4-pro`, with JSON mode. The [pricing page](https://api-docs.deepseek.com/quick_start/pricing/) lists peak rates per million tokens of $0.30/$0.006/$1.20 for Flash cache-miss/cache-hit/output and $1.32/$0.044/$3.96 for Pro. The code uses peak rates for conservative reservations; reported `cost_actual` is still an estimate, not a provider invoice. Rates and model availability require rechecking before G1.
- Backup/restore previously had a hard-coded fallback passphrase and transient plaintext dump/archive files. The scripts now require `BACKUP_ENCRYPTION_KEY` and stream SQL/tar through encryption. A restore must explicitly name the target via `RESTORE_CONFIRM_DB`, and Docker fallback requires an explicit `PG_DOCKER_CONTAINER`. SHA-256 catches accidental corruption but does not authenticate an attacker-modified archive.
- **Disposable restore rehearsal:** On 2026-09-27, the isolated container `talentscreen-codex-gate-db` exposed only port 55432. A synthetic `gate_drill_marker` row and marker blob were changed after backup, then both returned to `before-backup` after restore. Alembic finished and the deletion-ledger CLI completed with **zero records to re-purge**. The three backup artifacts were encrypted SQL (699,648 bytes), encrypted tar (10,272 bytes), and SHA manifest (165 bytes), each mode `0600`; there were no plaintext SQL/tar files in the backup directory. This verifies the basic path, not SEC-11 zombie-record recovery, load SLO, provider cost, or production restore readiness.

## Gate ledger at this review

| Gate | Status after this review | Evidence still required |
|---|---|---|
| G1 | Pending | User-supplied key, live synthetic capability probe, account billing/limits, signed current rate card and cap. |
| G2 | Pending HR/IT | Dated approval of actual JD, rubric anchors, weights, threshold and ownership. |
| G3 | Pending | Representative real vi/en/mixed CV sanitization, raw access and egress audit. |
| G4 | Partial | All 126 backend tests passed locally on migrated, isolated PostgreSQL/pgvector on 2026-09-27; [clean-checkout CI passed for code commit `dbb4d2e`](https://github.com/DucPh4t/TalentScreen-AI/actions/runs/36258196547). Technical review remains. |
| G5 | Pending | Two independent human ratings, frozen evaluation set, recorded AI predictions, disagreement/error and language analysis, actual real-shadow cases. Synthetic rehearsal does not count. |
| G6 | Partial | Basic encrypted backup/restore drill passed on synthetic DB/blob markers. Need deletion-after-backup zombie drill, rollback, load/SLO measurements, cost report, and operator sign-off. |
| G7 | Pending HR | Backend-recorded sandbox walkthrough completion and HR UAT signature. |
