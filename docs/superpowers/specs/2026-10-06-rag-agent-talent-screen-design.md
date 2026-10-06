# TalentScreen AI: RAG and bounded agent design

- **Date:** 2026-10-06
- **Status:** Architecture sections approved; awaiting final review of this written specification
- **Product:** TalentScreen AI
- **Audience:** HR reviewers, IT hiring reviewers, and the implementation agent
- **Implementation authorization:** This document is a design artifact. Implementation starts only after the user reviews and approves this specification and a separate implementation plan.

## 1. Product decision

TalentScreen AI will evolve its existing evidence-based CV review workflow to use real multilingual hybrid retrieval and one bounded, read-only agent. The product will emphasize verifiable RAG and useful agent behavior inside HR tasks, without restoring a general Copilot chat. HR remains responsible for every hiring decision.

The selected direction is a workflow-first product: a requisition queue, a candidate evidence review, contextual agent actions, and a comparison matrix. DeepSeek Chat is the primary assessment and agent provider. Jev 1.13 remains a separate structured shadow scorer for benchmark and explicitly enabled, cost-limited comparisons. Provider scores are never averaged into an authoritative score. The backend validates evidence and calculates rubric scores deterministically.

## 2. Current baseline and constraints

The existing repository already has requisitions, role-specific rubric drafts and approvals, PDF/DOCX intake, redaction review, evidence-validated assessment, HR score overrides and decisions, candidate comparison, interview-question support, reviewer scorecards, operations views, and a synthetic sandbox. PostgreSQL/pgvector, FastAPI, a background worker, and a Next.js interface are in place.

The current README identifies this as a sandbox/portfolio prototype, not approved for live applicant decisions. Retrieval defaults to a full-text baseline; the offline embedding implementation creates deterministic hash vectors rather than multilingual semantic embeddings. The approved design must preserve that honest status until the gates in this document are evaluated and signed off.

Constraints from the user:

- One developer, roughly one to two months for the next substantial iteration.
- Develop and verify locally first; deployment is a later phase.
- Support more than one IT role through requisition-specific JD and dynamic, approved rubrics; do not hardcode the product to Backend Python.
- DeepSeek Chat is the primary LLM. Jev is a distinct optional provider, not a DeepSeek model or an automatic tie-breaker.
- CV content, model output, retrieved passages, and tool arguments are untrusted inputs.
- Use applicant data with the institution's authorization and configured privacy controls. Do not claim legal or policy compliance solely because the application has technical safeguards.

## 3. Goals and non-goals

### Goals

1. Retrieve relevant, exact CV evidence for each approved rubric criterion using multilingual semantic and lexical search.
2. Let a bounded agent request additional evidence when the initial retrieval is insufficient, while enforcing requisition and document scope in backend code.
3. Make every AI observation traceable to a reviewed CV span and an approved rubric version.
4. Make uncertainty, missing evidence, conflicting evidence, and model disagreement visible to HR.
5. Measure retrieval quality, evidence support, score agreement, agent/tool behavior, operational reliability, fairness checks, and cost.
6. Keep HR in control, with auditability, privacy safeguards, and a reliable manual fallback.

### Non-goals

- Autonomous rejection, advancement, ranking-based exclusion, or communication with applicants.
- A general-purpose Copilot chat or unconstrained agent.
- Agent-controlled database writes, rubric changes, candidate status changes, emails, web browsing, or cross-requisition search.
- Multiple cooperating agents in this iteration.
- Claiming the product is production-ready, fair, legally compliant, or suitable for public deployment before the evidence and institutional approvals exist.
- ATS integration, automated email, interview scheduling, or public deployment as part of this architecture iteration.

## 4. Approved architecture choices

The user reviewed six design areas and approved the following choices:

1. **Overall architecture:** Extend the existing deterministic HR workflow with evidence retrieval and bounded agent actions.
2. **RAG:** Section-aware chunks, local multilingual E5 embeddings plus lexical search, Reciprocal Rank Fusion (RRF), immutable source references, fallback, and a benchmark gate.
3. **Agent:** One bounded LangGraph StateGraph using validated read-only tools; no multi-agent design.
4. **HITL, fairness, privacy, security:** Requisition-scoped access, minimized/redacted model input, explicit HR review and audit, counterfactual fairness tests, and no automated hiring decisions.
5. **Evaluation and operations:** Per-role benchmark and locked holdout, independent HR/IT labels, Jev shadow comparison with cost limits, and operational metrics.
6. **UI and readiness:** A recruitment queue plus evidence-first candidate page, contextual agent actions, compact comparison matrix, responsive UI, and readiness gates before enabling AI assistance in a real hiring round.

