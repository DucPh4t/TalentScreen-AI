/**
 * Typed API Client for TalentScreen AI
 * Connects to FastAPI backend via Next.js proxy rewrite at /api/v1
 */

export interface UserAccount {
  id: string;
  login_name: string;
  display_name: string;
  status: string;
  roles?: string[];
}

export interface RequisitionItem {
  my_role?: "owner" | "admin" | "reviewer" | "recruiter";
  id: string;
  title: string;
  department?: string;
  status: "draft" | "open" | "paused" | "closed";
  row_version: number;
  created_by?: string;
  current_rubric_version_id?: string;
  current_jd_version_id?: string;
  created_at: string;
  updated_at: string;
}

export interface ApplicationItem {
  id: string;
  requisition_id: string;
  candidate_id: string;
  public_label: string;
  status: string;
  generation: number;
  row_version: number;
  current_document_id?: string;
  current_sanitized_version_id?: string;
  current_assessment_run_id?: string;
  current_decision_id?: string;
  received_at: string;
}

export interface CriterionAssessmentData {
  criterion_id: string;
  status: "assessed" | "insufficient_evidence" | "conflicting_evidence";
  score: number | null;
  rationale: string;
  missing_information?: string[];
  evidence: Array<{
    span_id: string;
    quote: string;
    resolved_start_cp: number;
    resolved_end_cp: number;
  }>;
}

export interface AssessmentExecutionToolCallData {
  tool_name?: string;
  outcome?: string;
  criterion_ids?: string[];
  span_ids?: string[];
  result_count?: number;
  error_code?: string;
}

export interface AssessmentExecutionTraceData {
  retrieval_strategy?: string;
  agent_prompt_version?: string;
  assessment_prompt_version?: string;
  provider?: string;
  model?: string;
  model_round_trips?: number;
  tool_execution_count?: number;
  result_criterion_count?: number;
  outcome?: string;
  error_code?: string | null;
  tool_calls?: AssessmentExecutionToolCallData[];
}

export interface AssessmentRunData {
  id: string;
  application_id: string;
  run_no: number;
  status: string;
  strategy: string;
  execution_trace: AssessmentExecutionTraceData;
  observed_score: number | null;
  coverage: number;
  comparable_score: number | null;
  recommendation: "consider_next_round" | "needs_clarification" | "review_required" | null;
  secondary_model_output?: {
    status: "succeeded" | "failed" | "skipped_insufficient_evidence" | string;
    requested_model?: string;
    reported_model?: string;
    error_code?: string;
    evaluations?: Record<string, {
      score: number;
      confidence: number;
      probabilities: Record<string, number>;
      deepseek_score: number;
      delta_from_deepseek: number;
    }>;
  } | null;
  criteria: CriterionAssessmentData[];
  completed_at?: string;
  failure_code?: string;
}

export interface ReviewWorkspaceData {
  application_id: string;
  public_label: string;
  generation: number;
  current_document_id?: string;
  current_sanitized_version_id?: string;
  latest_run?: AssessmentRunData;
  latest_hr_revision?: any;
  latest_decision?: any;
}

export interface ReviewQueueItem {
  application_id: string;
  public_label: string;
  received_at: string;
  document_status: string;
  sanitized_status: string;
  risk_flags: string[];
  assessment_available: boolean;
  workflow_stage?: string;
  sla_breached?: boolean;
  hours_in_stage?: number;
  application_history_count?: number;
  is_duplicate?: boolean;
  duplicate_reasons?: string[];
}

export interface CandidateComparison {
  rubric_version_id: string | null;
  criteria: Array<{ id: string; label: string }>;
  candidates: Array<{
    application_id: string;
    public_label: string;
    assessment_status: string;
    coverage: number | null;
    observed_score: number | null;
    comparable_score: number | null;
    recommendation: string | null;
    criteria: Record<string, { status: string; score: number | null }>;
  }>;
}

export interface ShortlistCandidate {
  application_id: string;
  candidate_id: string;
  public_label: string;
  rank: number | null;
  tier: "recommend" | "borderline" | "below_threshold" | "core_fail" | "not_assessed";
  tier_display: string;
  comparable_score: number | null;
  observed_score: number | null;
  coverage: number | null;
  recommendation: string | null;
  strengths: string[];
  missing_criteria: string[];
  core_failed_criteria: string[];
  criteria_scores: Record<string, { label: string; score: number | null; status: string; core: boolean }>;
  has_decision: boolean;
  received_at: string | null;
}

