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

Before moving from Sandbox $\rightarrow$ Real Shadow $\rightarrow$ Assisted Pilot, attach dated evidence and an HR/IT sign-off for every applicable gate. `PENDING_EVIDENCE` is not PASS. The school has approved use of DeepSeek, but account configuration, budget, provider probe and operating procedures still need verification.

| Gate | Category | Required Evidence | Disallowed Shortcuts | Status |
|---|---|---|---|---|
| **G1** | Permissions & Config | DeepSeek permission, valid key, live capability probe, current rate card and budget cap | Merely having API key | **PENDING_EVIDENCE** |
| **G2** | Business Policy | Dated HR Owner & IT approval of JD, six rubric criteria, weights and thresholds | Seed rubric only | **PENDING_HR_IT** |
| **G3** | Privacy & Data | Sanitization review on representative vi/en/mixed CVs, raw grant and egress audit | Unit tests alone | **PENDING_EVIDENCE** |
| **G4** | Technical Invariants | Clean-checkout CI and local test reports, including concurrency and recovery | Commit message claiming tests pass | **PARTIAL: 126 LOCAL TESTS PASS; NEW BRANCH CI/TECHNICAL REVIEW PENDING** |
| **G5** | Evaluation Quality | Independent HR labels, recorded AI predictions, frozen holdout of 30 families and real-shadow report. Draft targets for HR/IT approval: conditional MAE ≤0.75/4, human-assessable coverage ≥85%, linear weighted kappa ≥0.60, with error audit | Synthetic scenario expectations or self-comparison | **PENDING_DATA** |
| **G6** | Operations | Measured load/SLO and cost report, dated restore/delete/rollback drill artifacts | Runbook text alone | **PARTIAL: SYNTHETIC BACKUP/RESTORE DRILL PASS; DELETE/ROLLBACK/LOAD PENDING** |
| **G7** | User Training | Backend-recorded sandbox completion and HR UAT sign-off | Offline local state | **PENDING_HR** |

---

## 5. Shadow Evaluation Report Template

After HR reviewers label cases before viewing AI outputs, export only pseudonymous IDs, rubric scores, recommendations and run metadata to private JSONL files described in `docs/evaluation-data-contract.md`. Never commit real candidate labels or predictions. Run:
```bash
.venv/bin/python scripts/eval_harness.py \
  --predictions private_storage/eval/ai_predictions.jsonl \
  --labels private_storage/eval/hr_blind_labels.jsonl \
  --split real_shadow \
  --output private_storage/eval/shadow_report.json
```

The report records matched and missing counts, conditional MAE, human-assessable coverage, linear weighted kappa on 0..4 scores, recommendation agreement, language breakdown and observed usage when supplied. `gate_eligible` is a data-completeness hint, **not** an approval. Human reviewers must inspect error cases and sign the gate. Do not label a group with no comparable scores or an undefined kappa as PASS.