Alternatives considered included whole-document context without retrieval, a fixed RAG chain without an agent, multiple specialist agents, chat-first UI, a minimal smoke-test-only evaluation, and enterprise SSO/KMS controls. These were not selected for this iteration due to weaker RAG/agent demonstration, unnecessary complexity, or mismatch with the agreed workflow and schedule.

## 5. System architecture and data flow

### 5.1 Layers

1. **Web application:** Next.js HR workspace for requisitions, rubric approval, intake, sanitization review, candidate evidence review, comparison, interviewer handoff, and operations status.
2. **API and authorization:** FastAPI authenticates the actor, checks role and requisition scope, validates workflow state, and creates auditable jobs. Authorization is enforced server-side for every data read and tool invocation.
3. **Workflow/orchestration:** Existing background job system executes deterministic processing. A LangGraph StateGraph is invoked only for bounded evidence assessment and contextual evidence-follow-up actions. The graph is not the authority for access or hiring decisions.
4. **Retrieval and document services:** PDF/DOCX extraction, OCR fallback, redaction, immutable source spans, section-aware chunking, local embedding generation, lexical search, dense search, and RRF fusion.
5. **Provider adapters:** DeepSeek Chat for primary structured assessment and tool use; Jev 1.13 for a separately configured shadow scoring call. Mock remains available for tests and local development.
6. **Persistence and audit:** PostgreSQL and pgvector store requisitions, rubric/document versions, source span metadata, chunks and embeddings, jobs, assessments, reviewer changes, and minimized audit events. Original and sanitized files remain under the existing private storage policy.

### 5.2 Candidate assessment flow

1. HR creates or selects a requisition, enters a real JD, and drafts the role-specific rubric. The authorized HR and technical reviewers approve the JD and rubric version before assessment.
2. HR uploads a supported CV. The intake pipeline validates file type/size, extracts text, records page/offset spans, flags extraction/OCR quality, and creates a redacted version.
3. HR reviews and approves the redacted version before any external LLM call. This approval is per document version; low confidence or detected residual identifiers require manual correction.
4. The indexing worker chunks the approved redacted text by logical section and creates local embeddings and lexical indexes tied to the immutable sanitized document version.
5. An authorized HR reviewer requests assessment. The API snapshots the approved JD/rubric/document versions and creates a job.
6. Retrieval runs per criterion with strict requisition and document-version filters. The agent receives only the permitted rubric and retrieved evidence references/text.
7. DeepSeek returns validated structured criterion observations or requests a bounded read-only tool call for more evidence. The server runs the retrieval tool under the original authenticated scope and limits further calls.
8. Backend validation checks schema, criterion IDs, evidence references/quotes, missing-evidence semantics, policy constraints, and score bounds. Backend code calculates weighted scores and advisory summaries from the approved rubric; model output does not calculate or choose a hiring outcome.
9. Optional Jev shadow assessment runs only when explicitly enabled for the evaluation cohort and budget. It is stored separately and does not alter the DeepSeek result or backend score.
10. HR reviews evidence, uncertainty, provider disagreement, and score. HR may override with a reason and records the final decision. Every state transition requiring a hiring decision is performed by an authorized human.

### 5.3 Failure behavior

- Parse/OCR uncertainty, low retrieval coverage, provider outage, invalid JSON, invalid citation, or failed authorization produces a visible not-ready/failed state; it must not produce a fabricated low score.
- Retry only transient provider errors once, with a per-job retry budget. Do not retry invalid content or permission failures.
- Offer HR a manual review path from the original workflow. Never silently substitute mock output in a live workflow.
- If the source document or approved rubric changes, invalidate downstream retrieval/assessment caches by version and require a new assessment.

## 6. RAG design

### 6.1 Corpus and authorization boundary

Index only the HR-approved sanitized document version and approved JD/rubric context. The original CV is not embedded or sent to an external model. Every dense and lexical query must filter by the authenticated requisition, candidate/application, sanitized document version, and approved rubric snapshot. The application must not retrieve evidence from another candidate or requisition, even if the model requests it.

