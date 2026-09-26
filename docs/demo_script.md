# TalentScreen AI — Live Demo & Presentation Script (Task B26)

This script provides an 8-minute demonstration script for showcasing the TalentScreen AI system to stakeholders and hiring committee members.

---

## Act 1: Intake & PII Sanitization (2 minutes)

1. **Open Dashboard**: Navigate to `http://localhost:3000`.
   - Log in using a dedicated sandbox Recruiter account provisioned locally; never reuse demo credentials for a pilot.
   - Notice the dark palette, environment banner ("Local Sandbox"), and absence of any external tracking.
2. **Requisition Overview**: Click **Đợt tuyển dụng** $\rightarrow$ select `Senior Python Backend Engineer`.
   - Highlight the FIFO ordering of applications (strictly ordered by `received_at`, not scores).
   - Point out that candidate names and emails are masked by default (`APP-XXXXXX`).
3. **Inspect Application Detail**: Click on candidate `APP-01`.
   - Tab 1: **Sanitization Redaction Viewer**.
   - Show side-by-side comparison:
     - Left: Redacted text with clear tokens `[ỨNG_VIÊN]`, `[EMAIL]`, `[SỐ_ĐIỆN_THOẠI]`, `[TRƯỜNG_ĐẠI_HỌC]`.
     - Right: Technical keywords preserved (`Python FastAPI`, `PostgreSQL`, `Docker`, `AsyncIO`).
     - Emphasize: *No personal contact info or university prestige is ever sent to external LLMs.*

---

## Act 2: Evidence-First Assessment & Quote Drawer (2 minutes)

1. Switch to Tab 2: **Evidence-First Assessment**.
   - **Key Design Point**: Note the complete absence of a giant "Hero Score" banner at the top. Evaluators must look at the evidence first before seeing aggregated numbers.
2. **Expand Criterion `python_backend`**:
   - Review AI score (e.g. 3/4).
   - Click on the quote: *"Thiết kế kiến trúc microservices xử lý 10,000 req/s..."*
   - **Quote Drawer Modal** opens instantly:
     - Displays exact character-span offsets (`start_cp`, `end_cp`).
     - Shows SHA-256 provenance hash.
     - Confirms exact codepoint equality with original normalized document.
3. **Inspect Missing Information Flags**:
   - Point out criteria where AI flagged missing metrics: *"Chưa có số liệu chứng minh hiệu năng indexing."*

---

## Act 3: HR Revision Override & Attested Decision (2 minutes)

1. Switch to Tab 3: **HR Revision & Quyết Định**.
   - As HR reviewer, identify that the candidate's GitHub open-source work demonstrates expert testing competency.
   - Adjust score for `testing_debugging` from 2 to 3.
   - Enter mandatory justification rationale: *"Đã kiểm tra repo GitHub cá nhân của ứng viên, có bộ test Pytest bao phủ 92% code coverage."*
   - Click **Ghi Đè & Tính Lại Điểm**:
     - System recalculates `comparable_score` deterministically on the server.
     - New score updates from 68.0 to 74.5 (crossing the 70-point threshold).
2. **Attested Decision (Owner Role ONLY)**:
   - Check the `ReviewAttestation` confirmation box.
   - Select outcome: **advance** (Chuyển sang phỏng vấn kỹ thuật).
   - Click **Ký Attestation & Lưu Quyết Định Tuyển Dụng**.
   - Show that the decision is now frozen and immutable.

---

## Act 4: Interview Guide & Sandbox Simulation (2 minutes)

1. Switch to Tab 4: **Interview Guide**.
   - Point out the 6 immutable Core Questions derived from the approved Requisition Question Bank.
   - Show candidate-specific Follow-up Questions (max 3) tailored directly to the missing evidence flags identified during screening.
2. **Sandbox Huấn Luyện**:
   - Navigate to `/sandbox` from the top navigation bar.
   - Walk through the 5 interactive training scenarios designed for new HR evaluators.
   - Complete a step to demonstrate instant progress tracking and feedback.
3. **Admin Observability**:
   - Show `/api/v1/admin/readiness` returning `{"status": "ready", "database": true, "storage": true}`.
   - Show `/api/v1/admin/metrics` returning SLI status, queue latencies, and daily budget usage.

---

## Concluding Message

> *"TalentScreen AI shows an evidence-first workflow for HR review. Throughput, fairness, privacy and agreement with HR still require measured pilot evidence; human reviewers retain final decision authority."*