export interface ShortlistResponse {
  requisition_id: string;
  requisition_title: string;
  rubric_version_id: string | null;
  threshold: number;
  total_candidates: number;
  assessed_candidates: number;
  shortlisted_candidates: number;
  average_score: number | null;
  tier_summary: Record<string, number>;
  criteria: Array<{ id: string; label: string; weight: number; core: boolean }>;
  candidates: ShortlistCandidate[];
}

export interface EmailDraftData {
  id: string;
  application_id: string;
  decision_id?: string | null;
  template_type: string;
  subject: string;
  body: string;
  variables: Record<string, any>;
  status: "draft" | "approved" | "invalidated";
  version_no: number;
  created_by?: string | null;
  approved_by?: string | null;
  approved_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExecutiveSummaryData {
  application_id: string;
  status: string;
  headline: string;
  summary_paragraph: string;
  key_strengths: string[];
  gaps_or_questions: string[];
  recommended_interview_focus: string[];
  recommendation_label: string;
  comparable_score?: number;
  coverage?: number;
  cached: boolean;
}


export interface IndependentReviewContext {
  requisition_id?: string;
  application_id: string;
  public_label: string;
  application_generation: number;
  document_id: string;
  sanitized_version_id: string;
  rubric_version_id: string;
  sanitized_text: string;
  criteria: Array<{ id: string; label: string; description: string; anchors: Record<string, unknown> }>;
  already_submitted: boolean;
  enforced_blind: boolean;
}

// Global CSRF token cache
let cachedCsrfToken: string | null = null;
const csrfStorageKey = "talentscreen_csrf_token";

export function setCsrfToken(token: string) {
  cachedCsrfToken = token || null;
  if (typeof window !== "undefined") {
    if (token) window.sessionStorage.setItem(csrfStorageKey, token);
    else window.sessionStorage.removeItem(csrfStorageKey);
  }
}

export function getCsrfToken(): string | null {
  if (cachedCsrfToken) return cachedCsrfToken;
  if (typeof window !== "undefined") {
    const stored = window.sessionStorage.getItem(csrfStorageKey);
    if (stored) {
      cachedCsrfToken = stored;
      return stored;
    }
    const cookie = document.cookie.match(/(?:^|;\s*)talentscreen_csrf=([^;]+)/);
    if (cookie) {
      cachedCsrfToken = decodeURIComponent(cookie[1]);
      return cachedCsrfToken;
    }
  }
  return null;
}

async function apiRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers || {});
  
  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const csrf = getCsrfToken();
  if (csrf && ["POST", "PUT", "PATCH", "DELETE"].includes((options.method || "GET").toUpperCase())) {
    headers.set("X-CSRF-Token", csrf);
  }

  const res = await fetch(`/api/v1${path}`, {
    ...options,
    headers,
    credentials: "include", // Forward session cookie
  });

  // Extract CSRF token if returned in headers
  const newCsrf = res.headers.get("X-CSRF-Token");
  if (newCsrf) setCsrfToken(newCsrf);

  if (!res.ok) {
    let errDetail = `HTTP ${res.status}: ${res.statusText}`;
    try {
      const errJson = await res.json();
      errDetail = typeof errJson.detail === "string" ? errJson.detail : Array.isArray(errJson.detail) ? errJson.detail.map((item: { msg?: string }) => item.msg || "Dữ liệu chưa hợp lệ").join("; ") : errDetail;
    } catch {
      // ignore
    }
    throw new Error(errDetail);
  }

  if (res.status === 204) {
    return {} as T;
  }

  return (await res.json()) as T;
}