### 6.2 Chunking and provenance

- Split by logical sections/headings when available (experience, projects, skills, education, certifications); preserve section boundaries and do not combine unrelated sections merely to fill a chunk.
- Target 250–350 model tokens per chunk; hard maximum 480 tokens. Use small within-section overlap only where needed to retain sentence context.
- Preserve canonical source span IDs, exact offsets, page numbers, section labels, document-version ID, and a content hash. Retrieved excerpts must map back to these immutable source references.
- Treat headings and layout as hints, not proof. For scanned or poorly extracted pages, surface extraction quality and require manual source inspection.

### 6.3 Embeddings and retrieval

- Use `intfloat/multilingual-e5-base` locally for Vietnamese, English, and mixed-language CV content. Use the model's required `query:` and `passage:` prefixes consistently. Record model/version and preprocessing version with each vector.
- Keep the vector model local to avoid sending CV text to another embedding provider. Provide a deterministic test double only in tests; never describe test-double vectors as semantic retrieval.
- Use lexical retrieval alongside vector retrieval so exact technical terms, versions, acronyms, and library names remain findable.
- Build a criterion query from approved criterion name, description, anchor wording, and HR/IT-approved bilingual synonyms. Do not ask the model to invent synonyms during a live query.
- Retrieve up to 10 lexical and 10 dense candidates per criterion and fuse ranks with RRF. Cap the initial assessment context at four evidence chunks per criterion after deduplication and diversity by source section.
- Do not add a reranker in the first implementation. Reconsider it only if the benchmark shows RRF is insufficient and the latency/cost gain is justified.
- Keep the configured `full_text_baseline` or manual path available until the new multilingual retrieval passes the benchmark gate.

### 6.4 Retrieval fallback and evaluation

When retrieval returns no reliable evidence, mark the criterion as insufficient evidence and offer an HR follow-up question. The agent may search again only for named criteria and only within the same authorized snapshot. Evaluate Recall@5/10, evidence precision, citation validity, duplicate evidence rate, and retrieval latency on human-labeled evidence queries per job family.

## 7. Agent design

### 7.1 One bounded agent, deterministic graph

Implement one LangGraph StateGraph in the backend worker. The graph combines deterministic nodes with LLM calls and has explicit transitions and a bounded state. It is a tool-using workflow agent, not an autonomous hiring agent and not a set of independent agents.

Proposed graph:

`authorize_and_snapshot -> initial_retrieval -> assess_evidence_coverage -> structured_assessment -> [optional retrieve_more_evidence, max 2 calls] -> validate_and_score -> audit_and_return`

The optional loop is allowed only when one or more criterion IDs lack adequate evidence or have a material evidence conflict. The model cannot force a loop after the graph's call budget is exhausted.

### 7.2 Tool policy

Allow only these read-only tools in this iteration:

- `retrieve_more_evidence(criterion_ids, query_hint)`: criterion IDs must belong to the approved rubric snapshot; query hint is length-limited and sanitized; server executes hybrid retrieval in the already authorized candidate/requisition/document scope.
- `get_source_spans(span_ids)`: returns only authorized exact source excerpts and page/offset metadata referenced by the current job.

The model must not choose candidate IDs, requisition IDs, storage paths, SQL, URLs, or provider credentials. Server-side graph state supplies those values. No write, status update, email, file export, internet, or cross-candidate comparison tool is exposed to the agent.

### 7.3 Output contract

Use Pydantic models and a strict JSON Schema at the application boundary. Each criterion observation contains:

- approved `criterion_id`;
- `score` in the approved 0–4 scale or `null` when evidence is insufficient;
- one or more `evidence_span_ids`;
- concise explanation grounded only in those spans;
- uncertainty/conflict flags and a missing-evidence explanation where applicable;
- suggested verification question when appropriate.

Do not accept a model-provided overall score, hiring decision, candidate rank, or state transition. The backend calculates weighted totals using the immutable approved rubric. Validate every quote/reference against stored source spans; reject unsupported or malformed fields and show a failure state.

### 7.4 Prompt and trace management

