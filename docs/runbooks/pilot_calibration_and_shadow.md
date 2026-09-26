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
3. **UI Blinding**: The web workspace hides preliminary AI scores and recommendations from human reviewers until their independent assessment is submitted.
4. Once the human reviewer submits their score, the system reveals the comparative delta:
   - Difference in comparable score ($\Delta = |Score_{HR} - Score_{AI}|$)
   - Discrepancies in criterion anchors
   - Missed evidence spans identified by either party
5. The evaluation lead compiles Cohen's Kappa ($\kappa$) on advance recommendations and Mean Absolute Error (MAE) on criterion scores.

---

## 4. Stage-Gate Verification Matrix (G1 — G7)

Before moving from Sandbox $\rightarrow$ Real Shadow $\rightarrow$ Assisted Pilot, the following gates must be documented and signed:

| Gate | Category | Required Evidence | Disallowed Shortcuts | Status |
|---|---|---|---|---|
| **G1** | Permissions & Config | DeepSeek agreement confirmed; valid API key; rate card verified; budget cap set | Merely having API key without budget guard | **PASS** |
| **G2** | Business Policy | HR Owner & IT approval on JD, 6 Rubric criteria, weights = 100, threshold = 70 | Unvalidated AI-drafted rubric | **PASS** |
| **G3** | Privacy & Data | PII redaction engine verified; raw grant access logs; university masking active | Unsanitized CV egress to LLM | **PASS** |
| **G4** | Technical Invariants | 120 automated tests pass (SEC-01..15, math scoring, idempotency, race conditions) | Mock UI or SQLite-only tests | **PASS** |
| **G5** | Evaluation Quality | Holdout MAE $\le 0.50$; Cohen's Kappa $\ge 0.70$; zero demographic violations | LLM-as-a-judge self-evaluation | **PASS** |
| **G6** | Operations | Encrypted backup/restore drill completed; SEC-11 deletion ledger verified | Theoretical disaster recovery plans | **PASS** |
| **G7** | User Training | HR completed 5 Sandbox Onboarding scenarios; knows how to inspect spans & override | Skimming user documentation | **PASS** |

---

## 5. Shadow Evaluation Report Template

When executing a shadow batch, generate the report using:
```bash
.venv/bin/python scripts/eval_harness.py --split holdout --output reports/shadow_report.json
```

The resulting report records:
- Evaluated candidate count
- Score MAE overall and per criterion
- Recommendation Cohen's Kappa
- Disaggregated metrics for Vietnamese vs English vs Code-switching CVs
- Token cost and provider latency percentiles
- Zero demographic bias confirmation hash
