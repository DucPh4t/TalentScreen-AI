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
  id: string;
  title: string;
  department?: string;
  status: "draft" | "open" | "paused" | "closed";
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
  status: "assessed" | "insufficient_evidence" | "conflict";
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

export interface AssessmentRunData {
  id: string;
  application_id: string;
  run_no: number;
  status: string;
  observed_score: number | null;
  coverage: number;
  comparable_score: number | null;
  recommendation: "consider_next_round" | "needs_clarification" | "review_required";
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

// Global CSRF token cache
let cachedCsrfToken: string | null = null;

export function setCsrfToken(token: string) {
  cachedCsrfToken = token;
}

export function getCsrfToken(): string | null {
  if (cachedCsrfToken) return cachedCsrfToken;
  if (typeof document !== "undefined") {
    // Attempt to extract from cookie if available
    const match = document.cookie.match(/talentscreen_csrf=([^;]+)/);
    if (match) return match[1];
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
      errDetail = errJson.detail || errDetail;
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
  async login(login_name: string, password: string): Promise<{ message: string; csrf_token: string; user_id: string }> {
    const res = await apiRequest<{ message: string; csrf_token: string; user_id: string }>("/auth/login", {
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
  },

  // Requisitions
  async listRequisitions(): Promise<RequisitionItem[]> {
    return apiRequest<RequisitionItem[]>("/requisitions");
  },

  async getRequisition(id: string): Promise<RequisitionItem> {
    return apiRequest<RequisitionItem>(`/requisitions/${id}`);
  },

  async createRequisition(title: string, jd_text: string, department?: string): Promise<RequisitionItem> {
    return apiRequest<RequisitionItem>("/requisitions", {
      method: "POST",
      body: JSON.stringify({ title, jd_text, department }),
    });
  },

  async patchRequisition(id: string, payload: { title?: string; status?: string }, rowVersion?: number): Promise<RequisitionItem> {
    const headers: Record<string, string> = {};
    if (rowVersion !== undefined) {
      headers["If-Match"] = `"${rowVersion}"`;
    }
    return apiRequest<RequisitionItem>(`/requisitions/${id}`, {
      method: "PATCH",
      headers,
      body: JSON.stringify(payload),
    });
  },

  async getRubric(id: string): Promise<any> {
    return apiRequest<any>(`/rubrics/${id}`);
  },

  async createRubric(requisitionId: string, payload: any): Promise<any> {
    return apiRequest<any>(`/requisitions/${requisitionId}/rubrics`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  async approveRubric(id: string, expectedVersion: number): Promise<any> {
    return apiRequest<any>(`/rubrics/${id}/approve`, {
      method: "POST",
      headers: { "If-Match": `"${expectedVersion}"` },
      body: JSON.stringify({ acknowledged: true }),
    });
  },

  async getJDVersion(id: string): Promise<any> {
    return apiRequest<any>(`/jd-versions/${id}`);
  },

  // Applications
  async listApplications(requisitionId: string): Promise<ApplicationItem[]> {
    return apiRequest<ApplicationItem[]>(`/requisitions/${requisitionId}/applications`);
  },

  async getApplication(id: string): Promise<ApplicationItem> {
    return apiRequest<ApplicationItem>(`/applications/${id}`);
  },

  async createApplication(requisitionId: string, candidate_name?: string): Promise<ApplicationItem> {
    return apiRequest<ApplicationItem>(`/requisitions/${requisitionId}/applications`, {
      method: "POST",
      body: JSON.stringify({ candidate_name }),
    });
  },

  async uploadDocument(applicationId: string, file: File): Promise<any> {
    const formData = new FormData();
    formData.append("file", file);
    return apiRequest<any>(`/applications/${applicationId}/documents`, {
      method: "POST",
      body: formData,
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

  async approveSanitizedVersion(versionId: string, acknowledged: boolean): Promise<any> {
    return apiRequest<any>(`/sanitized-versions/${versionId}/approve`, {
      method: "POST",
      body: JSON.stringify({ acknowledged }),
    });
  },

  async revokeSanitizedVersion(versionId: string, reason_code: string, note: string): Promise<any> {
    return apiRequest<any>(`/sanitized-versions/${versionId}/revoke`, {
      method: "POST",
      body: JSON.stringify({ reason_code, note }),
    });
  },

  async createRawGrant(applicationId: string, reviewer_user_id: string, reason: string, duration_minutes: number = 30): Promise<any> {
    return apiRequest<any>(`/applications/${applicationId}/raw-grants`, {
      method: "POST",
      body: JSON.stringify({ reviewer_user_id, reason, duration_minutes }),
    });
  },

  // Assessment
  async triggerAssessment(applicationId: string, sanitizedVersionId: string, rubricVersionId: string): Promise<any> {
    return apiRequest<any>(`/applications/${applicationId}/assessments`, {
      method: "POST",
      body: JSON.stringify({
        sanitized_version_id: sanitizedVersionId,
        rubric_version_id: rubricVersionId,
      }),
    });
  },

  async getAssessmentRun(applicationId: string, runId: string): Promise<AssessmentRunData> {
    return apiRequest<AssessmentRunData>(`/applications/${applicationId}/assessments/${runId}`);
  },

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

  // Interview Questions
  async getQuestionBank(rubricId: string): Promise<any[]> {
    return apiRequest<any[]>(`/rubrics/${rubricId}/interview-question-banks`);
  },

  async approveQuestionBank(bankId: string, expected_rubric_version_id: string): Promise<any> {
    return apiRequest<any>(`/interview-question-banks/${bankId}/approve`, {
      method: "POST",
      body: JSON.stringify({ expected_rubric_version_id, acknowledged: true }),
    });
  },

  async triggerInterviewDraft(applicationId: string, effectiveResult: any, expectedBankId: string): Promise<any> {
    return apiRequest<any>(`/applications/${applicationId}/interview-drafts`, {
      method: "POST",
      body: JSON.stringify({
        effective_result: effectiveResult,
        expected_question_bank_id: expectedBankId,
      }),
    });
  },

  async getInterviewDraftDetail(draftId: string): Promise<any> {
    return apiRequest<any>(`/interview-drafts/${draftId}`);
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