- Treat prompt templates as versioned source code. Store prompt ID/version, provider/model, schema version, retrieval configuration, rubric version, and document version with each assessment.
- Maintain regression fixtures for Vietnamese, English, mixed-language CVs, missing evidence, conflicting evidence, prompt injection in CV text, invalid citations, invalid JSON, and tool-boundary violations.
- Run prompt changes against the same versioned evaluation set before release; support rollback to the last approved prompt version.
- Do not send raw CV text, secrets, or applicant-identifying values to hosted observability/tracing services. Persist graph checkpoints as IDs, hashes, references, and minimized metadata, not raw CV passages. Keep needed excerpts in the protected application store.

## 8. HITL, fairness, privacy, and security

### 8.1 Human authority and UI

- AI output is advisory. No automated reject/advance action, no automatic applicant communication, and no hiring decision inferred from a score threshold.
- HR reviews each criterion and its source evidence. Missing evidence is explicitly `null`/“chưa đủ bằng chứng”, not zero.
- HR can revise an observation/score with a reason and can make any final decision permitted by institutional policy. Record the actor, time, previous and new values, reason, and source assessment version.
- Show DeepSeek and Jev outputs separately. A disagreement is a review signal, not a vote or a way to average model scores.

### 8.2 Fairness controls

- Reject prohibited demographic and proxy rubric criteria at rubric validation and again at assessment validation. Exclude name, age, gender, hometown, photo, and school identity from model assessment. Permit credentials only when a specific credential itself is job-related and explicitly stated in the approved rubric; school prestige/identity is never a criterion.
- Keep candidate identity separate from assessment content. Use anonymized candidate IDs in queue and comparison views by default; identity access is role-gated and audited.
- Require every criterion score to have relevant evidence and explain the anchor match. Missing evidence cannot lower a score by default.
- Add synthetic paired counterfactual tests that change irrelevant names, pronouns, hometowns, and school identities while holding qualifications fixed. Assessment evidence, score, and ranking must remain invariant within an agreed tolerance; any difference is a release blocker until explained and fixed.
- Do not collect or infer sensitive-group labels just to claim statistical fairness. Any group fairness analysis on real applicants requires institutional approval, a lawful data basis, and a documented purpose.

### 8.3 Privacy, access, and security

- Enforce role- and requisition-scoped authorization in API, retrieval SQL/vector filters, file access, and agent tools. Never trust an ID supplied by a model or browser without rechecking ownership/scope.
- Require sanitization review before external provider calls. Send only the minimum excerpts needed for the current criteria. Keep provider keys in secrets/environment configuration, never client bundles or logs.
- Encrypt transport and protected storage according to the deployment environment. Use short-lived, authorized file access links. Keep raw/original CV access restricted and audited.
- Treat CV text as untrusted prompt content. Delimit it as data, instruct the model not to follow embedded instructions, validate every tool call, and test indirect prompt-injection attempts.
- Audit actor, purpose, requisition/application/document/rubric versions, provider/model/prompt/schema versions, tool names and sanitized arguments, retrieved span IDs/hashes, validation outcomes, score revisions, and final HR actions. Do not place raw CV, secrets, or full prompts in ordinary logs.
- Define retention per institution and requisition. A verified deletion request must remove or schedule purge of original and sanitized files, extracted text, chunks, vectors, cached assessments, and derived artifacts. Keep only minimized audit metadata where policy permits. Include backup expiry/purge replay in the operational drill.
- Before live use, institution owners must confirm data-processing terms, provider configuration, applicant notices/legal basis, and any cross-border processing requirements. Technical safeguards alone do not establish legal compliance.

## 9. UI and user journey

Use the existing Next.js application and extend the HR workflow; do not restore the removed general Copilot chat.

1. **Recruitment queue:** requisition, role, intake volume, processing/sanitization/assessment states, reviewer assignment, and failures needing attention. Show candidate codes and job-related status, not demographic details.
2. **Candidate evidence page:** concise advisory summary; per-criterion score or insufficient-evidence state; anchor used; exact citation excerpt with page/section; extraction confidence; conflicting evidence; HR edit/override controls and reason; separate provider disagreement panel.
3. **Contextual agent actions:** “Tìm thêm bằng chứng” for selected criteria, “Giải thích tiêu chí” using cited evidence, and “Soạn câu hỏi phỏng vấn” tied to evidence gaps. Each action shows progress, source references, completion/failure, and whether it used another retrieval call. No open-ended chat surface.
4. **Comparison matrix:** compare evidence and criterion scores across candidates for one requisition, with sorting that cannot automatically exclude applicants. Every cell opens its evidence. Ensure horizontal scrolling or a usable responsive layout on small screens.
5. **Decision capture:** HR records advance/hold/reject/other permitted action and reason. AI recommendation cannot trigger the transition. Record overrides without treating them as automatic training labels.
6. **Onboarding:** short first-use walkthrough distinguishing evidence observation from absolute ability, score from decision, and missing evidence from low score. Provide synthetic sandbox scenarios without real candidate information.
7. **Accessibility and responsive behavior:** keyboard-accessible controls, clear status labels, readable evidence at mobile widths, loading/empty/error states, and no color-only meaning.