export const api = {
  // Auth
  async login(login_name: string, password: string): Promise<{ status: string; csrf_token: string; user: UserAccount }> {
    const res = await apiRequest<{ status: string; csrf_token: string; user: UserAccount }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ login_name, password }),
    });
    if (res.csrf_token) setCsrfToken(res.csrf_token);
    return res;
  },

  async getMe(): Promise<UserAccount> {
    return apiRequest<UserAccount>("/auth/me");
  },

  async logout(): Promise<void> {
    await apiRequest<void>("/auth/logout", { method: "POST" });
    setCsrfToken("");
    Object.keys(sessionStorage).filter(key => key.startsWith("ts-upload:")).forEach(key => sessionStorage.removeItem(key));
  },

  // Requisitions
  async listRequisitions(): Promise<RequisitionItem[]> {
    return apiRequest<RequisitionItem[]>("/requisitions");
  },

  async getRequisition(id: string): Promise<RequisitionItem> {
    return apiRequest<RequisitionItem>(`/requisitions/${id}`);
  },

  async createRequisition(title: string): Promise<RequisitionItem> {
    return apiRequest<RequisitionItem>("/requisitions", {
      method: "POST",
      body: JSON.stringify({ title }),
    });
  },

  async createJDVersion(requisitionId: string, sourceText: string, rowVersion: number): Promise<{ id: string; text_hash: string }> {
    return apiRequest<{ id: string; text_hash: string }>(`/requisitions/${requisitionId}/jd-versions`, {
      method: "POST",
      headers: { "If-Match": `"${rowVersion}"` },
      body: JSON.stringify({ source_text: sourceText, change_reason: "Tạo JD ban đầu", expected_requisition_version: rowVersion }),
    });
  },

  async patchRequisition(id: string, payload: { title?: string; status?: string; reason?: string }, rowVersion?: number): Promise<RequisitionItem> {
    const headers: Record<string, string> = {};
    if (rowVersion !== undefined) {
      headers["If-Match"] = `"${rowVersion}"`;
    }
    return apiRequest<RequisitionItem>(`/requisitions/${id}`, {
      method: "PATCH",
      headers,
      body: JSON.stringify({ ...payload, expected_version: rowVersion }),
    });
  },

  async getRubric(id: string): Promise<any> {
    return apiRequest<any>(`/rubrics/${id}`);
  },

  async listRubrics(requisitionId: string): Promise<any[]> {
    return apiRequest<any[]>(`/requisitions/${requisitionId}/rubrics`);
  },

  async createRubric(requisitionId: string, payload: any): Promise<any> {
    return apiRequest<any>(`/requisitions/${requisitionId}/rubrics`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async updateRubric(id: string, rubric: any): Promise<any> {
    return apiRequest<any>(`/rubrics/${id}`, {
      method: "PUT",
      body: JSON.stringify({ rubric }),
    });
  },

  async approveRubric(id: string, expectedRequisitionVersion: number, expectedJdVersionId: string): Promise<any> {
    return apiRequest<any>(`/rubrics/${id}/approve`, {
      method: "POST",
      headers: { "If-Match": `"${expectedRequisitionVersion}"` },
      body: JSON.stringify({ expected_requisition_version: expectedRequisitionVersion, expected_jd_version_id: expectedJdVersionId, acknowledge_thresholds: true }),
    });
  },

  async approveJDForAI(jdVersionId: string, textHash: string): Promise<any> {
    return apiRequest(`/jd-versions/${jdVersionId}/approve-egress`, {
      method: "POST", body: JSON.stringify({ expected_text_hash: textHash, acknowledged: true }),
    });
  },

  async draftRubricFromJD(requisitionId: string): Promise<any> {
    return apiRequest<any>(`/requisitions/${requisitionId}/rubrics/draft-from-jd`, {
      method: "POST",
    });
  },

  async getJDVersion(id: string): Promise<any> {
    return apiRequest<any>(`/jd-versions/${id}`);
  },

  // Applications
  async listApplications(requisitionId: string): Promise<ApplicationItem[]> {
    return apiRequest<ApplicationItem[]>(`/requisitions/${requisitionId}/applications`);
  },

  async getReviewQueue(requisitionId: string): Promise<ReviewQueueItem[]> {
    return apiRequest<ReviewQueueItem[]>(`/requisitions/${requisitionId}/review-queue`);
  },

  async getCandidateComparison(requisitionId: string): Promise<CandidateComparison> {
    return apiRequest<CandidateComparison>(`/requisitions/${requisitionId}/comparison`);
  },

  async getShortlist(requisitionId: string, threshold?: number): Promise<ShortlistResponse> {
    const query = threshold !== undefined ? `?threshold=${threshold}` : "";
    return apiRequest<ShortlistResponse>(`/requisitions/${requisitionId}/shortlist${query}`);
  },

  async getIndependentReviewWorklist(requisitionId: string): Promise<Array<{ application_id: string; public_label: string; ready: boolean; submitted: boolean; received_at: string }>> {
    return apiRequest(`/requisitions/${requisitionId}/independent-reviews/mine`);
  },
  async getIndependentReviewDraft(applicationId: string): Promise<any> { return apiRequest(`/applications/${applicationId}/independent-review/draft`); },
  async saveIndependentReviewDraft(applicationId: string, payload: any): Promise<any> { return apiRequest(`/applications/${applicationId}/independent-review/draft`, { method: "PUT", body: JSON.stringify(payload) }); },
  async getIndependentReviewContext(applicationId: string): Promise<IndependentReviewContext> {
    return apiRequest<IndependentReviewContext>(`/applications/${applicationId}/independent-review/context`);
  },

  async submitIndependentReview(applicationId: string, payload: {
    review_kind: "hr" | "it";
    expected_generation: number;
    expected_document_id: string;
    expected_sanitized_version_id: string;
    expected_rubric_version_id: string;
    criterion_scores: Record<string, number | null>;
    criterion_statuses: Record<string, "assessed" | "insufficient_evidence" | "conflicting_evidence">;
    criterion_quotes: Record<string, string | null>;
    criterion_notes: Record<string, string>;
    recommendation: "consider_next_round" | "needs_clarification" | "review_required";
  }): Promise<{ id: string; submitted_at: string; snapshot_hash: string }> {
    return apiRequest(`/applications/${applicationId}/independent-review`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async getApplication(id: string): Promise<ApplicationItem> {
    return apiRequest<ApplicationItem>(`/applications/${id}`);
  },

  async createApplication(requisitionId: string, idempotencyKey?: string): Promise<ApplicationItem> {
    return apiRequest<ApplicationItem>(`/requisitions/${requisitionId}/applications`, {
      method: "POST",
      body: JSON.stringify({}),
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
    });
  },

  async uploadDocument(applicationId: string, file: File, idempotencyKey?: string): Promise<any> {
    const formData = new FormData();
    formData.append("file", file);
    return apiRequest<any>(`/applications/${applicationId}/documents`, {
      method: "POST",
      body: formData,
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
    });
  },

  // Review Workspace
  async getReviewWorkspace(applicationId: string): Promise<ReviewWorkspaceData> {
    return apiRequest<ReviewWorkspaceData>(`/applications/${applicationId}/review-workspace`);
  },

  // Sanitization
  async listSanitizedVersions(documentId: string): Promise<any[]> {
    return apiRequest<any[]>(`/documents/${documentId}/sanitized-versions`);
  },

  async getSanitizedDetail(sanitizedId: string): Promise<any> {
    return apiRequest<any>(`/sanitized-versions/${sanitizedId}`);
  },

  async editSanitizedVersion(documentId: string, baseVersionId: string, canonicalText: string, editReason: string): Promise<any> {
    return apiRequest<any>(`/documents/${documentId}/sanitized-versions`, {
      method: "POST",
      body: JSON.stringify({
        base_version_id: baseVersionId,
        canonical_text: canonicalText,
        edit_reason: editReason,
      }),
    });
  },

  async approveSanitizedVersion(versionId: string, expectedApplicationVersion: number, expectedSha256: string, confirmedDocumentIsCv: boolean = false): Promise<any> {
    return apiRequest<any>(`/sanitized-versions/${versionId}/approve`, {
      method: "POST",
      body: JSON.stringify({
        expected_application_version: expectedApplicationVersion,
        expected_sha256: expectedSha256,
        acknowledged: true,
        confirmed_document_is_cv: confirmedDocumentIsCv,
      }),
    });
  },

  async revokeSanitizedVersion(versionId: string, reason_code: string, note: string): Promise<any> {
    return apiRequest<any>(`/sanitized-versions/${versionId}/revoke`, {
      method: "POST",
      body: JSON.stringify({ reason_code, note }),
    });
  },

  async createRawGrant(applicationId: string, granteeUserId: string, reason: string, durationMinutes: number = 30): Promise<any> {
    return apiRequest<any>(`/applications/${applicationId}/raw-grants`, {
      method: "POST",
      body: JSON.stringify({
        grantee_user_id: granteeUserId,
        scopes: ["raw_cv"],
        expires_at: new Date(Date.now() + durationMinutes * 60_000).toISOString(),
        reason,
      }),
    });
  },

  async getRawDocumentPreview(documentId: string): Promise<Blob> {
    const res = await fetch(`/api/v1/documents/${encodeURIComponent(documentId)}/raw-preview`, {
      credentials: "include",
      cache: "no-store",
      headers: { Accept: "application/pdf" },
    });
    if (!res.ok) {
      if (res.status === 403) throw new Error("Quyền xem CV gốc đã hết hạn hoặc chưa được cấp. Hãy cấp lại quyền rồi thử lại.");
      throw new Error("Không thể tải PDF. Hãy làm mới hồ sơ và thử lại.");
    }
    const contentType = res.headers.get("Content-Type")?.split(";")[0].trim().toLowerCase();
    if (contentType !== "application/pdf") {
      throw new Error("Xem trực tiếp hiện hỗ trợ PDF. Tệp này chưa có bản PDF để xem trong ứng dụng.");
    }
    const blob = await res.blob();
    if (!blob.size) throw new Error("Tệp PDF rỗng.");
    return blob;
  },

  // Assessment
  async triggerAssessment(
    applicationId: string,
    sanitizedVersionId: string,
    rubricVersionId: string,
    focusCriterionIds?: string[],
  ): Promise<any> {
    return apiRequest<any>(`/applications/${applicationId}/assessments`, {
      method: "POST",
      body: JSON.stringify({
        sanitized_version_id: sanitizedVersionId,
        rubric_version_id: rubricVersionId,
        ...(focusCriterionIds?.length ? { focus_criterion_ids: focusCriterionIds } : {}),
      }),
    });
  },

  async getAssessmentRun(applicationId: string, runId: string): Promise<AssessmentRunData> {
    return apiRequest<AssessmentRunData>(`/applications/${applicationId}/assessments/${runId}`);
  },

  async getCandidateSummary(applicationId: string): Promise<ExecutiveSummaryData> {
    return apiRequest<ExecutiveSummaryData>(`/applications/${applicationId}/summary`);
  },

  async generateCandidateSummary(applicationId: string): Promise<ExecutiveSummaryData> {
    return apiRequest<ExecutiveSummaryData>(`/applications/${applicationId}/summary/generate`, {
      method: "POST",
    });
  },

  async getApprovedSpans(applicationId: string): Promise<any[]> { return apiRequest(`/applications/${applicationId}/approved-spans`); },
  async getSourceSpan(spanId: string): Promise<any> { return apiRequest(`/source-spans/${spanId}`); },
  async updateHRRevision(revisionId: string, payload: any): Promise<any> { return apiRequest(`/hr-revisions/${revisionId}`, { method: "PUT", body: JSON.stringify(payload) }); },
  async getApplicationProgress(applicationId: string): Promise<any> { return apiRequest(`/applications/${applicationId}/progress`); },

  // HR Revisions & Final Decision
  async listHRRevisions(applicationId: string): Promise<any[]> {
    return apiRequest<any[]>(`/applications/${applicationId}/hr-revisions`);
  },

  async createHRRevision(applicationId: string, payload: any): Promise<any> {
    return apiRequest<any>(`/applications/${applicationId}/hr-revisions`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async finalizeHRRevision(revisionId: string, expected_application_version: number, expected_rubric_version_id: string): Promise<any> {
    return apiRequest<any>(`/hr-revisions/${revisionId}/finalize`, {
      method: "POST",
      body: JSON.stringify({ expected_application_version, expected_rubric_version_id }),
    });
  },

  async createReviewAttestation(applicationId: string, payload: any): Promise<any> {
    return apiRequest<any>(`/applications/${applicationId}/review-attestations`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async listDecisions(applicationId: string): Promise<any[]> {
    return apiRequest<any[]>(`/applications/${applicationId}/decisions`);
  },

  async createFinalDecision(applicationId: string, payload: any): Promise<any> {
    return apiRequest<any>(`/applications/${applicationId}/decisions`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  // Versioned correspondence templates; no sending or LLM call.
  async getEmailDraft(applicationId: string, template?: string): Promise<EmailDraftData> {
    const query = template ? `?template=${template}` : "";
    return apiRequest<EmailDraftData>(`/applications/${applicationId}/email-draft${query}`);
  },

  async generateEmailDraft(applicationId: string, template?: string): Promise<EmailDraftData> {
    const query = template ? `?template=${template}` : "";
    return apiRequest<EmailDraftData>(`/applications/${applicationId}/email-draft/generate${query}`, {
      method: "POST",
    });
  },

  async updateEmailDraft(applicationId: string, subject: string, body: string, draftId: string, expectedVersion: number, status: "draft" | "approved" = "draft", acknowledgedContent = false): Promise<EmailDraftData> {
    return apiRequest<EmailDraftData>(`/applications/${applicationId}/email-draft`, {
      method: "PUT",
      body: JSON.stringify({ subject, body, status, draft_id: draftId, expected_version: expectedVersion, acknowledged_content: acknowledgedContent }),
    });
  },

  // Interview Questions
  async getQuestionBank(rubricId: string): Promise<any[]> {
    return apiRequest<any[]>(`/rubrics/${rubricId}/interview-question-banks`);
  },

  async createSeedQuestionBank(rubricId: string): Promise<any> {
    return apiRequest<any>(`/rubrics/${rubricId}/interview-question-banks`, {
      method: "POST", body: JSON.stringify({ source: "seed" }),
    });
  },

  async approveQuestionBank(bankId: string, expected_rubric_version_id: string): Promise<any> {
    return apiRequest<any>(`/interview-question-banks/${bankId}/approve`, {
      method: "POST",
      body: JSON.stringify({ expected_rubric_version_id, acknowledged: true }),
    });
  },

  async triggerInterviewDraft(applicationId: string, effectiveResult: any, expectedBankId?: string | null): Promise<any> {
    return apiRequest<any>(`/applications/${applicationId}/interview-drafts`, {
      method: "POST",
      body: JSON.stringify({
        effective_result: effectiveResult,
        expected_question_bank_id: expectedBankId ?? null,
      }),
    });
  },

  async getInterviewDraftDetail(draftId: string): Promise<any> {
    return apiRequest<any>(`/interview-drafts/${draftId}`);
  },

  async getLatestInterviewDraft(applicationId: string): Promise<any | null> {
    return apiRequest<any | null>(`/applications/${applicationId}/interview-drafts/latest`);
  },

  async getInterviewScorecards(applicationId: string): Promise<any[]> {
    return apiRequest<any[]>(`/applications/${applicationId}/interview-scorecards`);
  },

  async saveInterviewScorecard(applicationId: string, payload: any): Promise<any> {
    return apiRequest<any>(`/applications/${applicationId}/interview-scorecards`, {
      method: "PUT", body: JSON.stringify(payload),
    });
  },

  async finalizeInterviewScorecard(scorecardId: string, expected_version: number): Promise<any> {
    return apiRequest<any>(`/interview-scorecards/${scorecardId}/finalize`, {
      method: "POST", body: JSON.stringify({ expected_version }),
    });
  },

  async saveInterviewRevision(draftId: string, payload: any): Promise<any> {
    return apiRequest<any>(`/interview-drafts/${draftId}/revisions`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  // Deletion
  async requestDeletion(scope: "application" | "candidate", targetId: string, reason_category: string): Promise<any> {
    return apiRequest<any>("/deletion-requests", {
      method: "POST",
      body: JSON.stringify({ scope, target_id: targetId, reason_category }),
    });
  },

  async getDeletionRequest(id: string): Promise<any> {
    return apiRequest<any>(`/deletion-requests/${id}`);
  },

  async getRetentionPolicy(): Promise<any> {
    return apiRequest<any>("/retention-policy");
  },

  // Onboarding & Sandbox (Task B21)
  async getOnboardingStatus(): Promise<any> {
    return apiRequest<any>("/onboarding");
  },

  async completeOnboardingStep(stepId: string, exerciseResult?: any): Promise<any> {
    return apiRequest<any>("/onboarding/step", {
      method: "POST",
      body: JSON.stringify({ step_id: stepId, exercise_result: exerciseResult }),
    });
  },

  async resetOnboarding(): Promise<any> {
    return apiRequest<any>("/onboarding/reset", {
      method: "POST",
    });
  },

  async getSandboxScenarios(): Promise<any[]> {
    return apiRequest<any[]>("/onboarding/scenarios");
  },

  // Admin & Observability (Task B23)
  async getAdminMetrics(): Promise<any> {
    return apiRequest<any>("/admin/metrics");
  },

  async getSystemReadiness(): Promise<any> {
    return apiRequest<any>("/admin/readiness");
  },
};
