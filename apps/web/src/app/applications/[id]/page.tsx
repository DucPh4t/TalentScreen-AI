"use client";

import React, { use, useEffect, useState } from "react";
import Link from "next/link";
import { api, ApplicationItem, AssessmentRunData } from "@/lib/api";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function ApplicationWorkspacePage({ params }: PageProps) {
  const { id } = use(params);

  const [application, setApplication] = useState<any>(null);
  const [requisition, setRequisition] = useState<any>(null);
  const [rubric, setRubric] = useState<any>(null);
  const [sanitizedVersion, setSanitizedVersion] = useState<any>(null);
  const [assessmentRun, setAssessmentRun] = useState<AssessmentRunData | null>(null);
  const [hrRevisions, setHrRevisions] = useState<any[]>([]);
  const [decisions, setDecisions] = useState<any[]>([]);
  const [interviewDraft, setInterviewDraft] = useState<any>(null);
  const [questionBanks, setQuestionBanks] = useState<any[]>([]);

  const [activeTab, setActiveTab] = useState<"sanitization" | "assessment" | "revision" | "interview">("assessment");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Quote drawer
  const [selectedEvidence, setSelectedEvidence] = useState<any | null>(null);

  // Sanitization action state
  const [approvingSanitized, setApprovingSanitized] = useState(false);
  const [acknowledgedSanitization, setAcknowledgedSanitization] = useState(false);

  // Assessment action state
  const [triggeringAssessment, setTriggeringAssessment] = useState(false);

  // Deletion modal
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteScope, setDeleteScope] = useState<"application" | "candidate">("application");
  const [deleteReason, setDeleteReason] = useState("candidate_request");
  const [deleting, setDeleting] = useState(false);

  // HR Revision state
  const [showRevisionForm, setShowRevisionForm] = useState(false);
  const [revisionSummary, setRevisionSummary] = useState("");
  const [revisionCriteria, setRevisionCriteria] = useState<Record<string, any>>({});
  const [savingRevision, setSavingRevision] = useState(false);

  // Decision Form state
  const [decisionOutcome, setDecisionOutcome] = useState<"advance" | "request_information" | "not_advance">("advance");
  const [decisionReason, setDecisionReason] = useState("");
  const [attestCheck1, setAttestCheck1] = useState(false);
  const [attestCheck2, setAttestCheck2] = useState(false);
  const [attestCheck3, setAttestCheck3] = useState(false);
  const [submittingDecision, setSubmittingDecision] = useState(false);

  // Interview state
  const [triggeringInterview, setTriggeringInterview] = useState(false);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      // 1. Load application detail
      const app = await api.getApplication(id);
      setApplication(app);

      // 2. Load Requisition & Rubric
      if (app.requisition_id) {
        try {
          const req = await api.getRequisition(app.requisition_id);
          setRequisition(req);
          if (req.current_rubric_version_id) {
            const rub = await api.getRubric(req.current_rubric_version_id);
            setRubric(rub);

            // Load question bank if available
            try {
              const banks = await api.getQuestionBank(req.current_rubric_version_id);
              setQuestionBanks(banks);
            } catch (err) {
              console.warn("Could not load question banks:", err);
            }
          }
        } catch (err) {
          console.warn("Could not load requisition:", err);
        }
      }

      // 3. Load Sanitized Version if present
      if (app.current_document_id) {
        try {
          const sanList = await api.listSanitizedVersions(app.current_document_id);
          if (sanList.length > 0) {
            // Fetch detail of latest sanitized version
            const latestId = app.current_sanitized_version_id || sanList[0].id;
            const sanDetail = await api.getSanitizedDetail(latestId);
            setSanitizedVersion(sanDetail);
          }
        } catch (err) {
          console.warn("Could not load sanitized versions:", err);
        }
      }

      // 4. Load Assessment Run if present
      if (app.current_assessment_run_id) {
        try {
          const run = await api.getAssessmentRun(app.id, app.current_assessment_run_id);
          setAssessmentRun(run);
        } catch (err) {
          console.warn("Could not load assessment run:", err);
        }
      }

      // 5. Load HR Revisions
      try {
        const revs = await api.listHRRevisions(app.id);
        setHrRevisions(revs);
      } catch (err) {
        console.warn("Could not load HR revisions:", err);
      }

      // 6. Load Decisions
      try {
        const decs = await api.listDecisions(app.id);
        setDecisions(decs);
      } catch (err) {
        console.warn("Could not load decisions:", err);
      }
    } catch (err: any) {
      setError(err.message || "Không thể tải không gian xét duyệt hồ sơ");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [id]);

  // Handler: Approve Sanitized Version
  async function handleApproveSanitization() {
    if (!sanitizedVersion) return;
    if (!acknowledgedSanitization) {
      alert("Vui lòng xác nhận đã kiểm tra khử định danh PII.");
      return;
    }
    setApprovingSanitized(true);
    try {
      await api.approveSanitizedVersion(sanitizedVersion.id, true);
      alert("Đã phê duyệt phiên bản khử định danh thành công!");
      await loadData();
    } catch (err: any) {
      alert("Lỗi phê duyệt khử định danh: " + err.message);
    } finally {
      setApprovingSanitized(false);
    }
  }

  // Handler: Trigger Assessment
  async function handleTriggerAssessment() {
    if (!sanitizedVersion || !requisition?.current_rubric_version_id) {
      alert("Cần có phiên bản khử định danh và Rubric được kích hoạt.");
      return;
    }
    setTriggeringAssessment(true);
    try {
      await api.triggerAssessment(
        id,
        sanitizedVersion.id,
        requisition.current_rubric_version_id
      );
      alert("Đã đưa yêu cầu đánh giá AI vào hàng đợi xử lý.");
      await loadData();
    } catch (err: any) {
      alert("Lỗi kích hoạt đánh giá: " + err.message);
    } finally {
      setTriggeringAssessment(false);
    }
  }

  // Handler: Submit Attested Hiring Decision
  async function handleSubmitDecision(e: React.FormEvent) {
    e.preventDefault();
    if (!attestCheck1 || !attestCheck2 || !attestCheck3) {
      alert("Bạn phải cam kết đầy đủ cả 3 điều khoản ký duyệt trước khi ban hành quyết định.");
      return;
    }
    if (decisionReason.trim().length < 20) {
      alert("Lý do quyết định phải dài tối thiểu 20 ký tự.");
      return;
    }

    submittingDecisionSet: setSubmittingDecision(true);
    try {
      // 1. Sign ReviewAttestation first
      let effectiveKind: "assessment_run" | "hr_revision" = "assessment_run";
      let effectiveId = assessmentRun?.id;
      if (hrRevisions.length > 0 && hrRevisions[0].status === "finalized") {
        effectiveKind = "hr_revision";
        effectiveId = hrRevisions[0].id;
      }

      if (!effectiveId) {
        throw new Error("Chưa có kết quả đánh giá hoặc bản sửa đổi HR hợp lệ để làm cơ sở ra quyết định.");
      }

      const attestation = await api.createReviewAttestation(id, {
        decision_basis: "assessment_review",
        effective_result: {
          kind: effectiveKind,
          id: effectiveId,
        },
        reviewed_criterion_ids: [
          "technical_competence",
          "system_design_architecture",
          "problem_solving_debugging",
          "code_quality_testing",
          "communication_collaboration",
          "domain_expertise",
        ],
        acknowledged: true,
      });

      // 2. Submit Final Decision bound to Attestation
      await api.createFinalDecision(id, {
        decision_basis: "assessment_review",
        outcome: decisionOutcome,
        reason: decisionReason,
        attestation_id: attestation.id,
        expected_rubric_version_id: rubric?.id,
      });

      alert("Quyết định tuyển dụng đã được ban hành và ký cam kết thành công!");
      await loadData();
    } catch (err: any) {
      alert("Lỗi ban hành quyết định: " + err.message);
    } finally {
      setSubmittingDecision(false);
    }
  }

  // Handler: Trigger Interview Draft
  async function handleTriggerInterview() {
    if (!questionBanks || questionBanks.length === 0) {
      alert("Chưa có ngân hàng câu hỏi chuẩn cho Rubric này.");
      return;
    }
    setTriggeringInterview(true);
    try {
      const activeBank = questionBanks.find((b) => b.is_active) || questionBanks[0];
      let effectiveKind = "assessment_run";
      let effectiveId = assessmentRun?.id;
      if (hrRevisions.length > 0 && hrRevisions[0].status === "finalized") {
        effectiveKind = "hr_revision";
        effectiveId = hrRevisions[0].id;
      }

      const draft = await api.triggerInterviewDraft(
        id,
        { kind: effectiveKind, id: effectiveId },
        activeBank.id
      );
      setInterviewDraft(draft);
      alert("Đã tạo kế hoạch phỏng vấn và câu hỏi đào sâu!");
    } catch (err: any) {
      alert("Lỗi tạo câu hỏi phỏng vấn: " + err.message);
    } finally {
      setTriggeringInterview(false);
    }
  }

  // Handler: Data Deletion
  async function handleDeleteConfirm() {
    if (!confirm("Hành động này sẽ XÓA VĨNH VIỄN tệp CV và đặt trạng thái tombstone ngay lập tức. Tiếp tục?")) {
      return;
    }
    setDeleting(true);
    try {
      await api.requestDeletion(deleteScope, id, deleteReason);
      alert("Hồ sơ đã được xóa vĩnh viễn khỏi hệ thống.");
      setShowDeleteModal(false);
      await loadData();
    } catch (err: any) {
      alert("Lỗi xóa dữ liệu: " + err.message);
    } finally {
      setDeleting(false);
    }
  }

  if (loading) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "4rem" }}>
        <div style={{ color: "var(--text-muted)" }}>Đang mở không gian xét duyệt hồ sơ...</div>
      </div>
    );
  }

  if (error || !application) {
    return (
      <div className="card" style={{ borderColor: "var(--danger)" }}>
        <h2 style={{ color: "var(--danger)", marginBottom: "0.5rem" }}>Không tìm thấy hồ sơ</h2>
        <p style={{ color: "var(--text-muted)", marginBottom: "1rem" }}>{error}</p>
        <Link href="/requisitions" className="btn btn-secondary">
          Quay lại đợt tuyển dụng
        </Link>
      </div>
    );
  }

  return (
    <div>
      {/* Top Header Bar */}
      <div style={{ marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
          <Link href={application.requisition_id ? `/requisitions/${application.requisition_id}` : "/requisitions"} style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
            ← {requisition?.title || "Đợt tuyển dụng"}
          </Link>
          <span style={{ color: "var(--text-muted)" }}>/</span>
          <span style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>{application.public_label}</span>
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.25rem" }}>
              <h1 style={{ fontSize: "1.75rem", fontWeight: 700, fontFamily: "monospace", color: "var(--accent-glow)" }}>
                {application.public_label}
              </h1>
              <span className={`badge badge-${application.status}`}>{application.status.toUpperCase()}</span>
              <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)", background: "var(--bg-main)", padding: "0.2rem 0.5rem", borderRadius: "var(--radius-sm)" }}>
                Thế hệ g{application.generation} • Khóa v{application.row_version}
              </span>
            </div>
            <p style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>
              Quy tắc AI có trách nhiệm: Quyết định dựa trên chuỗi bằng chứng thực tế — Không sử dụng điểm tổng hợp làm căn cứ tự động loại ứng viên.
            </p>
          </div>

          <div style={{ display: "flex", gap: "0.75rem" }}>
            <button
              className="btn btn-secondary"
              style={{ color: "var(--danger)", borderColor: "rgba(239, 68, 68, 0.4)" }}
              onClick={() => setShowDeleteModal(true)}
            >
              Yêu cầu xóa dữ liệu (GDPR)
            </button>
          </div>
        </div>
      </div>

      {/* Tabs Bar */}
      <div className="tabs">
        <button
          className={`tab-btn ${activeTab === "assessment" ? "active" : ""}`}
          onClick={() => setActiveTab("assessment")}
        >
          1. Đánh giá & Bằng chứng ({assessmentRun ? "Đã có kết quả" : "Chưa chạy"})
        </button>
        <button
          className={`tab-btn ${activeTab === "sanitization" ? "active" : ""}`}
          onClick={() => setActiveTab("sanitization")}
        >
          2. Khử định danh PII ({sanitizedVersion?.status || "Chờ xử lý"})
        </button>
        <button
          className={`tab-btn ${activeTab === "revision" ? "active" : ""}`}
          onClick={() => setActiveTab("revision")}
        >
          3. Hiệu chỉnh HR & Ký quyết định ({decisions.length > 0 ? "Đã duyệt" : "Chờ quyết định"})
        </button>
        <button
          className={`tab-btn ${activeTab === "interview" ? "active" : ""}`}
          onClick={() => setActiveTab("interview")}
        >
          4. Phỏng vấn & Đào sâu
        </button>
      </div>

      {/* Tab 1: Evidence-first Assessment */}
      {activeTab === "assessment" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          {!assessmentRun ? (
            <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 600, marginBottom: "0.75rem" }}>
                Hồ sơ chưa có kết quả đánh giá AI
              </h2>
              <p style={{ color: "var(--text-muted)", maxWidth: "600px", margin: "0 auto 1.5rem auto", fontSize: "0.875rem" }}>
                Đánh giá AI sẽ đối chiếu văn bản CV đã khử định danh với 6 tiêu chí chuẩn hóa của Rubric. Mọi trích dẫn đều được liên kết mã byte để kiểm chứng.
              </p>
              <button
                className="btn btn-primary"
                onClick={handleTriggerAssessment}
                disabled={triggeringAssessment || !sanitizedVersion}
              >
                {triggeringAssessment ? "Đang xếp hàng đánh giá..." : "Chạy đánh giá AI ngay"}
              </button>
              {!sanitizedVersion && (
                <p style={{ color: "var(--warning)", fontSize: "0.8125rem", marginTop: "0.5rem" }}>
                  * Lưu ý: Cần xử lý bước Khử định danh trước khi đánh giá.
                </p>
              )}
            </div>
          ) : (
            <div>
              {/* Summary Collapsible Card */}
              <div className="card" style={{ marginBottom: "1.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
                  <div>
                    <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                      Khuyến nghị từ hệ thống
                    </span>
                    <div style={{ marginTop: "0.25rem" }}>
                      <span className={`badge badge-${assessmentRun.recommendation === "consider_next_round" ? "open" : "paused"}`} style={{ fontSize: "0.95rem", padding: "0.35rem 0.75rem" }}>
                        {assessmentRun.recommendation === "consider_next_round" && "Đề xuất phỏng vấn vòng sau (Consider Next Round)"}
                        {assessmentRun.recommendation === "needs_clarification" && "Cần làm rõ thêm thông tin (Needs Clarification)"}
                        {assessmentRun.recommendation === "review_required" && "Cần HR xem xét trực tiếp (Review Required)"}
                      </span>
                    </div>
                  </div>

                  <div style={{ display: "flex", gap: "2rem" }}>
                    <div>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>ĐỘ PHỦ TIÊU CHÍ</div>
                      <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-primary)" }}>
                        {assessmentRun.coverage}%
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>ĐIỂM QUAN SÁT</div>
                      <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--accent-glow)" }}>
                        {assessmentRun.observed_score ?? "N/A"}/100
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>ĐIỂM SO SÁNH</div>
                      <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-primary)" }}>
                        {assessmentRun.comparable_score ?? "N/A"}/100
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Criteria Evidence Table */}
              <div className="card">
                <h2 style={{ fontSize: "1.25rem", fontWeight: 600, marginBottom: "1rem" }}>
                  Bảng đối chiếu 6 tiêu chí & Bằng chứng nguyên văn
                </h2>

                <div className="table-container">
                  <table>
                    <thead>
                      <tr>
                        <th style={{ width: "20%" }}>Tiêu chí</th>
                        <th style={{ width: "12%" }}>Trạng thái</th>
                        <th style={{ width: "10%" }}>Điểm (0..4)</th>
                        <th style={{ width: "30%" }}>Giải trình đánh giá</th>
                        <th>Trích dẫn bằng chứng (Exact Span)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {assessmentRun.criteria.map((c) => (
                        <tr key={c.criterion_id}>
                          <td>
                            <strong style={{ fontSize: "0.875rem" }}>{c.criterion_id}</strong>
                          </td>
                          <td>
                            <span className={`badge badge-${c.status === "assessed" ? "open" : "draft"}`}>
                              {c.status}
                            </span>
                          </td>
                          <td>
                            <span style={{ fontSize: "1.125rem", fontWeight: 700, color: c.score !== null && c.score >= 2 ? "var(--success)" : "var(--warning)" }}>
                              {c.score !== null ? c.score : "-"}
                            </span>
                          </td>
                          <td style={{ fontSize: "0.8125rem", lineHeight: 1.5 }}>
                            {c.rationale}
                            {c.missing_information && c.missing_information.length > 0 && (
                              <div style={{ marginTop: "0.5rem", color: "var(--warning)" }}>
                                <strong>Thiếu thông tin:</strong> {c.missing_information.join(", ")}
                              </div>
                            )}
                          </td>
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                              {c.evidence.map((ev) => (
                                <div
                                  key={ev.span_id}
                                  onClick={() => setSelectedEvidence(ev)}
                                  style={{
                                    padding: "0.4rem 0.6rem",
                                    background: "var(--bg-main)",
                                    border: "1px solid var(--border-subtle)",
                                    borderRadius: "var(--radius-sm)",
                                    cursor: "pointer",
                                    fontSize: "0.75rem",
                                  }}
                                  title="Bấm để xem trích dẫn đầy đủ"
                                >
                                  <div style={{ color: "var(--accent-glow)", fontFamily: "monospace", marginBottom: "0.2rem" }}>
                                    {ev.span_id} [{ev.resolved_start_cp}..{ev.resolved_end_cp}]
                                  </div>
                                  <div style={{ color: "var(--text-secondary)", fontStyle: "italic" }}>
                                    &ldquo;{ev.quote.slice(0, 80)}{ev.quote.length > 80 ? "..." : ""}&rdquo;
                                  </div>
                                </div>
                              ))}
                              {c.evidence.length === 0 && (
                                <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
                                  Không có trích dẫn bằng chứng
                                </span>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Sanitization & Redaction Viewer */}
      {activeTab === "sanitization" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          <div className="card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem", flexWrap: "wrap", gap: "0.75rem" }}>
              <div>
                <h2 style={{ fontSize: "1.25rem", fontWeight: 600 }}>Văn bản hồ sơ đã khử định danh PII</h2>
                <p style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>
                  Toàn bộ tên riêng, số điện thoại, email, địa chỉ, ngày sinh và trường đại học đã được thay thế bằng token khử định danh.
                </p>
              </div>

              {sanitizedVersion && (
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                  <span className={`badge badge-${sanitizedVersion.status === "approved" ? "open" : "draft"}`}>
                    {sanitizedVersion.status.toUpperCase()}
                  </span>
                  {sanitizedVersion.status === "draft" && (
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <label style={{ fontSize: "0.8125rem", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                        <input
                          type="checkbox"
                          checked={acknowledgedSanitization}
                          onChange={(e) => setAcknowledgedSanitization(e.target.checked)}
                        />
                        Xác nhận đã kiểm tra
                      </label>
                      <button
                        className="btn btn-primary"
                        onClick={handleApproveSanitization}
                        disabled={approvingSanitized || !acknowledgedSanitization}
                      >
                        Phê duyệt PII (Owner)
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>

            {sanitizedVersion ? (
              <div style={{
                background: "var(--bg-main)",
                padding: "1.25rem",
                borderRadius: "var(--radius-sm)",
                fontSize: "0.875rem",
                lineHeight: 1.7,
                maxHeight: "500px",
                overflowY: "auto",
                whiteSpace: "pre-wrap",
                fontFamily: "var(--font-mono)",
                color: "var(--text-secondary)",
              }}>
                {sanitizedVersion.canonical_text}
              </div>
            ) : (
              <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
                Chưa có văn bản khử định danh nào được tạo cho hồ sơ này.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Tab 3: HR Revision & Attested Hiring Decision */}
      {activeTab === "revision" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          {/* Attested Decision Section */}
          <div className="card">
            <h2 style={{ fontSize: "1.25rem", fontWeight: 600, marginBottom: "0.5rem" }}>
              Quyết định tuyển dụng chính thức (Attested Hiring Decision)
            </h2>
            <p style={{ color: "var(--text-muted)", fontSize: "0.8125rem", marginBottom: "1.5rem" }}>
              Theo quy chuẩn kiến trúc: AI không bao giờ tự đưa ra quyết định tuyển dụng. Con người (Owner) phải trực tiếp đối chiếu trích dẫn và chịu trách nhiệm pháp lý.
            </p>

            {decisions.length > 0 ? (
              <div style={{ padding: "1.25rem", background: "var(--bg-main)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-md)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                  <span className={`badge badge-${decisions[0].outcome === "advance" ? "open" : "draft"}`} style={{ fontSize: "1rem", padding: "0.4rem 0.8rem" }}>
                    {decisions[0].outcome.toUpperCase()}
                  </span>
                  <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                    Ký ngày: {new Date(decisions[0].created_at).toLocaleString("vi-VN")}
                  </span>
                </div>
                <p style={{ fontSize: "0.875rem", lineHeight: 1.6, color: "var(--text-primary)" }}>
                  <strong>Lý do quyết định:</strong> {decisions[0].reason}
                </p>
              </div>
            ) : (
              <form onSubmit={handleSubmitDecision}>
                <div className="form-group">
                  <label className="form-label">Kết luận tuyển dụng:</label>
                  <select
                    className="form-input"
                    value={decisionOutcome}
                    onChange={(e: any) => setDecisionOutcome(e.target.value)}
                  >
                    <option value="advance">Chuyển tiếp vòng phỏng vấn (ADVANCE)</option>
                    <option value="request_information">Yêu cầu bổ sung thông tin (REQUEST INFORMATION)</option>
                    <option value="not_advance">Từ chối / Không tiếp tục (NOT ADVANCE)</option>
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Giải trình quyết định của người duyệt (Tối thiểu 20 ký tự):</label>
                  <textarea
                    className="form-input"
                    rows={4}
                    placeholder="Nêu rõ căn cứ từ năng lực kỹ thuật, thiết kế hệ thống, các bằng chứng đã đối chiếu..."
                    value={decisionReason}
                    onChange={(e) => setDecisionReason(e.target.value)}
                    required
                  />
                </div>

                {/* Signed ReviewAttestation Checklist */}
                <div style={{ background: "var(--bg-main)", padding: "1rem", borderRadius: "var(--radius-sm)", marginBottom: "1.5rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  <div style={{ fontWeight: 600, fontSize: "0.875rem", color: "var(--accent-glow)" }}>
                    Bản cam kết ký duyệt có trách nhiệm (Review Attestation Checklist):
                  </div>

                  <label style={{ fontSize: "0.8125rem", display: "flex", alignItems: "flex-start", gap: "0.5rem", cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={attestCheck1}
                      onChange={(e) => setAttestCheck1(e.target.checked)}
                      style={{ marginTop: "0.2rem" }}
                    />
                    <span>1. Tôi đã đối chiếu trực tiếp các trích dẫn bằng chứng với văn bản ứng viên và xác nhận tính xác thực.</span>
                  </label>

                  <label style={{ fontSize: "0.8125rem", display: "flex", alignItems: "flex-start", gap: "0.5rem", cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={attestCheck2}
                      onChange={(e) => setAttestCheck2(e.target.checked)}
                      style={{ marginTop: "0.2rem" }}
                    />
                    <span>2. Tôi chịu trách nhiệm hoàn toàn về quyết định tuyển dụng độc lập của con người, không ủy quyền cho AI.</span>
                  </label>

                  <label style={{ fontSize: "0.8125rem", display: "flex", alignItems: "flex-start", gap: "0.5rem", cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={attestCheck3}
                      onChange={(e) => setAttestCheck3(e.target.checked)}
                      style={{ marginTop: "0.2rem" }}
                    />
                    <span>3. Tôi cam kết tuân thủ quy chuẩn không phân biệt đối xử dựa trên các đặc tính nhân khẩu học.</span>
                  </label>
                </div>

                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={submittingDecision || !attestCheck1 || !attestCheck2 || !attestCheck3}
                >
                  {submittingDecision ? "Đang ký duyệt..." : "Ký cam kết & Ban hành quyết định chính thức (Owner)"}
                </button>
              </form>
            )}
          </div>
        </div>
      )}

      {/* Tab 4: Interview Guide */}
      {activeTab === "interview" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          <div className="card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem", flexWrap: "wrap", gap: "0.75rem" }}>
              <div>
                <h2 style={{ fontSize: "1.25rem", fontWeight: 600 }}>Bộ câu hỏi phỏng vấn & Đào sâu</h2>
                <p style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>
                  Bao gồm câu hỏi chuẩn từ Ngân hàng Rubric và tối đa 3 câu hỏi đào sâu do AI gợi ý dựa trên lỗ hổng bằng chứng.
                </p>
              </div>

              <button
                className="btn btn-primary"
                onClick={handleTriggerInterview}
                disabled={triggeringInterview || !assessmentRun}
              >
                {triggeringInterview ? "Đang tạo câu hỏi..." : "+ Tạo câu hỏi đào sâu bằng AI"}
              </button>
            </div>

            {interviewDraft ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                {interviewDraft.candidate_followups && interviewDraft.candidate_followups.map((q: any, idx: number) => (
                  <div key={idx} style={{ padding: "1rem", background: "var(--bg-main)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-subtle)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                      <span className="badge badge-paused">Câu hỏi đào sâu {idx + 1} (Tiêu chí: {q.criterion_id})</span>
                      <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Trọng tâm: {q.focus_area}</span>
                    </div>
                    <p style={{ fontSize: "0.95rem", fontWeight: 500, color: "var(--text-primary)", marginBottom: "0.5rem" }}>
                      {q.question_text}
                    </p>
                    <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                      <strong>Dấu hiệu cần tìm kiếm:</strong> {q.what_to_look_for}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
                Chưa tạo bản thảo câu hỏi phỏng vấn riêng cho ứng viên này. Bấm &quot;Tạo câu hỏi đào sâu bằng AI&quot; để tạo.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Quote Drawer Modal */}
      {selectedEvidence && (
        <div className="modal-backdrop" onClick={() => setSelectedEvidence(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ fontSize: "1.25rem", fontWeight: 600, marginBottom: "0.5rem" }}>
              Chi tiết trích dẫn bằng chứng (Exact Span Provenance)
            </h2>
            <div style={{ fontFamily: "monospace", color: "var(--accent-glow)", fontSize: "0.8125rem", marginBottom: "1rem" }}>
              Mã: {selectedEvidence.span_id} • Codepoints: [{selectedEvidence.resolved_start_cp}..{selectedEvidence.resolved_end_cp}]
            </div>

            <div style={{
              background: "var(--bg-main)",
              padding: "1rem",
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--border-subtle)",
              fontSize: "0.9375rem",
              lineHeight: 1.6,
              color: "var(--text-primary)",
              fontStyle: "italic",
              marginBottom: "1.5rem",
            }}>
              &ldquo;{selectedEvidence.quote}&rdquo;
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button className="btn btn-secondary" onClick={() => setSelectedEvidence(null)}>
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Deletion Request Modal (B17) */}
      {showDeleteModal && (
        <div className="modal-backdrop">
          <div className="modal-content">
            <h2 style={{ fontSize: "1.25rem", fontWeight: 600, color: "var(--danger)", marginBottom: "0.5rem" }}>
              Yêu cầu xóa dữ liệu vĩnh viễn (Data Deletion)
            </h2>
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", marginBottom: "1.5rem" }}>
              Theo quy định B17 & GDPR: Bản ghi sẽ được đánh dấu xóa tombstone ngay lập tức, tệp nhị phân trong kho bị hủy liên kết, hủy mọi tiến trình worker đang chạy.
            </p>

            <div className="form-group">
              <label className="form-label">Phạm vi xóa:</label>
              <select
                className="form-input"
                value={deleteScope}
                onChange={(e: any) => setDeleteScope(e.target.value)}
              >
                <option value="application">Chỉ xóa Hồ sơ ứng tuyển này (Application)</option>
                <option value="candidate">Xóa toàn bộ Ứng viên & Các hồ sơ liên quan (Candidate)</option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Lý do yêu cầu xóa:</label>
              <select
                className="form-input"
                value={deleteReason}
                onChange={(e) => setDeleteReason(e.target.value)}
              >
                <option value="candidate_request">Yêu cầu từ ứng viên (GDPR Right to be Forgotten)</option>
                <option value="retention_expired">Hết hạn thời gian lưu trữ theo chính sách</option>
                <option value="legal_obligation">Yêu cầu pháp lý bắt buộc</option>
              </select>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "1.5rem" }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setShowDeleteModal(false)}
                disabled={deleting}
              >
                Hủy
              </button>
              <button
                type="button"
                className="btn btn-primary"
                style={{ background: "var(--danger)", borderColor: "var(--danger)" }}
                onClick={handleDeleteConfirm}
                disabled={deleting}
              >
                {deleting ? "Đang xóa dữ liệu..." : "Xác nhận xóa vĩnh viễn"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