## 10. Evaluation, readiness gates, and error budget

### 10.1 Dataset and protocol

- Build an evaluation set by job family, with approved real or synthetic JD/rubric and CV data. The eight currently available mixed-role CVs can verify ingestion and end-to-end integration but cannot establish per-role accuracy, agreement, or fairness.
- HR and an IT-domain reviewer label criteria independently using the approved anchors and source evidence. Adjudicate disagreements and measure human-to-human agreement before interpreting AI-human agreement.
- Freeze a holdout set before prompt/retrieval tuning. Separate prompt regression/development samples from holdout. Record dataset version, label provenance, consent/authorization status, prompt/model/retrieval versions, and exclusions.
- Run DeepSeek as primary and Jev as a separate shadow comparison on the agreed benchmark. Do not train prompts against the locked holdout and do not average model scores.

### 10.2 Metrics

- **Retrieval:** Recall@5 and Recall@10 against labeled evidence, evidence precision, duplicate rate, retrieval latency.
- **Grounding:** citation-to-span validity (must be 100% for accepted assessments), supported-claim rate, unsupported-claim rate, and missing-evidence correctness.
- **Scoring:** criterion-level MAE on 0–4 scores, weighted agreement with HR/IT, human-to-human agreement, rank correlation as a diagnostic, disagreement/override rates with reason categories. Agreement is a review metric, not a target to copy historical bias.
- **Agent:** useful additional-retrieval rate, unnecessary-call rate, tool argument/schema errors, max-loop enforcement, unauthorized-access denials, prompt-injection resistance.
- **Fairness:** paired counterfactual invariance and rubric proxy checks; group metrics only with an approved data basis.
- **Operations:** P50/P95 end-to-end latency, extraction/OCR failure rate, provider timeout/error rate, manual-fallback rate, cost per CV and per requisition, retry count, deletion completion and backup-purge drill results.

### 10.3 Hard release gates

Before AI-assisted recommendations are enabled in a real hiring round:

1. All accepted evidence references resolve to the correct immutable source span; otherwise the assessment is blocked.
2. Automated tests prove the agent cannot access another requisition/candidate or perform a write/decision action.
3. Prompt-injection, invalid-output, missing-evidence, and counterfactual test suites pass.
4. HR and IT approve each active JD/rubric; HR and IT labels exist for a locked holdout for each enabled job family.
5. Agreement/quality thresholds are written down and approved by the reviewers before holdout evaluation. Initial candidate thresholds (e.g. retrieval Recall@5 ≥ 0.85, criterion MAE ≤ 0.5/4, weighted agreement ≥ 0.60) are proposals to calibrate against human-human consistency, not claims or automatic acceptance criteria.
6. DeepSeek and Jev live calls, failure handling, data minimization, and cost are tested on authorized data and within a per-requisition budget.
7. HR rehearses override, manual fallback, applicant deletion, access review, and incident handling; provider processing and institutional privacy/legal review are documented.
8. Product copy, onboarding, and UI consistently state that AI provides evidence-based recommendations and HR decides.

### 10.4 Provisional internal SLO/error budget

Initial targets for local and staging rehearsal, to be validated against actual hardware/cloud setup before sign-off:

- At least 95% of supported text-based PDF/DOCX CVs complete extraction and redaction draft within 2 minutes of upload under the agreed test load. Separately, at least 95% of approved assessment jobs complete initial assessment within 2 minutes of enqueueing; report queue wait and model time separately.
- At least 95% of supported scanned CVs complete OCR and extraction within 5 minutes of upload; otherwise show a clear retry/manual-review path.
- Supported-format extraction failure rate below 5% on the labeled test corpus; report OCR separately from digitally generated files.
- 100% of provider or validation failures produce an explicit failed/manual-review state and never a silent mock result or fabricated score.

