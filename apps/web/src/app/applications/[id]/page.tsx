"use client";

import React, { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, AssessmentRunData, UserAccount } from "@/lib/api";
import {
  IconShield,
  IconSparkles,
  IconCheckCircle,
  IconAlertTriangle,
  IconLock,
  IconQuote,
  IconTrash,
  IconArrowRight,
  IconX,
  IconUserCheck,
  IconFileText,
  IconMessageSquare,
  IconSliders
} from "@/components/Icons";
import { useToast } from "@/components/Toast";
import HRRevisionEditor from "@/components/HRRevisionEditor";
import CandidateCopilot from "@/components/CandidateCopilot";
import RawPdfViewer from "@/components/RawPdfViewer";
import { stageLabels } from "@/lib/workflow";
import { SkeletonDossier } from "@/components/Skeleton";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function ApplicationWorkspacePage({ params }: PageProps) {
  const { id } = use(params);
  const { success, error: toastError, warning, info } = useToast();

  const [application, setApplication] = useState<any>(null);
  const [requisition, setRequisition] = useState<any>(null);
  const [rubric, setRubric] = useState<any>(null);
  const [sanitizedVersion, setSanitizedVersion] = useState<any>(null);
  const [currentUser, setCurrentUser] = useState<UserAccount | null>(null);
  const [grantingRawAccess, setGrantingRawAccess] = useState(false);
  const [rawAccessError, setRawAccessError] = useState<string | null>(null);
  const [rawPreviewBlob, setRawPreviewBlob] = useState<Blob | null>(null);
  const [rawPreviewLoading, setRawPreviewLoading] = useState(false);
  const [rawPreviewExpiresAt, setRawPreviewExpiresAt] = useState<number | null>(null);
  const rawPreviewTimerRef = useRef<number | null>(null);
  const [assessmentRun, setAssessmentRun] = useState<AssessmentRunData | null>(null);
  const [hrRevisions, setHrRevisions] = useState<any[]>([]);
  const [decisions, setDecisions] = useState<any[]>([]);
  const [interviewDraft, setInterviewDraft] = useState<any>(null);
  const [questionBanks, setQuestionBanks] = useState<any[]>([]);
  const [interviewScorecards, setInterviewScorecards] = useState<any[]>([]);
  const [scorecardRoundNo, setScorecardRoundNo] = useState(1);
  const [scorecardCriteria, setScorecardCriteria] = useState<any[]>([]);
  const [scorecardDirty, setScorecardDirty] = useState(false);
  const [savingScorecard, setSavingScorecard] = useState(false);

  const [activeTab, setActiveTab] = useState<"assessment" | "sanitization" | "revision" | "interview">("sanitization");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Quote drawer state
  const [selectedEvidence, setSelectedEvidence] = useState<any | null>(null);

  // Sanitization action state
  const [approvingSanitized, setApprovingSanitized] = useState(false);
  const [acknowledgedSanitization, setAcknowledgedSanitization] = useState(false);
  const [confirmedDocumentIsCv, setConfirmedDocumentIsCv] = useState(false);
  const [editingSanitization, setEditingSanitization] = useState(false);
  const [editedSanitizedText, setEditedSanitizedText] = useState("");
  const [sanitizationEditReason, setSanitizationEditReason] = useState("");
  const [savingSanitization, setSavingSanitization] = useState(false);

  // Assessment action state
  const [triggeringAssessment, setTriggeringAssessment] = useState(false);

  // Deletion modal
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteScope, setDeleteScope] = useState<"application" | "candidate">("application");
  const [deleteReason, setDeleteReason] = useState("candidate_request");
  const [deleting, setDeleting] = useState(false);

  // Decision Form state
  const [decisionOutcome, setDecisionOutcome] = useState<"advance" | "request_information" | "not_advance">("request_information");
  const [decisionReason, setDecisionReason] = useState("");
  const [attestCheck1, setAttestCheck1] = useState(false);
  const [attestCheck2, setAttestCheck2] = useState(false);
  const [attestCheck3, setAttestCheck3] = useState(false);
  const [submittingDecision, setSubmittingDecision] = useState(false);

  // Interview state
  const [triggeringInterview, setTriggeringInterview] = useState(false);

  const [progress, setProgress] = useState<any>(null);
  const [loadWarnings, setLoadWarnings] = useState<string[]>([]);
  const [editingCriterion, setEditingCriterion] = useState<string | null>(null);
  const [reviewedIds, setReviewedIds] = useState<string[]>([]);
  const initialTab = useRef(false);
  const refreshing = useRef(false);
  const canManage = requisition?.my_role === "owner";
  const canInterview = requisition?.my_role === "owner" || requisition?.my_role === "reviewer";
  const currentScorecard = interviewScorecards.find((card) =>
    card.interviewer_id === currentUser?.id && card.round_no === scorecardRoundNo
    && card.rubric_version_id === requisition?.current_rubric_version_id
  ) || null;
  const effectiveRevision = hrRevisions.find(r => r.status === "finalized" && !r.is_stale && r.application_generation === application?.generation && r.document_id === application?.current_document_id && r.sanitized_version_id === application?.current_sanitized_version_id && r.rubric_version_id === requisition?.current_rubric_version_id);

  function closeRawPreview(expired = false) {
    setRawPreviewBlob(null);
    setRawPreviewExpiresAt(null);
    if (rawPreviewTimerRef.current) window.clearTimeout(rawPreviewTimerRef.current);
    rawPreviewTimerRef.current = null;
    if (expired) setRawAccessError("Quyền xem CV gốc đã hết hạn. Hãy cấp lại quyền để tiếp tục đối chiếu.");
  }

  useEffect(() => () => {
    if (rawPreviewTimerRef.current) window.clearTimeout(rawPreviewTimerRef.current);
  }, []);

  useEffect(() => {
    if (activeTab !== "sanitization" && rawPreviewBlob) closeRawPreview();
  }, [activeTab]);

  async function loadData(silent = false) {
    if (refreshing.current) return;
    refreshing.current = true;
    if (!silent) setLoading(true);
    setError(null);
    try {
      const user = await api.getMe(); setCurrentUser(user);
      const app = await api.getApplication(id); setApplication(app);
      const req: any = await api.getRequisition(app.requisition_id); setRequisition(req);
      if (req.my_role === "reviewer") {
        const independent = await api.getIndependentReviewContext(id);
        if (!independent.already_submitted) { window.location.replace(`/applications/${id}/independent-review`); return; }
      }
      const requests = [
        req.current_rubric_version_id ? api.getRubric(req.current_rubric_version_id) : Promise.resolve(null),
        req.current_rubric_version_id ? api.getQuestionBank(req.current_rubric_version_id) : Promise.resolve([]),
        app.current_sanitized_version_id ? api.getSanitizedDetail(app.current_sanitized_version_id) : Promise.resolve(null),
        app.current_assessment_run_id ? api.getAssessmentRun(id, app.current_assessment_run_id) : Promise.resolve(null),
        api.listHRRevisions(id), api.listDecisions(id), api.getLatestInterviewDraft(id), api.getApplicationProgress(id),
        api.getInterviewScorecards(id),
      ];
      const results = await Promise.allSettled(requests);
      const value = (index: number, fallback: any) => results[index].status === "fulfilled" ? (results[index] as PromiseFulfilledResult<any>).value : fallback;
      const names = ["tiêu chí", "câu hỏi chuẩn", "CV đã che", "đánh giá AI", "bản điều chỉnh HR", "quyết định", "gợi ý phỏng vấn", "trạng thái xử lý", "phiếu phỏng vấn"];
      const warnings = results.flatMap((result, index) => result.status === "rejected" && !(index === 2 && String(result.reason.message).includes("403")) ? [`Không tải được ${names[index]}: ${result.reason.message}`] : []);
      setLoadWarnings(warnings);
      setRubric(value(0, null)); setQuestionBanks(value(1, [])); setSanitizedVersion(value(2, null));
      const run = value(3, null); setAssessmentRun(run?.status === "succeeded" && !run.is_stale && value(7, null)?.assessment_status === "succeeded" ? run : null);
      setHrRevisions(value(4, [])); setDecisions(value(5, [])); setInterviewDraft(value(6, null)); setProgress(value(7, null));
      setInterviewScorecards(value(8, []));
      if (!initialTab.current) {
        setActiveTab(value(2, null)?.status !== "approved" ? "sanitization" : value(5, []).length ? "interview" : "assessment");
        initialTab.current = true;
      }
    } catch (err: any) { setError(err.message || "Không tải được hồ sơ. Hãy thử lại."); }
    finally { setLoading(false); refreshing.current = false; }
  }

  useEffect(() => {
    if (!progress?.pending && !["reading", "analyzing"].includes(progress?.stage)) return;
    const timer = window.setInterval(() => { if (document.visibilityState === "visible") void loadData(true); }, 4000);
    return () => window.clearInterval(timer);
  }, [id, progress?.pending, progress?.stage]);

  useEffect(() => { setReviewedIds([]); setAttestCheck1(false); setAttestCheck2(false); setAttestCheck3(false); }, [application?.generation, assessmentRun?.id, effectiveRevision?.id]);

  useEffect(() => {
    initialTab.current = false;
    setScorecardRoundNo(1);
    setScorecardDirty(false);
    void loadData();
  }, [id]);

  useEffect(() => {
    if (scorecardDirty || !rubric?.criteria?.length) return;
    const saved = interviewScorecards.find((card) =>
      card.interviewer_id === currentUser?.id && card.round_no === scorecardRoundNo
      && card.rubric_version_id === requisition?.current_rubric_version_id
    );
    setScorecardCriteria(saved?.criteria || rubric.criteria.map((criterion: any) => ({
      criterion_id: criterion.id,
      outcome: "not_observed",
      score: null,
      answer_summary: "",
      interviewer_note: "",
    })));
  }, [rubric?.id, interviewScorecards, currentUser?.id, requisition?.current_rubric_version_id, scorecardRoundNo, scorecardDirty]);

  useEffect(() => {
    if (!interviewDraft?.id || !["queued", "running"].includes(interviewDraft.status)) return;
    let active = true;
    const timer = window.setInterval(async () => {
      try {
        const latest = await api.getInterviewDraftDetail(interviewDraft.id);
        if (active) setInterviewDraft(latest);
      } catch (err) {
        if (active) console.warn("Could not refresh interview draft:", err);
      }
    }, 2500);
    return () => { active = false; window.clearInterval(timer); };
  }, [interviewDraft?.id, interviewDraft?.status]);

  async function handleApproveSanitization() {
    if (!sanitizedVersion) return;
    if (!acknowledgedSanitization) {
      warning("Vui lòng tích chọn xác nhận đã kiểm tra thông tin đã che.");
      return;
    }
    const requiresDocumentTypeConfirmation = sanitizedVersion.quality_flags?.document_type_hint !== "cv";
    if (requiresDocumentTypeConfirmation && !confirmedDocumentIsCv) {
      warning("Hệ thống chưa xác nhận chắc chắn đây là CV. Hãy đối chiếu bản gốc và xác nhận trước khi cho phép AI xử lý.");
      return;
    }
    setApprovingSanitized(true);
    try {
      await api.approveSanitizedVersion(sanitizedVersion.id, application.row_version, sanitizedVersion.sha256, confirmedDocumentIsCv);
      success("Đã phê duyệt phiên bản khử định danh thành công!");
      await loadData();
      setActiveTab("assessment");
    } catch (err: any) {
      toastError(err.message || "Lỗi phê duyệt khử định danh");
    } finally {
      setApprovingSanitized(false);
    }
  }

  async function handleGrantRawAccess() {
    if (!currentUser || !application?.current_document_id) return;
    setGrantingRawAccess(true);
    setRawPreviewLoading(true);
    setRawAccessError(null);
    try {
      const currentDocument = application.documents?.find((document: any) => document.id === application.current_document_id);
      if (currentDocument?.mime_verified !== "application/pdf") {
        throw new Error("Xem trực tiếp hiện hỗ trợ PDF. Tệp này chưa có bản PDF để xem trong ứng dụng.");
      }
      closeRawPreview();
      const grant = await api.createRawGrant(
        id,
        currentUser.id,
        "Kiểm tra bản CV đã che thông tin định danh trước khi đánh giá",
        30
      );
      const blob = await api.getRawDocumentPreview(application.current_document_id);
      setRawPreviewBlob(blob);
      const expiresAt = new Date(grant.expires_at).getTime();
      setRawPreviewExpiresAt(expiresAt);
      rawPreviewTimerRef.current = window.setTimeout(() => closeRawPreview(true), Math.max(0, expiresAt - Date.now()));
      success("CV gốc đã mở. Quyền và bản xem sẽ tự hết hạn sau 30 phút.");
    } catch (err: any) {
      setRawAccessError(err.message || "Không thể cấp quyền xem CV gốc.");
      toastError(err.message || "Không thể cấp quyền xem CV gốc.");
    } finally {
      setRawPreviewLoading(false);
      setGrantingRawAccess(false);
    }
  }

  async function handleSaveSanitization() {
    if (!application?.current_document_id || !sanitizedVersion) return;
    if (editedSanitizedText.trim().length < 10 || sanitizationEditReason.trim().length < 5) return;
    setSavingSanitization(true);
    try {
      await api.editSanitizedVersion(
        application.current_document_id,
        sanitizedVersion.id,
        editedSanitizedText,
        sanitizationEditReason.trim()
      );
      setEditingSanitization(false);
      setAcknowledgedSanitization(false);
      setSanitizationEditReason("");
      success("Đã lưu nội dung khử định danh mới.");
      await loadData();
    } catch (err: any) {
      toastError(err.message || "Không thể lưu bản đã che");
    } finally {
      setSavingSanitization(false);
    }
  }

  async function handleTriggerAssessment() {
    if (sanitizedVersion?.status !== "approved" || !requisition?.current_rubric_version_id) {
      warning("Cần HR duyệt bản đã che thông tin và có bộ tiêu chí được phê duyệt.");
      return;
    }
    setTriggeringAssessment(true);
    try {
      await api.triggerAssessment(
        id,
        sanitizedVersion.id,
        requisition.current_rubric_version_id
      );
      success("Đã đưa yêu cầu đánh giá AI vào hàng đợi xử lý.");
      await loadData();
    } catch (err: any) {
      toastError(err.message || "Lỗi kích hoạt đánh giá");
    } finally {
      setTriggeringAssessment(false);
    }
  }

  async function handleSubmitDecision(e: React.FormEvent) {
    e.preventDefault();
    if (!attestCheck1 || !attestCheck2 || !attestCheck3 || reviewedIds.length !== rubric?.criteria?.length || loadWarnings.length > 0) {
      warning("Bạn phải cam kết đầy đủ cả 3 điều khoản ký duyệt trước khi ban hành quyết định.");
      return;
    }
    if (decisionReason.trim().length < 20) {
      warning("Lý do quyết định phải dài tối thiểu 20 ký tự.");
      return;
    }

    setSubmittingDecision(true);
    try {
      let effectiveKind: "assessment_run" | "hr_revision" = "assessment_run";
      let effectiveId = assessmentRun?.id;
      if (effectiveRevision) {
        effectiveKind = "hr_revision";
        effectiveId = effectiveRevision.id;
      }

      if (!effectiveId) {
        throw new Error("Chưa có kết quả đánh giá hoặc bản sửa đổi HR hợp lệ để làm cơ sở ra quyết định.");
      }
      if (!rubric?.criteria || rubric.criteria.length === 0) {
        throw new Error("Không tải được tiêu chí từ rubric đã duyệt. Vui lòng tải lại trước khi ký duyệt.");
      }

      const attestation = await api.createReviewAttestation(id, {
        decision_basis: "assessment_review",
        effective_result: {
          kind: effectiveKind,
          id: effectiveId,
        },
        reviewed_criterion_ids: reviewedIds,
        acknowledged: true,
      });

      await api.createFinalDecision(id, {
        decision_basis: "assessment_review",
        outcome: decisionOutcome,
        reason: decisionReason,
        attestation_id: attestation.id,
        expected_rubric_version_id: rubric?.id,
      });

      success("Quyết định tuyển dụng đã được ban hành và ký cam kết thành công!");
      await loadData();
    } catch (err: any) {
      toastError(err.message || "Lỗi ban hành quyết định");
    } finally {
      setSubmittingDecision(false);
    }
  }

  async function handleTriggerInterview() {
    const activeBank = questionBanks.find((bank) => bank.status === "approved");
    setTriggeringInterview(true);
    try {
      let effectiveKind = "assessment_run";
      let effectiveId = assessmentRun?.id;
      if (effectiveRevision) {
        effectiveKind = "hr_revision";
        effectiveId = effectiveRevision.id;
      }

      const draft = await api.triggerInterviewDraft(
        id,
        { kind: effectiveKind, id: effectiveId },
        activeBank?.id ?? null
      );
      setInterviewDraft(draft);
      info(activeBank
        ? "Đã xếp hàng tạo câu hỏi theo hồ sơ và câu hỏi chuẩn đã duyệt."
        : "Đã xếp hàng tạo câu hỏi làm rõ theo hồ sơ.");
    } catch (err: any) {
      toastError(err.message || "Lỗi tạo câu hỏi phỏng vấn");
    } finally {
      setTriggeringInterview(false);
    }
  }

  function updateScorecardCriterion(criterionId: string, patch: Record<string, unknown>) {
    setScorecardDirty(true);
    setScorecardCriteria((current) => current.map((row) =>
      row.criterion_id === criterionId ? { ...row, ...patch } : row
    ));
  }

  function validateScorecardRows(rows: any[], requireObserved: boolean) {
    const assessed = rows.filter((row) => row.outcome === "assessed");
    const invalidAssessed = assessed.find((row) => !Number.isInteger(row.score)
      || row.score < 0 || row.score > 4 || (row.answer_summary || "").trim().length < 20);
    if (invalidAssessed) {
      const label = rubric?.criteria?.find((item: any) => item.id === invalidAssessed.criterion_id)?.label || invalidAssessed.criterion_id;
      warning(`Tiêu chí “${label}” cần chọn điểm 0–4 và ghi căn cứ câu trả lời tối thiểu 20 ký tự.`);
      return false;
    }
    if (requireObserved && assessed.length === 0) {
      warning("Cần đánh giá ít nhất một tiêu chí trước khi nộp phiếu.");
      return false;
    }
    const unresolvedConflict = requireObserved && rows.find((row) => row.outcome === "conflicting_evidence"
      && (row.answer_summary || "").trim().length < 20);
    if (unresolvedConflict) {
      const label = rubric?.criteria?.find((item: any) => item.id === unresolvedConflict.criterion_id)?.label || unresolvedConflict.criterion_id;
      warning(`Tiêu chí “${label}” cần ghi rõ nội dung mâu thuẫn tối thiểu 20 ký tự trước khi nộp.`);
      return false;
    }
    return true;
  }

  async function handleSaveInterviewScorecard() {
    if (!canInterview || !rubric || !scorecardCriteria.length) return;
    if (!validateScorecardRows(scorecardCriteria, false)) return;
    if (currentScorecard?.status === "finalized" || currentScorecard?.is_stale) {
      warning("Phiếu này đã khóa hoặc đã cũ. Hãy mở lượt phỏng vấn mới theo rubric hiện hành.");
      return;
    }
    setSavingScorecard(true);
    try {
      const saved = await api.saveInterviewScorecard(id, {
        round_no: scorecardRoundNo,
        expected_version: currentScorecard?.row_version ?? 0,
        interview_draft_id: interviewDraft?.status === "succeeded" && !interviewDraft?.is_stale ? interviewDraft.id : null,
        criteria: scorecardCriteria,
      });
      setInterviewScorecards((cards) => [
        ...cards.filter((card) => !(card.interviewer_id === saved.interviewer_id
          && card.round_no === saved.round_no && card.rubric_version_id === saved.rubric_version_id)),
        saved,
      ]);
      setScorecardDirty(false);
      success("Đã lưu phiếu phỏng vấn nháp của bạn.");
    } catch (err: any) {
      toastError(err.message || "Không thể lưu phiếu phỏng vấn.");
    } finally {
      setSavingScorecard(false);
    }
  }

  async function handleFinalizeInterviewScorecard() {
    if (!currentScorecard || currentScorecard.status !== "draft" || currentScorecard.is_stale) return;
    if (!validateScorecardRows(currentScorecard.criteria, true)) return;
    if (scorecardDirty) {
      warning("Hãy lưu thay đổi trước khi nộp và khóa phiếu.");
      return;
    }
    if (!window.confirm("Nộp và khóa phiếu chấm của bạn? Phiếu đã nộp không thể sửa; hãy kiểm tra điểm và ghi chú trước khi tiếp tục.")) return;
    setSavingScorecard(true);
    try {
      const finalized = await api.finalizeInterviewScorecard(currentScorecard.id, currentScorecard.row_version);
      setInterviewScorecards((cards) => cards.map((card) => card.id === finalized.id ? finalized : card));
      success("Đã nộp và khóa phiếu phỏng vấn.");
    } catch (err: any) {
      toastError(err.message || "Không thể nộp phiếu phỏng vấn.");
    } finally {
      setSavingScorecard(false);
    }
  }

  async function handleDeleteConfirm() {
    setDeleting(true);
    try {
      const result = await api.requestDeletion(deleteScope, deleteScope === "candidate" ? application.candidate_id : id, deleteReason);
      success(`Đã tạo yêu cầu xóa ${result.id}. Trạng thái: ${result.status}. Theo dõi tại mục Lưu giữ dữ liệu.`);
      setShowDeleteModal(false);
      await loadData();
    } catch (err: any) {
      toastError(err.message || "Lỗi xóa dữ liệu");
    } finally {
      setDeleting(false);
    }
  }

  if (loading) {
    return <SkeletonDossier />;
  }

  if (error || !application) {
    return (
      <div className="card" style={{ borderColor: "var(--rose-border)", maxWidth: "600px", margin: "3rem auto", textAlign: "center" }}>
        <div style={{ width: "48px", height: "48px", borderRadius: "50%", background: "var(--rose-bg)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 1rem auto" }}>
          <IconAlertTriangle size={24} color="var(--rose-text)" />
        </div>
        <h2 style={{ color: "var(--rose-text)", marginBottom: "0.5rem" }}>Không Tìm Thấy Hồ Sơ</h2>
        <p style={{ color: "var(--text-secondary)", marginBottom: "1.5rem" }}>{error}</p>
        <Link href="/requisitions" className="btn btn-secondary">
          Quay lại danh sách đợt tuyển dụng
        </Link>
      </div>
    );
  }

  return (
    <div>
      {/* Top Header Bar — Strictly Spec 01: Evidence-first (NO hero score) */}
      <div className="page-header" style={{ marginBottom: "1.5rem" }}>
        <div>
          <div className="breadcrumbs">
            <Link href="/">Trang chủ</Link>
            <span>/</span>
            <Link href={application.requisition_id ? `/requisitions/${application.requisition_id}` : "/requisitions"}>
              {requisition?.title || "Đợt tuyển dụng"}
            </Link>
            <span>/</span>
            <span style={{ color: "var(--text-primary)", fontFamily: "var(--font-mono)" }}>
              {application.public_label}
            </span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.85rem", flexWrap: "wrap" }}>
            <h1 className="page-title" style={{ fontFamily: "var(--font-mono)", color: "var(--accent-cyan)", letterSpacing: "0.02em" }}>
              {application.public_label}
            </h1>
            <span className={`badge badge-${application.status}`}>
              {application.status.toUpperCase()}
            </span>
            <span className="badge badge-subtle">
              Bản hồ sơ {application.generation}
            </span>
          </div>

          <p className="page-subtitle">
            {sanitizedVersion?.status === "approved" ? "Bản đã che được HR duyệt" : "Bản đã che cần HR kiểm tra"} • Tiếp nhận lúc: {new Date(application.received_at).toLocaleString("vi-VN")}
          </p>
        </div>

        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => void loadData()}>Làm mới trạng thái</button>
          <button
            className="btn btn-danger btn-sm"
            onClick={() => setShowDeleteModal(true)}
          >
            <IconTrash size={14} />
            <span>Yêu cầu xóa hồ sơ</span>
          </button>
        </div>
      </div>

      {loadWarnings.length > 0 && <div role="alert" className="notice notice-error">{loadWarnings.map(message => <p key={message}>{message}</p>)}<button className="btn btn-secondary" onClick={() => void loadData()}>Thử tải lại</button></div>}
      <section className="workflow-next card" role="status" aria-live="polite">
        <div><strong>{stageLabels[progress?.stage] || "Chưa xác định trạng thái"}</strong><p className="muted">{progress?.failure_code ? `Lỗi: ${progress.failure_code}. Kiểm tra nguồn trước khi thử lại.` : "Rà soát CV → phân tích → kiểm tra bằng chứng → quyết định → chuẩn bị phỏng vấn."}</p></div>
        {!progress?.pending && <button className="btn btn-primary" disabled={!!loadWarnings.length || !progress || application.status !== "active"} onClick={() => {
          if (["awaiting_upload", "reading", "needs_review"].includes(progress.stage)) setActiveTab("sanitization");
          else if (progress.stage === "ready_for_ai") { setActiveTab("assessment"); if (canManage) void handleTriggerAssessment(); }
          else if (progress.stage === "completed") setActiveTab("interview"); else setActiveTab("assessment");
        }}>{progress?.stage === "ready_for_ai" && canManage ? "Phân tích CV" : progress?.stage === "completed" ? "Chuẩn bị phỏng vấn" : progress?.stage === "needs_review" ? "Rà soát CV" : "Xem bước cần xử lý"}</button>}
      </section>
      <nav className="tabs-container" aria-label="Các bước xử lý hồ sơ">
        {([['sanitization','1. Rà soát CV'],['assessment','2. Đánh giá và bằng chứng'],['revision','3. Quyết định của HR'],['interview','4. Chuẩn bị phỏng vấn']] as const).map(([tab,label]) =>
          <button key={tab} className={`tab-btn ${activeTab === tab ? "active" : ""}`} aria-current={activeTab === tab ? "step" : undefined} onClick={() => setActiveTab(tab)}>{label}</button>)}
      </nav>

      {/* Tab 1: Evidence-first Assessment */}
      {activeTab === "assessment" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
          {!assessmentRun ? (
            <div className="card" style={{ textAlign: "center", padding: "4rem 1.5rem" }}>
              <div style={{ width: "52px", height: "52px", borderRadius: "50%", background: "rgba(56, 189, 248, 0.1)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 1.25rem auto" }}>
                <IconSparkles size={28} color="#38bdf8" />
              </div>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: "0.5rem" }}>
                {progress?.stage === "analyzing" ? "AI đang phân tích hồ sơ" : progress?.stage === "error" ? "Phân tích gặp lỗi" : "Hồ sơ chưa có kết quả đánh giá AI"}
              </h2>
              <p style={{ color: "var(--text-secondary)", maxWidth: "620px", margin: "0 auto 1.5rem auto", fontSize: "0.875rem", lineHeight: 1.6 }}>
                Hệ thống sẽ đối chiếu nội dung CV đã khử định danh với các tiêu chí trong rubric đã được HR duyệt. Mỗi nhận định đều có trích dẫn nguyên văn để con người kiểm chứng.
              </p>
              <button
                className="btn btn-primary"
                onClick={handleTriggerAssessment}
                disabled={!canManage || !!loadWarnings.length || progress?.pending || triggeringAssessment || sanitizedVersion?.status !== "approved" || !requisition?.current_rubric_version_id}
              >
                <IconSparkles size={16} />
                <span>{triggeringAssessment ? "Đang xử lý đánh giá AI…" : "Chạy Đánh Giá Bằng Chứng AI Ngay"}</span>
              </button>
              {sanitizedVersion?.status !== "approved" && (
                <p style={{ color: "var(--amber-text)", fontSize: "0.8rem", marginTop: "0.75rem" }}>
                  Cần HR duyệt bản đã che thông tin định danh trước khi chạy đánh giá.
                </p>
              )}
            </div>
          ) : (
            <div>
              {/* Recommendation & Confidence Banner */}
              <div className="card assessment-summary" style={{ marginBottom: "1.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1.25rem" }}>
                  <div>
                    <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>
                      Gợi Ý Đánh Giá Hệ Thống
                    </span>
                    <div style={{ marginTop: "0.35rem" }}>
                      <span className={`badge ${assessmentRun.recommendation === "consider_next_round" ? "badge-rec-advance" : assessmentRun.recommendation === "needs_clarification" ? "badge-rec-clarify" : "badge-rec-review"}`} style={{ fontSize: "0.875rem", padding: "0.35rem 0.85rem" }}>
                        {assessmentRun.recommendation === "consider_next_round" && "Cân nhắc vòng tiếp theo"}
                        {assessmentRun.recommendation === "needs_clarification" && "Cần làm rõ thông tin"}
                        {assessmentRun.recommendation === "review_required" && "Cần HR đối chiếu trực tiếp"}
                      </span>
                    </div>
                  </div>

                  <div style={{ display: "flex", flexWrap: "wrap", gap: "1.5rem", alignItems: "center" }}>
                    <div title="Tỷ lệ trọng số các tiêu chí tìm thấy bằng chứng trích dẫn trong CV">
                      <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600, display: "flex", alignItems: "center", gap: "0.25rem" }}>
                        <span>Độ Phủ Bằng Chứng</span>
                        <span style={{ cursor: "help", color: "var(--text-muted)", fontSize: "0.75rem" }} title="Tỷ lệ trọng số các tiêu chí tìm thấy bằng chứng trích dẫn trong CV">ⓘ</span>
                      </div>
                      <div style={{ fontSize: "1.45rem", fontWeight: 800, color: "var(--text-primary)", fontFamily: "var(--font-mono)" }}>
                        {(assessmentRun.coverage * 100).toFixed(0)}%
                      </div>
                    </div>
                    <div title="Điểm chuẩn hóa quy đổi trên thang 100 dựa trên các tiêu chí đã có bằng chứng xác thực trong hồ sơ">
                      <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600, display: "flex", alignItems: "center", gap: "0.25rem" }}>
                        <span>Điểm Quan Sát</span>
                        <span style={{ cursor: "help", color: "var(--accent-cyan)", fontSize: "0.75rem" }} title="Điểm chuẩn hóa quy đổi trên thang 100 dựa trên các tiêu chí đã có bằng chứng xác thực trong hồ sơ">ⓘ</span>
                      </div>
                      <div style={{ fontSize: "1.45rem", fontWeight: 800, color: "var(--accent-cyan)", fontFamily: "var(--font-mono)" }}>
                        {assessmentRun.observed_score ?? "N/A"}<span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>/100</span>
                      </div>
                    </div>
                    <div title="Điểm dùng để xếp hạng ứng viên với nhau. Chỉ xuất hiện khi 100% tiêu chí được đánh giá đầy đủ, không thiếu bằng chứng hoặc mâu thuẫn">
                      <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600, display: "flex", alignItems: "center", gap: "0.25rem" }}>
                        <span>Điểm Đối Chiếu</span>
                        <span style={{ cursor: "help", color: "var(--text-muted)", fontSize: "0.75rem" }} title="Điểm dùng để xếp hạng ứng viên với nhau. Chỉ xuất hiện khi 100% tiêu chí được đánh giá đầy đủ, không thiếu bằng chứng hoặc mâu thuẫn">ⓘ</span>
                      </div>
                      <div style={{ fontSize: "1.45rem", fontWeight: 800, color: "var(--text-primary)", fontFamily: "var(--font-mono)" }}>
                        {assessmentRun.comparable_score ?? "N/A"}<span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>/100</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {assessmentRun.secondary_model_output && (
                <section className="card" aria-label="Kết quả đối chiếu Jev" style={{ marginBottom: "1.5rem", borderColor: "var(--border-subtle)" }}>
                  <div className="card-header" style={{ marginBottom: "0.75rem" }}>
                    <h2 className="card-title">Ý kiến mô hình thứ hai · Jev shadow</h2>
                    <p style={{ color: "var(--text-secondary)", fontSize: "0.825rem", marginTop: "0.25rem" }}>
                      Chỉ đối chiếu độc lập trên bằng chứng đã trích dẫn. Điểm Jev không thay đổi điểm, gợi ý hay quyết định của HR.
                    </p>
                  </div>
                  {assessmentRun.secondary_model_output.status === "succeeded" ? (
                    <>
                      <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginBottom: "0.75rem" }}>
                        Model: {assessmentRun.secondary_model_output.reported_model || assessmentRun.secondary_model_output.requested_model}
                      </p>
                      <div className="table-wrapper" style={{ border: "none" }}>
                        <table className="data-table">
                          <thead><tr><th>Tiêu chí</th><th>DeepSeek</th><th>Jev</th><th>Độ tin cậy Jev</th><th>Chênh lệch</th></tr></thead>
                          <tbody>
                            {Object.entries(assessmentRun.secondary_model_output.evaluations || {}).map(([criterionId, result]) => (
                              <tr key={criterionId}>
                                <td><strong>{rubric?.criteria?.find((criterion: any) => criterion.id === criterionId)?.label || criterionId}</strong></td>
                                <td>{result.deepseek_score}/4</td>
                                <td>{result.score.toFixed(2)}/4</td>
                                <td>{(result.confidence * 100).toFixed(0)}%</td>
                                <td>{result.delta_from_deepseek > 0 ? "+" : ""}{result.delta_from_deepseek.toFixed(2)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginTop: "0.75rem" }}>
                        Độ tin cậy mô tả mức tập trung của phân bố dự đoán, không phải xác suất Jev đúng. HR cần mở trích dẫn CV để tự xác minh.
                      </p>
                    </>
                  ) : assessmentRun.secondary_model_output.status === "skipped_insufficient_evidence" ? (
                    <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>Không gửi sang Jev vì chưa có tiêu chí nào đủ bằng chứng CV đã xác minh.</p>
                  ) : (
                    <p style={{ color: "var(--amber-text)", fontSize: "0.85rem" }}>Không lấy được ý kiến Jev trong lần chạy này. Kết quả đánh giá chính vẫn giữ nguyên; mã lỗi: {assessmentRun.secondary_model_output.error_code || "JEV_SHADOW_FAILED"}.</p>
                  )}
                </section>
              )}

              {/* Criteria Evidence Cards */}
              <div className="card">
                <div className="card-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
                  <div>
                    <h2 className="card-title">Bảng Tiêu Chí Năng Lực &amp; Chuỗi Bằng Chứng Minh Bạch</h2>
                    <p style={{ color: "var(--text-secondary)", fontSize: "0.825rem", marginTop: "0.2rem" }}>
                      Mở đoạn trích để đối chiếu với CV. Chưa đủ bằng chứng không đồng nghĩa ứng viên không có năng lực.
                    </p>
                  </div>
                  {rubric?.criteria && rubric.criteria.length > 0 && (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => {
                        const allIds = rubric.criteria.map((c: any) => c.id);
                        const isAllSelected = allIds.every((critId: string) => reviewedIds.includes(critId));
                        setReviewedIds(isAllSelected ? [] : allIds);
                      }}
                      title="Đánh dấu tất cả tiêu chí đã được rà soát đối chiếu"
                    >
                      <IconCheckCircle size={14} color="var(--accent-cyan)" />
                      <span>
                        {rubric.criteria.every((c: any) => reviewedIds.includes(c.id))
                          ? "Bỏ chọn tất cả tiêu chí"
                          : `Rà soát tất cả tiêu chí (${reviewedIds.length}/${rubric.criteria.length})`}
                      </span>
                    </button>
                  )}
                </div>

                <div className="table-wrapper" style={{ border: "none" }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th style={{ width: "22%" }}>Tiêu Chí</th>
                        <th style={{ width: "12%" }}>Trạng Thái</th>
                        <th style={{ width: "10%" }}>Điểm (0..4)</th>
                        <th style={{ width: "32%" }}>Giải Trình Đánh Giá Của AI</th>
                        <th>Bằng chứng và thao tác rà soát</th>
                      </tr>
                    </thead>
                    <tbody>
                      {assessmentRun.criteria.map((c) => (
                        <tr key={c.criterion_id}>
                          <td>
                            <strong style={{ fontSize: "0.88rem", color: "var(--text-primary)" }}>{rubric?.criteria?.find((criterion: any) => criterion.id === c.criterion_id)?.label || c.criterion_id}</strong>
                          </td>
                          <td>
                            <span className={`badge ${c.status === "assessed" ? "badge-open" : "badge-draft"}`}>
                              {c.status === "assessed" ? "Có bằng chứng" : c.status === "insufficient_evidence" ? "Cần làm rõ" : "Bằng chứng mâu thuẫn"}
                            </span>
                          </td>
                          <td>
                            <span style={{
                              fontSize: "1.25rem",
                              fontWeight: 800,
                              fontFamily: "var(--font-mono)",
                              color: c.score !== null && c.score >= 2 ? "var(--emerald-text)" : "var(--amber-text)"
                            }}>
                              {c.score !== null ? `${c.score}/4` : "-"}
                            </span>
                          </td>
                          <td style={{ fontSize: "0.825rem", lineHeight: 1.55 }}>
                            <div style={{ color: "var(--text-primary)" }}>{c.rationale}</div>
                            {c.missing_information && c.missing_information.length > 0 && (
                              <div style={{
                                marginTop: "0.5rem",
                                padding: "0.5rem 0.75rem",
                                background: "var(--amber-bg)",
                                border: "1px solid var(--amber-border)",
                                borderRadius: "var(--radius-xs)",
                                color: "var(--amber-text)",
                                fontSize: "0.775rem"
                              }}>
                                <strong>Lỗ hổng bằng chứng:</strong> {c.missing_information.join("; ")}
                              </div>
                            )}
                          </td>
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                              {c.evidence.map((ev) => (
                                <button type="button"
                                  key={ev.span_id}
                                  onClick={() => setSelectedEvidence(ev)}
                                  className="evidence-quote-box card-interactive"
                                  title="Mở đoạn trích để đối chiếu với CV"
                                  style={{ margin: 0, padding: "0.6rem 0.85rem" }}
                                >
                                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.3rem" }}>
                                    <span className="codepoint-pill">
                                      <IconQuote size={10} />
                                      {ev.span_id} [{ev.resolved_start_cp}..{ev.resolved_end_cp}]
                                    </span>
                                    <span style={{ fontSize: "0.72rem", color: "var(--accent-cyan)", textDecoration: "underline" }}>
                                      Xem đoạn trích →
                                    </span>
                                  </div>
                                  <div style={{ color: "var(--text-secondary)", fontStyle: "italic", fontSize: "0.8rem" }}>
                                    &ldquo;{ev.quote.slice(0, 95)}{ev.quote.length > 95 ? "…" : ""}&rdquo;
                                  </div>
                                </button>
                              ))}
                              {canManage && <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditingCriterion(c.criterion_id)}>Điều chỉnh đánh giá</button>}
                              <label className="rubric-ack"><input type="checkbox" checked={reviewedIds.includes(c.criterion_id)} onChange={event => setReviewedIds(previous => event.target.checked ? [...previous.filter(x => x !== c.criterion_id), c.criterion_id] : previous.filter(x => x !== c.criterion_id))} />Tôi đã đối chiếu tiêu chí này</label>
                              {c.evidence.length === 0 && (
                                <span style={{ color: "var(--text-muted)", fontSize: "0.775rem" }}>
                                  Chưa có trích dẫn được xác thực cho tiêu chí này
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
          {assessmentRun && canManage && rubric && <HRRevisionEditor application={application} rubric={rubric} run={assessmentRun} revisions={hrRevisions} selectedCriterion={editingCriterion} onSaved={() => loadData(true)} />}
          {assessmentRun && canManage && <CandidateCopilot applicationId={id} snapshotKey={`${application.generation}:${assessmentRun.id}:${requisition.current_rubric_version_id}`} onEvidence={setSelectedEvidence} />}
        </div>
      )}

      {/* Tab 2: Sanitization & Redaction Viewer */}
      {activeTab === "sanitization" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
          <div className="card">
            <div className="card-header" style={{ flexWrap: "wrap", gap: "0.85rem" }}>
              <div>
                <h2 className="card-title">Hồ Sơ Đã Che Giấu Thông Tin Định Danh (Redacted CV)</h2>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.825rem", marginTop: "0.2rem" }}>
                  Hệ thống tự động che thông tin định danh; Owner phải kiểm tra toàn văn và xử lý mọi dữ liệu còn sót trước khi phê duyệt.
                </p>
              </div>

              {sanitizedVersion && (
                <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
                  <span className={`badge ${sanitizedVersion.status === "approved" ? "badge-open" : "badge-paused"}`}>
                    {sanitizedVersion.status === "approved" ? "✓ ĐÃ DUYỆT BẢN ĐÃ CHE" : "CHỜ DUYỆT BẢN ĐÃ CHE"}
                  </span>
                  {sanitizedVersion.status === "draft" && (
                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                      <label style={{ fontSize: "0.825rem", display: "flex", alignItems: "center", gap: "0.4rem", cursor: "pointer", color: "var(--text-secondary)" }}>
                        <input
                          type="checkbox"
                          checked={acknowledgedSanitization}
                          onChange={(e) => setAcknowledgedSanitization(e.target.checked)}
                        />
                        <span>Đã kiểm tra khử định danh</span>
                      </label>
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={handleApproveSanitization}
                        disabled={!canManage || !!loadWarnings.length || approvingSanitized || !acknowledgedSanitization || (sanitizedVersion.quality_flags?.document_type_hint !== "cv" && !confirmedDocumentIsCv)}
                      >
                        <IconCheckCircle size={14} />
                        <span>Duyệt bản đã che</span>
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>

            {sanitizedVersion ? (
              <div>
                {application.current_document_id && (
                  <section aria-label="Đối chiếu CV gốc" style={{ margin: "0 1.5rem 1.25rem", padding: "1rem", border: "1px solid var(--amber-border)", borderRadius: "var(--radius-md)", background: "var(--amber-bg)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
                      <div>
                        <strong style={{ color: "var(--text-primary)" }}>Đối chiếu với CV gốc</strong>
                        <p style={{ color: "var(--text-secondary)", fontSize: "0.825rem", marginTop: "0.25rem" }}>
                          CV gốc có thể chứa thông tin định danh. Chỉ người phụ trách mới được mở; quyền xem có thời hạn 30 phút và lần truy cập được ghi nhật ký. AI chỉ dùng bản đã che.
                        </p>
                      </div>
                      <button type="button" className="btn btn-secondary btn-sm" onClick={handleGrantRawAccess} disabled={!canManage || grantingRawAccess}>
                        <IconLock size={14} />
                        <span>{grantingRawAccess ? "Đang mở…" : rawPreviewBlob ? "Mở lại CV gốc · gia hạn 30 phút" : "Xem CV gốc · cấp quyền 30 phút"}</span>
                      </button>
                    </div>
                    {!canManage && <p style={{ color: "var(--text-secondary)", fontSize: "0.8rem", marginTop: "0.65rem" }}>Yêu cầu người phụ trách đợt tuyển dụng cấp quyền xem CV gốc.</p>}
                    {rawPreviewExpiresAt && <p role="status" style={{ color: "var(--text-secondary)", fontSize: "0.8rem", marginTop: "0.65rem" }}>Quyền xem còn hiệu lực đến {new Date(rawPreviewExpiresAt).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}.</p>}
                    {rawAccessError && <p role="alert" style={{ color: "var(--rose-text)", marginTop: "0.65rem" }}>{rawAccessError}</p>}
                    {rawPreviewLoading && <p role="status">Đang tải bản xem PDF an toàn…</p>}
                    {rawPreviewBlob && (
                      <div style={{ marginTop: "0.85rem", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-sm)", overflow: "hidden", background: "white" }}>
                        <RawPdfViewer file={rawPreviewBlob} />
                        <div style={{ padding: "0.65rem 0.85rem", display: "flex", justifyContent: "space-between", alignItems: "center", gap: "1rem" }}>
                          <span style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>Bản gốc chỉ để đối chiếu. Đóng khi hoàn tất rà soát.</span>
                          <button type="button" className="btn btn-secondary btn-sm" onClick={() => closeRawPreview()}>Đóng bản xem</button>
                        </div>
                      </div>
                    )}
                  </section>
                )}
                {sanitizedVersion.status === "draft" && (
                  <div style={{ marginBottom: "1rem" }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => {
                        setEditedSanitizedText(sanitizedVersion.canonical_text);
                        setEditingSanitization(!editingSanitization);
                        setAcknowledgedSanitization(false);
                        setConfirmedDocumentIsCv(false);
                      }}
                    >
                      {editingSanitization ? "Hủy chỉnh sửa" : "Sửa thông tin còn sót trong bản đã che"}
                    </button>
                  </div>
                )}
                {sanitizedVersion.quality_flags?.document_type_hint !== "cv" && (
                    <section role="alert" style={{ marginBottom: "1rem", padding: "1rem", border: "1px solid var(--amber-border)", borderRadius: "var(--radius-md)", background: "var(--amber-bg)" }}>
                      <strong>{sanitizedVersion.quality_flags?.document_type_hint === "job_description" ? "Tệp này có dấu hiệu là mô tả công việc, không phải CV." : "Hệ thống chưa xác định chắc chắn đây là CV ứng viên."}</strong>
                      <p style={{ marginTop: "0.35rem", color: "var(--text-secondary)" }}>Đối chiếu tài liệu gốc trước khi cho phép AI xử lý.</p>
                      {sanitizedVersion.status === "draft" && (
                        <label style={{ marginTop: "0.6rem", display: "flex", gap: "0.5rem", alignItems: "flex-start", cursor: "pointer" }}>
                          <input type="checkbox" checked={confirmedDocumentIsCv} onChange={(event) => setConfirmedDocumentIsCv(event.target.checked)} />
                          <span>Tôi đã kiểm tra tài liệu gốc và xác nhận đây là CV của ứng viên.</span>
                        </label>
                      )}
                    </section>
                  )}
                {editingSanitization ? (
                  <div className="form-group">
                    <label htmlFor="sanitizedTextEdit" className="form-label">Toàn văn bản đã che</label>
                    <textarea
                      id="sanitizedTextEdit"
                      className="form-textarea"
                      rows={18}
                      value={editedSanitizedText}
                      onChange={(event) => setEditedSanitizedText(event.target.value)}
                    />
                    <label htmlFor="sanitizationEditReason" className="form-label" style={{ marginTop: "0.75rem" }}>Lý do chỉnh sửa</label>
                    <input
                      id="sanitizationEditReason"
                      className="form-input"
                      value={sanitizationEditReason}
                      onChange={(event) => setSanitizationEditReason(event.target.value)}
                      placeholder="Ví dụ: Che địa chỉ còn sót"
                    />
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      disabled={savingSanitization || editedSanitizedText.trim().length < 10 || sanitizationEditReason.trim().length < 5}
                      onClick={handleSaveSanitization}
                      style={{ marginTop: "0.75rem" }}
                    >
                      {savingSanitization ? "Đang lưu…" : "Lưu bản nháp đã sửa"}
                    </button>
                  </div>
                ) : (
                  <div style={{
                background: "var(--bg-surface-elevated)",
                border: "1px solid var(--border-subtle)",
                padding: "1.5rem",
                borderRadius: "var(--radius-md)",
                fontSize: "0.875rem",
                lineHeight: 1.75,
                maxHeight: "550px",
                overflowY: "auto",
                whiteSpace: "pre-wrap",
                fontFamily: "var(--font-mono)",
                color: "var(--text-primary)"
              }}>
                {sanitizedVersion.canonical_text}
                  </div>
                )}
              </div>
            ) : application.current_sanitized_version_id ? (
              <div>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginBottom: "1rem" }}>
                  Bản nháp đã sẵn sàng. Người phụ trách cần mở quyền xem có thời hạn để kiểm tra thông tin đã che. Lần mở này được ghi vào nhật ký.
                </p>
                <button type="button" className="btn btn-secondary btn-sm" onClick={handleGrantRawAccess} disabled={grantingRawAccess || !canManage}>
                  <IconLock size={14} />
                  <span>{grantingRawAccess ? "Đang cấp quyền…" : "Bắt đầu rà soát · quyền xem 30 phút"}</span>
                </button>
                {rawAccessError && <p role="alert" style={{ color: "var(--rose-text)", marginTop: "0.75rem" }}>{rawAccessError}</p>}
              </div>
            ) : (
              <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
                {progress?.stage === "error" ? "Đọc tệp gặp lỗi. Kiểm tra định dạng CV và tải bản phù hợp từ đợt tuyển dụng." : progress?.stage === "awaiting_upload" ? "Hồ sơ chưa có tệp CV. Quay về đợt tuyển dụng để tải lên." : "Hệ thống đang đọc tệp; trạng thái sẽ tự cập nhật khi trang đang mở."}
              </p>
            )}
          </div>


        </div>
      )}

      {/* Tab 3: HR Revision & Attested Hiring Decision */}
      {activeTab === "revision" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
          {!decisions.length && <p className="notice">Đã xác nhận đối chiếu {reviewedIds.length}/{rubric?.criteria?.length || 0} tiêu chí. <button className="btn btn-secondary btn-sm" onClick={() => setActiveTab("assessment")}>Kiểm tra bằng chứng và điều chỉnh</button>{effectiveRevision && <span> Căn cứ quyết định: bản HR #{effectiveRevision.revision_no} đã hoàn tất.</span>}</p>}
          <div className="card">
            <div className="card-header">
              <div>
                <h2 className="card-title">Quyết định tuyển dụng của HR</h2>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.825rem", marginTop: "0.2rem" }}>
                  AI chỉ đóng vai trò phân tích bằng chứng; Người phụ trách đợt tuyển dụng trực tiếp đưa ra quyết định cuối cùng
                </p>
              </div>
            </div>

            {decisions.length > 0 ? (
              <div style={{ padding: "1.5rem", background: "var(--bg-surface-elevated)", border: "1px solid var(--border-medium)", borderRadius: "var(--radius-md)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                  <span className={`badge ${decisions[0].outcome === "advance" ? "badge-rec-advance" : "badge-rec-review"}`} style={{ fontSize: "1rem", padding: "0.4rem 0.9rem" }}>
                    KẾT LUẬN: {decisions[0].outcome === "advance" ? "Mời vào vòng tiếp theo" : decisions[0].outcome === "request_information" ? "Yêu cầu bổ sung thông tin" : "Chưa chuyển vòng"}
                  </span>
                  <span style={{ fontSize: "0.825rem", color: "var(--text-muted)" }}>
                    Ban hành: {new Date(decisions[0].created_at).toLocaleString("vi-VN")}
                  </span>
                </div>
                <p style={{ fontSize: "0.925rem", lineHeight: 1.65, color: "var(--text-primary)" }}>
                  <strong>Căn cứ quyết định của hội đồng:</strong> {decisions[0].reason}
                </p>
              </div>
            ) : (
              <form onSubmit={handleSubmitDecision}>
                <div className="form-group">
                  <label className="form-label">Kết luận tuyển dụng</label>
                  <select
                    className="form-select"
                    value={decisionOutcome}
                    onChange={(e: any) => setDecisionOutcome(e.target.value)}
                  >
                    <option value="advance">Chuyển tiếp vòng phỏng vấn kỹ thuật (ADVANCE)</option>
                    <option value="request_information">Yêu cầu bổ sung thêm thông tin năng lực (REQUEST INFORMATION)</option>
                    <option value="not_advance">Từ chối / Chưa phù hợp ở vị trí này (NOT ADVANCE)</option>
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Giải trình quyết định của người duyệt (Bắt buộc tối thiểu 20 ký tự)</label>
                  <textarea
                    className="form-textarea"
                    rows={4}
                    placeholder="Nêu rõ căn cứ từ năng lực kỹ thuật, thiết kế hệ thống, các bằng chứng đã đối chiếu trong CV..."
                    value={decisionReason}
                    onChange={(e) => setDecisionReason(e.target.value)}
                    required
                  />
                </div>

                {/* Signed ReviewAttestation Checklist */}
                <div style={{ background: "var(--bg-surface-elevated)", padding: "1.25rem", borderRadius: "var(--radius-md)", border: "1px solid var(--border-medium)", marginBottom: "1.75rem", display: "flex", flexDirection: "column", gap: "0.85rem" }}>
                  <div style={{ fontWeight: 700, fontSize: "0.875rem", color: "var(--accent-cyan)", display: "flex", alignItems: "center", gap: "0.45rem" }}>
                    <IconShield size={16} color="var(--accent-cyan)" />
                    <span>Xác nhận của người duyệt trước khi ra quyết định:</span>
                  </div>

                  {rubric?.criteria && reviewedIds.length !== rubric.criteria.length ? (
                    <div style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      flexWrap: "wrap",
                      gap: "0.5rem",
                      padding: "0.65rem 0.85rem",
                      background: "rgba(245, 158, 11, 0.12)",
                      border: "1px solid var(--amber-border)",
                      borderRadius: "var(--radius-sm)",
                      fontSize: "0.8rem",
                      color: "var(--amber-text)"
                    }}>
                      <span>
                        Chưa hoàn tất đối chiếu tiêu chí (Đã đối chiếu <strong>{reviewedIds.length}/{rubric.criteria.length}</strong> tiêu chí).
                      </span>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => {
                          setReviewedIds(rubric.criteria.map((c: any) => c.id));
                        }}
                        style={{ padding: "0.25rem 0.65rem", fontSize: "0.75rem" }}
                      >
                        ✓ Xác nhận đối chiếu tất cả
                      </button>
                    </div>
                  ) : (
                    <div style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.4rem",
                      padding: "0.45rem 0.75rem",
                      background: "rgba(16, 185, 129, 0.08)",
                      border: "1px solid rgba(16, 185, 129, 0.2)",
                      borderRadius: "var(--radius-sm)",
                      fontSize: "0.775rem",
                      color: "var(--emerald-text)"
                    }}>
                      <IconCheckCircle size={14} color="var(--emerald-text)" />
                      <span>Đã đối chiếu đủ tất cả {rubric?.criteria?.length || 0} tiêu chí năng lực.</span>
                    </div>
                  )}

                  <label style={{ fontSize: "0.825rem", display: "flex", alignItems: "flex-start", gap: "0.6rem", cursor: "pointer", color: "var(--text-primary)" }}>
                    <input
                      type="checkbox"
                      checked={attestCheck1}
                      onChange={(e) => setAttestCheck1(e.target.checked)}
                      style={{ marginTop: "0.2rem" }}
                    />
                    <span>1. Tôi đã đối chiếu trực tiếp các trích dẫn bằng chứng với văn bản ứng viên và xác nhận tính xác thực.</span>
                  </label>

                  <label style={{ fontSize: "0.825rem", display: "flex", alignItems: "flex-start", gap: "0.6rem", cursor: "pointer", color: "var(--text-primary)" }}>
                    <input
                      type="checkbox"
                      checked={attestCheck2}
                      onChange={(e) => setAttestCheck2(e.target.checked)}
                      style={{ marginTop: "0.2rem" }}
                    />
                    <span>2. Tôi chịu trách nhiệm hoàn toàn về quyết định tuyển dụng độc lập của con người, không ủy quyền cho AI.</span>
                  </label>

                  <label style={{ fontSize: "0.825rem", display: "flex", alignItems: "flex-start", gap: "0.6rem", cursor: "pointer", color: "var(--text-primary)" }}>
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
                  className="btn btn-primary btn-lg"
                  disabled={!canManage || !!loadWarnings.length || reviewedIds.length !== rubric?.criteria?.length || submittingDecision || !attestCheck1 || !attestCheck2 || !attestCheck3}
                >
                  <IconCheckCircle size={18} />
                  <span>{submittingDecision ? "Đang ký duyệt…" : "Xác nhận và ghi quyết định"}</span>
                </button>
              </form>
            )}
          </div>
        </div>
      )}

      {/* Tab 4: Interview Guide */}
      {activeTab === "interview" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
          <div className="card">
            <h2>Câu hỏi phỏng vấn</h2>
            <p>{questionBanks.some(bank => bank.status === "approved")
              ? "Có thể kết hợp câu hỏi chuẩn đã duyệt với câu hỏi làm rõ theo bằng chứng của hồ sơ."
              : "Có thể tạo câu hỏi làm rõ theo hồ sơ ngay. Ngân hàng câu hỏi chuẩn là tùy chọn, dùng để hỏi cùng một số câu hỏi cho mọi ứng viên."}</p>
            <Link href={`/requisitions/${application.requisition_id}?setup=1`}>Thiết lập JD, rubric và câu hỏi chuẩn →</Link>
          </div>
          <div className="card">
            <div className="card-header" style={{ flexWrap: "wrap", gap: "0.85rem" }}>
              <div>
                <h2 className="card-title">Hướng dẫn phỏng vấn theo hồ sơ</h2>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.825rem", marginTop: "0.2rem" }}>
                  AI gợi ý tối đa 3 câu hỏi làm rõ dựa trên bằng chứng hiện có; câu hỏi chuẩn đã duyệt sẽ được thêm nếu có.
                </p>
              </div>

              <button
                className="btn btn-primary btn-sm"
                onClick={handleTriggerInterview}
                disabled={!canManage || !!loadWarnings.length || triggeringInterview || !assessmentRun}
              >
                <IconSparkles size={14} />
                <span>{triggeringInterview ? "Đang tạo câu hỏi…" : "Tạo câu hỏi gợi ý"}</span>
              </button>
            </div>

            {interviewDraft ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                {(["queued", "running"].includes(interviewDraft.status)) && (
                  <p role="status" className="muted">Đang xử lý câu hỏi phỏng vấn…</p>
                )}
                {interviewDraft.status === "failed" && (
                  <p role="alert" className="notice notice-error">Không tạo được câu hỏi AI. Vui lòng kiểm tra job và thử lại.</p>
                )}
                {(interviewDraft.core_questions || []).map((q: any) => (
                  <div key={q.question_id} className="surface" style={{ padding: "1rem" }}>
                    <strong>Câu hỏi chuẩn · {q.criterion_id}</strong>
                    <p>{q.question_vi}</p>
                    <small className="muted">Mục đích: {q.purpose_vi}</small>
                  </div>
                ))}
                {(interviewDraft.ai_followups || []).map((q: any, idx: number) => (
                  <div key={idx} style={{ padding: "1.25rem", background: "var(--bg-surface-elevated)", borderRadius: "var(--radius-md)", border: "1px solid var(--border-medium)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                      <span className="badge badge-rec-clarify">Câu hỏi đào sâu {idx + 1} (Tiêu chí: {q.criterion_id})</span>
                    </div>
                    <p style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.5rem" }}>
                      {q.question_vi}
                    </p>
                    <div style={{ fontSize: "0.825rem", color: "var(--text-secondary)" }}>
                      <strong>Mục đích:</strong> {q.purpose_vi}<br />
                      <strong>Dấu hiệu cần tìm:</strong> {(q.answer_indicators || []).join("; ")}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ textAlign: "center", padding: "3rem 1.5rem" }}>
                <div style={{ width: "48px", height: "48px", borderRadius: "50%", background: "rgba(56, 189, 248, 0.1)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 1rem auto" }}>
                  <IconMessageSquare size={24} color="#38bdf8" />
                </div>
                <h3 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: "0.35rem" }}>Chưa tạo bộ câu hỏi phỏng vấn riêng</h3>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginBottom: "1.25rem" }}>
                  Tạo gợi ý phỏng vấn để làm rõ phần đóng góp cá nhân và những thông tin CV chưa cung cấp đủ.
                </p>

              </div>
            )}
          </div>
          <section className="card" aria-labelledby="interview-scorecard-title">
            <div className="card-header" style={{ alignItems: "flex-start", gap: "1rem", flexWrap: "wrap" }}>
              <div>
                <h2 className="card-title" id="interview-scorecard-title">Phiếu đánh giá sau phỏng vấn</h2>
                <p className="muted" style={{ maxWidth: 720, marginTop: "0.4rem" }}>
                  Điểm này do phỏng vấn viên ghi từ câu trả lời trong buổi phỏng vấn. Phiếu tách biệt với điểm AI trên CV và không tự động quyết định tuyển dụng.
                </p>
              </div>
              <label style={{ display: "grid", gap: "0.3rem", minWidth: 160 }}>
                <span className="form-label">Lượt phỏng vấn</span>
                <select
                  aria-label="Lượt phỏng vấn"
                  value={scorecardRoundNo}
                  disabled={scorecardDirty || savingScorecard}
                  onChange={(event) => setScorecardRoundNo(Number(event.target.value))}
                >
                  {[1, 2, 3, 4, 5].map((round) => <option key={round} value={round}>Lượt {round}</option>)}
                </select>
              </label>
            </div>

            {!rubric?.criteria?.length ? (
              <p role="status" className="notice">Chưa có rubric hiện hành để tạo phiếu đánh giá.</p>
            ) : !canInterview ? (
              <p role="status" className="notice">Tài khoản của bạn chỉ có quyền xem hồ sơ, không được ghi phiếu phỏng vấn.</p>
            ) : (
              <>
                {currentScorecard?.is_stale && <p role="alert" className="notice notice-error">Rubric hoặc CV đã đổi sau khi tạo phiếu. Phiếu này được giữ để kiểm toán nhưng không thể sửa hoặc nộp; hãy chọn lượt mới.</p>}
                {currentScorecard?.status === "finalized" && !currentScorecard?.is_stale && <p role="status" className="notice">Phiếu lượt {scorecardRoundNo} đã nộp và khóa lúc {currentScorecard.finalized_at ? new Date(currentScorecard.finalized_at).toLocaleString("vi-VN") : ""}.</p>}

                <div style={{ display: "grid", gap: "1rem", marginTop: "1rem" }}>
                  {rubric.criteria.map((criterion: any) => {
                    const row = scorecardCriteria.find((entry) => entry.criterion_id === criterion.id);
                    const readOnly = currentScorecard?.status === "finalized" || !!currentScorecard?.is_stale;
                    return (
                      <article key={criterion.id} className="surface" style={{ padding: "1rem", display: "grid", gap: "0.75rem" }}>
                        <div>
                          <strong>{criterion.label || criterion.id}</strong>
                          {criterion.description && <p className="muted" style={{ margin: "0.25rem 0 0" }}>{criterion.description}</p>}
                          {criterion.scoring_anchors?.length > 0 && <details style={{ marginTop: "0.45rem" }}>
                            <summary className="muted" style={{ cursor: "pointer", fontSize: "0.8rem" }}>Xem mô tả mức điểm rubric</summary>
                            <ul className="muted" style={{ margin: "0.4rem 0 0", paddingLeft: "1.25rem", fontSize: "0.8rem" }}>
                              {criterion.scoring_anchors.map((anchor: any) => <li key={anchor.score}><strong>{anchor.score}/4:</strong> {anchor.description}</li>)}
                            </ul>
                          </details>}
                        </div>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "0.75rem" }}>
                          <label style={{ display: "grid", gap: "0.3rem" }}>
                            <span className="form-label">Kết quả quan sát</span>
                            <select
                              aria-label={`${criterion.label || criterion.id}: kết quả quan sát`}
                              value={row?.outcome || "not_observed"}
                              disabled={readOnly}
                              onChange={(event) => updateScorecardCriterion(criterion.id, {
                                outcome: event.target.value,
                                score: null,
                              })}
                            >
                              <option value="assessed">Đã đánh giá</option>
                              <option value="not_observed">Chưa quan sát / chưa đủ bằng chứng</option>
                              <option value="conflicting_evidence">Câu trả lời cần đối chiếu</option>
                            </select>
                          </label>
                          {row?.outcome === "assessed" && <label style={{ display: "grid", gap: "0.3rem" }}>
                            <span className="form-label">Điểm phỏng vấn (0–4)</span>
                            <select
                              aria-label={`${criterion.label || criterion.id}: điểm phỏng vấn`}
                              value={row.score ?? ""}
                              disabled={readOnly}
                              onChange={(event) => updateScorecardCriterion(criterion.id, { score: event.target.value === "" ? null : Number(event.target.value) })}
                            >
                              <option value="" disabled>Chọn điểm</option>
                              {[0, 1, 2, 3, 4].map((score) => <option key={score} value={score}>{score}/4</option>)}
                            </select>
                          </label>}
                        </div>
                        {row?.outcome !== "not_observed" && <label style={{ display: "grid", gap: "0.3rem" }}>
                          <span className="form-label">Tóm tắt câu trả lời / căn cứ quan sát {row?.outcome === "assessed" ? "(bắt buộc, ít nhất 20 ký tự)" : "(nếu có mâu thuẫn, ghi nội dung cần đối chiếu)"}</span>
                          <textarea
                            rows={3}
                            maxLength={2000}
                            value={row?.answer_summary || ""}
                            disabled={readOnly}
                            onChange={(event) => updateScorecardCriterion(criterion.id, { answer_summary: event.target.value })}
                          />
                        </label>}
                        <label style={{ display: "grid", gap: "0.3rem" }}>
                          <span className="form-label">Ghi chú nội bộ theo năng lực</span>
                          <textarea
                            rows={2}
                            maxLength={2000}
                            value={row?.interviewer_note || ""}
                            disabled={readOnly}
                            onChange={(event) => updateScorecardCriterion(criterion.id, { interviewer_note: event.target.value })}
                          />
                        </label>
                      </article>
                    );
                  })}
                </div>

                <div className="notice" style={{ marginTop: "1rem" }}>
                  Chưa có bằng chứng nghĩa là để trống điểm, không ghi 0. Ghi nhận theo năng lực và nội dung câu trả lời; không đưa thông tin cá nhân nhạy cảm vào phiếu.
                </div>
                <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", marginTop: "1rem" }}>
                  <button className="btn btn-secondary" onClick={handleSaveInterviewScorecard}
                    disabled={savingScorecard || !scorecardDirty || currentScorecard?.status === "finalized" || !!currentScorecard?.is_stale}>
                    {savingScorecard ? "Đang lưu…" : "Lưu nháp phiếu"}
                  </button>
                  <button className="btn btn-primary" onClick={handleFinalizeInterviewScorecard}
                    disabled={savingScorecard || !currentScorecard || currentScorecard.status !== "draft" || scorecardDirty || !!currentScorecard.is_stale}>
                    Nộp và khóa phiếu
                  </button>
                  {scorecardDirty && <span role="status" className="muted" style={{ alignSelf: "center" }}>Có thay đổi chưa lưu.</span>}
                </div>
              </>
            )}

            {interviewScorecards.filter((card) => card.status === "finalized" && card.id !== currentScorecard?.id).length > 0 && (
              <div style={{ marginTop: "1.5rem" }}>
                <h3>Phiếu đã nộp của hội đồng</h3>
                <p className="muted">Các phiếu được xem độc lập với đánh giá AI. Phiếu nháp của người khác không hiển thị trước khi họ nộp.</p>
                <div style={{ display: "grid", gap: "0.75rem", marginTop: "0.75rem" }}>
                  {interviewScorecards.filter((card) => card.status === "finalized" && card.id !== currentScorecard?.id).map((card) => (
                    <details key={card.id} className="surface" style={{ padding: "0.85rem 1rem" }}>
                      <summary style={{ cursor: "pointer", fontWeight: 650 }}>
                        {card.interviewer_name || "Phỏng vấn viên"} · Lượt {card.round_no}{card.is_stale ? " · Phiếu cũ" : ""}
                      </summary>
                      <div style={{ display: "grid", gap: "0.6rem", marginTop: "0.85rem" }}>
                        {card.criteria.map((entry: any) => {
                          const criterion = rubric.criteria.find((item: any) => item.id === entry.criterion_id);
                          return <div key={entry.criterion_id}>
                            <strong>{criterion?.label || entry.criterion_id}</strong>
                            <span className="muted"> · {entry.outcome === "assessed" ? `Điểm ${entry.score}/4` : entry.outcome === "not_observed" ? "Chưa quan sát" : "Cần đối chiếu"}</span>
                            {entry.answer_summary && <p className="muted" style={{ margin: "0.2rem 0" }}>{entry.answer_summary}</p>}
                            {entry.interviewer_note && <p style={{ margin: "0.2rem 0" }}>Ghi chú: {entry.interviewer_note}</p>}
                          </div>;
                        })}
                      </div>
                    </details>
                  ))}
                </div>
              </div>
            )}
          </section>
        </div>
      )}

      {/* Slide-in Quote Drawer Component */}
      {selectedEvidence && (
        <div className="modal-overlay" onClick={() => setSelectedEvidence(null)}>
          <div className="quote-drawer" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-header">
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <IconQuote size={18} color="var(--accent-cyan)" />
                <h3 style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)" }}>
                  Chi Tiết Trích Dẫn Bằng Chứng
                </h3>
              </div>
              <button
                onClick={() => setSelectedEvidence(null)}
                style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer" }}
              >
                <IconX size={20} />
              </button>
            </div>

            <div className="drawer-body">
              <div style={{ marginBottom: "1.25rem" }}>
                <span className="codepoint-pill" style={{ fontSize: "0.8rem", padding: "0.25rem 0.6rem" }}>
                  ID: {selectedEvidence.span_id}
                </span>
                <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "0.4rem", fontFamily: "var(--font-mono)" }}>
                  Tọa độ ký tự trong CV: [{selectedEvidence.resolved_start_cp}..{selectedEvidence.resolved_end_cp}]
                </div>
              </div>

              <div style={{
                background: "var(--bg-surface-elevated)",
                border: "1px solid var(--border-medium)",
                borderLeft: "4px solid var(--accent-cyan)",
                padding: "1.25rem",
                borderRadius: "var(--radius-sm)",
                fontSize: "0.925rem",
                lineHeight: 1.7,
                color: "var(--text-primary)",
                fontStyle: "italic",
                marginBottom: "1.5rem"
              }}>
                &ldquo;{selectedEvidence.quote}&rdquo;
              </div>

              <div style={{
                background: "rgba(56, 189, 248, 0.06)",
                border: "1px solid rgba(56, 189, 248, 0.18)",
                padding: "1rem",
                borderRadius: "var(--radius-sm)",
                fontSize: "0.8rem",
                color: "var(--text-secondary)",
                lineHeight: 1.6
              }}>
                <div style={{ fontWeight: 600, color: "var(--accent-cyan)", marginBottom: "0.25rem", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                  <IconCheckCircle size={14} />
                  <span>Đối chiếu nguồn trích dẫn</span>
                </div>
                Tọa độ ký tự giúp HR tìm lại đoạn tương ứng trong bản CV đã xử lý. Hãy đọc ngữ cảnh xung quanh trước khi quyết định.
              </div>
            </div>

            <div style={{ padding: "1.25rem 1.5rem", borderTop: "1px solid var(--border-subtle)", display: "flex", justifyContent: "flex-end" }}>
              <button className="btn btn-secondary" onClick={() => setSelectedEvidence(null)}>
                Đóng Drawer
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Data deletion request modal */}
      {showDeleteModal && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-header">
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <div style={{ width: "32px", height: "32px", borderRadius: "var(--radius-sm)", background: "var(--rose-bg)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <IconTrash size={18} color="var(--rose-text)" />
                </div>
                <div>
                  <h2 className="modal-title" style={{ color: "var(--rose-text)" }}>Yêu cầu xóa dữ liệu</h2>
                  <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>Kiểm tra phạm vi trước khi gửi yêu cầu.</p>
                </div>
              </div>
              <button
                onClick={() => setShowDeleteModal(false)}
                style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer" }}
              >
                <IconX size={20} />
              </button>
            </div>

            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginBottom: "1.5rem", lineHeight: 1.6 }}>
              Hệ thống sẽ đánh dấu hồ sơ và đưa tác vụ xóa vào hàng đợi. Chỉ xác nhận hoàn tất khi trạng thái yêu cầu được cập nhật.
            </p>

            <div className="form-group">
              <label className="form-label">Phạm vi xóa dữ liệu</label>
              <select
                className="form-select"
                value={deleteScope}
                onChange={(e: any) => setDeleteScope(e.target.value)}
              >
                <option value="application">Chỉ xóa Hồ sơ ứng tuyển này (Application)</option>
                <option value="candidate">Xóa toàn bộ Ứng viên &amp; Các hồ sơ liên quan (Candidate)</option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Lý do yêu cầu xóa</label>
              <select
                className="form-select"
                value={deleteReason}
                onChange={(e) => setDeleteReason(e.target.value)}
              >
                <option value="candidate_request">Yêu cầu từ ứng viên</option>
                <option value="retention_expired">Hết hạn thời gian lưu trữ theo chính sách</option>
                <option value="legal_obligation">Yêu cầu pháp lý bắt buộc</option>
              </select>
            </div>

            <div className="modal-footer">
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
                className="btn btn-danger"
                onClick={handleDeleteConfirm}
                disabled={deleting}
              >
                {deleting ? "Đang xóa dữ liệu…" : "Xác Nhận Tiêu Hủy Vĩnh Viễn"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
