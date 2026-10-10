# TalentScreen AI — Pilot Calibration, Shadow Evaluation & Gate Verification Runbook (Task B25)

## 1. Overview & Principles

Before deploying TalentScreen AI in an assisted pilot with real candidate applications, the system must undergo **HR Calibration** and **Shadow Evaluation**.

### Core Guarantees & Non-Negotiables
1. **Zero Automated Hiring Decisions**: AI output is strictly assistive. Requisition Owner must review, attest, and decide every outcome.
2. **Double-Blind Calibration**: In calibration and shadow phases, human reviewers score applications **prior to** viewing AI outputs. This prevents confirmation bias.
3. **Disaggregated Accuracy**: Metric reports must disaggregate performance across languages (`vi`, `en`, `mixed`) and detect any divergence.
4. **Data Isolation**: Shadow data runs under the same strict privacy controls (PII redaction, raw grant approvals, budget caps) as production.

---

## 2. HR & IT Collaboration Sessions (H1 — H5)

| Session | Focus | Duration | Attendees | Key Deliverables |
|---|---|---|---|---|
| **H1 — Week 1** | Rubric & Criteria Review | 60–90 min | HR Owner + IT Lead | Approved 6 canonical criteria, threshold (70) and core floor (2) definition |
| **H2 — Week 3** | Calibration on Fixtures | 2–3 hours | HR Reviewers (Blind) | Independent ratings recorded before viewing AI; disagreement arbitration |
| **H3 — Week 5/6** | Holdout Evaluation Batch | 2–4 hours | HR Reviewers + Evaluation Lead | Disaggregated evaluation report on 30 frozen families |
| **H4 — Week 7** | Shadow Batch & UAT | 60–90 min | HR Council | Assisted workflow walkthrough; error analysis; pilot readiness vote |
| **H5 — Week 8** | Release & Handoff | 45–60 min | Stakeholders & Ops | Final release sign-off, rate card confirmation, operations handover |

---

## 3. Independent Blind Scoring Protocol (Shadow Mode)

During the Shadow Evaluation phase:
1. Candidate CVs are ingested and sanitized through normal privacy pipelines.
2. The AI background assessment job runs asynchronously in shadow mode.
3. **UI Blinding is a pending implementation gate**: The current review workspace displays AI results; use a separate HR annotation form or controlled paper workflow before opening it. Do not call the current UI a blind-review tool.
4. Once the human reviewer submits their score, the system reveals the comparative delta:
   - Difference in comparable score ($\Delta = |Score_{HR} - Score_{AI}|$)
   - Discrepancies in criterion anchors
   - Missed evidence spans identified by either party
5. The evaluation lead compiles Cohen's Kappa ($\kappa$) on advance recommendations and Mean Absolute Error (MAE) on criterion scores.

---

## 4. Stage-Gate Verification Matrix (G1 — G7)

Before moving from Sandbox $\rightarrow$ Real Shadow $\rightarrow$ Assisted Pilot, attach dated evidence and an HR/IT sign-off for every applicable gate. `PENDING_EVIDENCE` is not PASS. The school has approved use of DeepSeek. A single synthetic API capability probe succeeded on 2026-09-27 local time (key-free evidence: `private_storage/eval/deepseek_probe_2026-09-27.json`); account limits, rate card, budget cap and application-level integration still need verification. The application remains configured with `LLM_PROVIDER=mock`.

| Gate | Category | Required Evidence | Disallowed Shortcuts | Status |
|---|---|---|---|---|
| **G1** | Permissions & Config | DeepSeek permission, valid key, live capability probe, current rate card and budget cap | Merely having API key | **PARTIAL: SYNTHETIC API PROBE PASS; ACCOUNT, BUDGET AND APP INTEGRATION PENDING** |
| **G2** | Business Policy | Dated HR Owner & IT approval of the JD, rubric criteria, weights and thresholds | Seed rubric or one AI acting in both roles | **PENDING_HR_IT** |
| **G3** | Privacy & Data | Sanitization review on representative vi/en/mixed CVs, raw grant and egress audit | Unit tests alone | **PENDING_EVIDENCE** |
| **G4** | Technical Invariants | Clean-checkout CI and local test reports, including concurrency and recovery | Commit message claiming tests pass | **PARTIAL: 131 ISOLATED BACKEND TESTS + BRANCH CI + INTEGRATED NEXT.JS BUILD PASS; 3/30 INITIAL SYNTHETIC CONTRACT FAILURES PASSED KNOWN-CASE RERUN; SCORING AND REAL-CV FLOW PENDING** |
| **G5** | Evaluation Quality | Independent JD-derived retrieval judgments and HR/IT blind rubric labels, adjudication, candidate/JD-disjoint holdout, separated retrieval and assessment metrics, and error audit | Synthetic scenario expectations, same-CV query/evidence, or self-comparison | **PENDING_DATA** — follow the [independent human-labeled evaluation protocol](../evaluation/independent-human-evaluation-design.md) |
| **G6** | Operations | Measured load/SLO and cost report, dated restore/delete/rollback drill artifacts | Runbook text alone | **PARTIAL: SYNTHETIC BACKUP/RESTORE DRILL PASS; DELETE/ROLLBACK/LOAD PENDING** |
| **G7** | User Training | Backend-recorded sandbox completion and HR UAT sign-off | Offline local state | **PENDING_HR** |

---

## 5. Evaluation package and report

Use the package and CLI in the [independent human-labeled evaluation design](../evaluation/independent-human-evaluation-design.md), not the legacy `scripts/eval_harness.py` format. The package is local-only and hash-pinned; individual blind labels and the adjudicated reference are retained separately. The CLI emits only aggregate metrics. Do not commit any real CV, evidence quote, PII, candidate/JD key, annotation, prediction, or private output to Git.

Retrieval and rubric assessment are separate tasks with separate denominators. `not_evidenced` remains a null score and must not be counted as a zero. A metric is not a gate pass: reviewers inspect disagreements, approve thresholds before holdout, and sign each gate themselves. No new independent HR/IT evaluation has run yet.