Track these weekly during early operation. If latency/error targets are exceeded, pause automatic assessment enqueueing for the affected provider or file class and route new work to manual review until recovered. These targets are internal starting points, not external uptime guarantees.

## 11. Cost and resource controls

- Generate embeddings locally and only once per immutable sanitized document version; cache by content/model/preprocessing hash and delete with the source lifecycle.
- Send retrieved evidence rather than the entire CV to DeepSeek. Keep prompts compact and cap context by the RAG limits above.
- Enforce at most three normal DeepSeek model round trips per candidate assessment: the model can request a first read-only retrieval, receive its result and request one more, then return the final structured response. This allows at most two tool executions; if no tool is needed, the model returns the structured response immediately. Allow at most one retry overall for a transient provider failure, so no assessment can exceed four outbound attempts. Tool executions remain capped at two even if a provider response is retried.
- Jev is off by default and limited to locked benchmark/shadow cohorts or a specifically configured sample and budget. It must never run without the required institutional approval and provider credentials.
- Record token usage, provider, model, request purpose, latency, retry, and estimated cost per assessment. Configure a hard cost ceiling per requisition and stop optional shadow calls when the ceiling is reached.
- Limit worker concurrency and request rate; use circuit breakers for provider outages. Do not lower evidence or safety validation to save cost.

## 12. Go-live sequence

This is a readiness-gated release, not a separate live-applicant pilot. Synthetic sandbox use supports HR training; real applicant assessment is enabled only after all release gates pass.

1. Implement and locally verify semantic embeddings, hybrid retrieval, bounded agent tools, validation, audit, and UI integration.
2. Run mock-provider regression and security tests; fix failures before live-provider evaluation.
3. Obtain reviewer-approved, role-specific JD/rubric and labeled development/locked holdout sets for each intended job family.
4. Run DeepSeek primary and Jev shadow evaluations with authorized data; inspect every disagreement and record costs/latency.
5. Rehearse operations with synthetic data and test deletion/backup purge; complete institutional provider/privacy review.
6. Product owner, HR owner, and IT reviewer sign the readiness record. Then enable AI-assisted review for approved requisitions with human final decisions, manual fallback, audit monitoring, and an immediate disable switch.

## 13. Acceptance criteria for the implementation plan

The later implementation plan should be considered complete only when it delivers:

- Real multilingual E5 embeddings and tested section-aware chunking/provenance.
- Hybrid dense + lexical retrieval with RRF, strict authorization filters, source-span citations, and manual/full-text fallback.
- A bounded LangGraph assessment workflow with no more than two evidence follow-up tool calls, server-enforced scope, validated JSON/Pydantic outputs, prompt versioning, and rollback.
- Separate DeepSeek primary and optional Jev shadow results; deterministic backend scores; no AI-controlled hiring action.
- HR evidence review, contextual agent controls, candidate comparison, reasoned override/final-decision audit, and responsive accessibility checks.
- Fairness/privacy/security tests and data deletion/retention drills.
- Versioned role-specific benchmark, locked holdout report, HR/IT agreement analysis, operating metrics, and cost report.
- Updated setup/runbook/onboarding material and truthful README status that does not imply live-readiness before sign-off.

## 14. Decisions still required during implementation planning

These details should be resolved with the current code and reviewers when converting this design to a task plan:

1. Exact active job families and the owners who approve each JD/rubric.
2. Label-set size and holdout composition per job family; eight mixed-role CVs are integration smoke data only.
3. Final agreement and retrieval thresholds after human-human baseline measurement.
4. Institution-specific retention periods, deletion deadline, backup purge interval, provider contract/region, and approved data classes.
5. The measured latency/cost envelope on the selected local and later deployment hardware.
6. Whether a graph persistence library is necessary for the first iteration; if used, checkpoint only minimized identifiers/references and test deletion semantics.

## 15. References

- DeepSeek tool calls: https://api-docs.deepseek.com/guides/tool_calls/
- Multilingual E5 model card: https://huggingface.co/intfloat/multilingual-e5-base
- LangGraph overview and human-in-the-loop/persistence concepts: https://docs.langchain.com/oss/python/langgraph/overview
