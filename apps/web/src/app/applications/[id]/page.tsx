"use client";

import React, { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, AssessmentRunData, UserAccount, ExecutiveSummaryData, EmailDraftData } from "@/lib/api";
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
  IconSliders,
  IconRefresh,
  IconMail,
  IconCopy
} from "@/components/Icons";
import { useToast } from "@/components/Toast";
import HRRevisionEditor from "@/components/HRRevisionEditor";
import RawPdfViewer from "@/components/RawPdfViewer";
import ScreeningDecision from "@/components/ScreeningDecision";
import InterviewWorkspace from "@/components/InterviewWorkspace";
import {screeningPayload, workflowTab, preserveEditBase, refreshInterviewCards} from "@/lib/hr-workflow";
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
  const [scorecardEditBase,setScorecardEditBase] = useState<any>({id:null,row_version:0});
  const [scorecardsReady,setScorecardsReady] = useState(false);
  const [savingScorecard, setSavingScorecard] = useState(false);
  const [interviewFocusIds, setInterviewFocusIds] = useState<string[]>([]);
  const [showAllInterviewCriteria, setShowAllInterviewCriteria] = useState(false);
  const [amendingScorecard, setAmendingScorecard] = useState(false);
  const [amendmentReason, setAmendmentReason] = useState("");

  // Executive Summary & Email Draft state
  const [executiveSummary, setExecutiveSummary] = useState<ExecutiveSummaryData | null>(null);
  const [generatingSummary, setGeneratingSummary] = useState(false);
  const [emailDraft, setEmailDraft] = useState<EmailDraftData | null>(null);
  const [generatingEmailDraft, setGeneratingEmailDraft] = useState(false);
  const [selectedEmailTemplate, setSelectedEmailTemplate] = useState<string>("technical_clarification");
  const [emailContentReviewed, setEmailContentReviewed] = useState(false);
  const [editingEmailDraft, setEditingEmailDraft] = useState(false);
  const emailEditingRef = useRef(false);
  emailEditingRef.current = editingEmailDraft;
  const [editedEmailSubject, setEditedEmailSubject] = useState("");
  const [editedEmailBody, setEditedEmailBody] = useState("");
  const [savingEmailDraft, setSavingEmailDraft] = useState(false);
  const [copiedEmail, setCopiedEmail] = useState(false);

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

  const [submittingDecision, setSubmittingDecision] = useState(false);

  // Interview state
  const [triggeringInterview, setTriggeringInterview] = useState(false);

  const [progress, setProgress] = useState<any>(null);
  const [loadWarnings, setLoadWarnings] = useState<string[]>([]);
  const [editingCriterion, setEditingCriterion] = useState<string | null>(null);
  const [reviewedIds, setReviewedIds] = useState<string[]>([]);
  const [reviewState,setReviewState] = useState<any>(null);
  const [reviewSaveError,setReviewSaveError] = useState("");
  const reviewDirtyRef = useRef(false);
  const reviewSourceRef = useRef("");
  const reviewSavingRef = useRef(false);
  function changeReviewedIds(value:React.SetStateAction<string[]>) { reviewDirtyRef.current=true;setReviewedIds(value); }
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
        api.getCandidateSummary(id).catch(() => null),
        api.getEmailDraft(id).catch(() => null),
        req.my_role === "owner" ? api.getReviewProgress(id) : Promise.resolve(null),
      ];
      const results = await Promise.allSettled(requests);
      const value = (index: number, fallback: any) => results[index].status === "fulfilled" ? (results[index] as PromiseFulfilledResult<any>).value : fallback;
      const names = ["tiêu chí", "câu hỏi chuẩn", "CV đã che", "đánh giá AI", "bản điều chỉnh HR", "quyết định", "gợi ý phỏng vấn", "trạng thái xử lý", "phiếu phỏng vấn", "tóm tắt hồ sơ", "bản nháp email", "tiến độ đối chiếu"];
      const warnings = results.flatMap((result, index) => result.status === "rejected" && !(index === 2 && String(result.reason.message).includes("403")) && [0,2,3,4,5,7,11].includes(index) ? [`Không tải được ${names[index]}: ${result.reason.message}`] : []);
      setLoadWarnings(warnings);
      setRubric(value(0, null)); setQuestionBanks(value(1, [])); setSanitizedVersion(value(2, null));
      const run = value(3, null);
      const latestProgress = value(7, null);
      const usableRun = run && !run.is_stale && (
        run.status === "failed" ||
        (run.status === "succeeded" && latestProgress?.assessment_status === "succeeded")
      ) ? run : null;
      setAssessmentRun(usableRun);
      setHrRevisions(value(4, [])); setDecisions(value(5, [])); setInterviewDraft(value(6, null)); setProgress(value(7, null));
      setInterviewScorecards(value(8, []));setScorecardsReady(results[8].status==="fulfilled");
      const savedReview = value(11,null);
      if (savedReview) {
        const changedSource = reviewSourceRef.current !== savedReview.source_hash;
        reviewSourceRef.current = savedReview.source_hash;
        setReviewState(savedReview);
        if (changedSource || !reviewDirtyRef.current) { setReviewedIds(savedReview.reviewed_criterion_ids); reviewDirtyRef.current=false; }
      }
      setExecutiveSummary(value(9, null));
      const loadedDraft = value(10, null);
      // Preserve both text AND its original revision while the editor is dirty.
      // Otherwise polling could silently rebase stale text onto a newer draft.
      if (!emailEditingRef.current) setEmailDraft(loadedDraft);
      if (loadedDraft && !emailEditingRef.current) {
        setSelectedEmailTemplate(loadedDraft.template_type);
        setEditedEmailSubject(loadedDraft.subject);
        setEditedEmailBody(loadedDraft.body);
      }
      if (!initialTab.current) {
        setActiveTab(value(2, null)?.status !== "approved" ? "sanitization" : workflowTab(value(7,null)?.stage || "awaiting_decision"));
        initialTab.current = true;
      }
    } catch (err: any) { setError(err.message || "Không tải được hồ sơ. Hãy thử lại."); }
    finally { setLoading(false); refreshing.current = false; }
  }

  useEffect(() => {
    if (!progress?.pending && !["reading", "analyzing"].includes(progress?.stage) && (interviewDraft?.is_stale || !["queued","running"].includes(interviewDraft?.status))) return;
    const timer = window.setInterval(() => { if (document.visibilityState === "visible") void loadData(true); }, 4000);
    return () => window.clearInterval(timer);
  }, [id, progress?.pending, progress?.stage, interviewDraft?.status]);

  useEffect(() => { setAttestCheck1(false); }, [application?.generation, assessmentRun?.id, effectiveRevision?.id]);
  useEffect(() => {
    if (!reviewState || !reviewDirtyRef.current || reviewSavingRef.current || JSON.stringify(reviewedIds)===JSON.stringify(reviewState.reviewed_criterion_ids)) return;
    const timer = window.setTimeout(async()=>{
      reviewSavingRef.current = true;
      const sourceHash = reviewState.source_hash;
      const submittedIds = [...reviewedIds];
      try {
        const saved = await api.saveReviewProgress(id,{source_hash:sourceHash,expected_version:reviewState.row_version,reviewed_criterion_ids:submittedIds});
        if(reviewSourceRef.current === sourceHash) { setReviewState(saved); setReviewSaveError(""); }
      } catch(e:any) { setReviewSaveError(e.message || "Chưa lưu được tiến độ đối chiếu."); }
      finally {reviewSavingRef.current=false;}
    },600);
    return ()=>window.clearTimeout(timer);
  },[id,reviewedIds,reviewState?.row_version,reviewState?.source_hash]);

  useEffect(() => {
    initialTab.current = false;
    setScorecardRoundNo(1);
    setScorecardDirty(false);
    void loadData();
  }, [id]);

  useEffect(() => {
    if (!rubric?.criteria?.length) return;
    const saved = interviewScorecards.find((card) =>
      card.interviewer_id === currentUser?.id && card.round_no === scorecardRoundNo
      && card.rubric_version_id === requisition?.current_rubric_version_id
    );
    setScorecardEditBase((previous:any)=>preserveEditBase(previous,{id:saved?.id || null,row_version:saved?.row_version || 0},scorecardDirty || amendingScorecard));
    if(scorecardDirty || amendingScorecard) return;
    setScorecardCriteria(saved?.criteria || rubric.criteria.map((criterion: any) => ({
      criterion_id: criterion.id,
      outcome: "not_observed",
      score: null,
      answer_summary: "",
      interviewer_note: "",
    })));
  }, [rubric?.id, interviewScorecards, currentUser?.id, requisition?.current_rubric_version_id, scorecardRoundNo, scorecardDirty, amendingScorecard]);

  useEffect(() => {
    if (!interviewDraft?.id || interviewDraft?.is_stale || !["queued", "running"].includes(interviewDraft.status)) return;
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
  }, [interviewDraft?.id, interviewDraft?.status, interviewDraft?.is_stale]);

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

  async function handleTriggerAssessment(focusCriterionIds?: string[]) {
    if (sanitizedVersion?.status !== "approved" || !requisition?.current_rubric_version_id) {
      warning("Cần HR duyệt bản đã che thông tin và có bộ tiêu chí được phê duyệt.");
      return;
    }
    setTriggeringAssessment(true);
    try {
      await api.triggerAssessment(
        id,
        sanitizedVersion.id,
        requisition.current_rubric_version_id,
        focusCriterionIds,
      );
      success(focusCriterionIds?.length
        ? "Đã đưa lượt đánh giá mới vào hàng đợi. Hệ thống vẫn trả kết quả đầy đủ theo rubric đã duyệt."
        : "Đã đưa yêu cầu đánh giá AI vào hàng đợi xử lý.");
      await loadData();
    } catch (err: any) {
      toastError(err.message || "Lỗi kích hoạt đánh giá");
    } finally {
      setTriggeringAssessment(false);
    }
  }

  async function handleSubmitDecision(e: React.FormEvent) {
    e.preventDefault();
    if (!attestCheck1 || reviewedIds.length !== rubric?.criteria?.length || loadWarnings.length > 0) {
      warning("Cần đối chiếu đủ tiêu chí và xác nhận đã rà soát trước khi ghi kết luận.");
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

      await api.recordScreeningDecision(id,screeningPayload(
        {kind:effectiveKind,id:effectiveId},reviewedIds,decisionOutcome,decisionReason,
        application.current_decision_id || null,rubric.id));
      success("Đã ghi kết luận sàng lọc của HR.");
      setAttestCheck1(false);setDecisionReason("");
      await loadData();
      try {
        const freshDraft = await api.generateEmailDraft(id);
        setEmailDraft(freshDraft);
        setSelectedEmailTemplate(freshDraft.template_type);
        setEditedEmailSubject(freshDraft.subject);
        setEditedEmailBody(freshDraft.body);
      } catch {
        // Non-blocking
      }
    } catch (err: any) {
      toastError(err.message || "Lỗi ban hành quyết định");
    } finally {
      setSubmittingDecision(false);
    }
  }

  async function handleGenerateSummary() {
    setGeneratingSummary(true);
    try {
      const summary = await api.generateCandidateSummary(id);
      setExecutiveSummary(summary);
      success("Đã phân tích và cập nhật tóm tắt hồ sơ ứng viên thành công!");
    } catch (err: any) {
      toastError(err.message || "Lỗi tạo tóm tắt hồ sơ");
    } finally {
      setGeneratingSummary(false);
    }
  }

  async function handleGenerateEmailDraft(template?: string) {
    const targetTemplate = template || selectedEmailTemplate;
    setGeneratingEmailDraft(true);
    try {
      const draft = await api.generateEmailDraft(id, targetTemplate);
      setEmailDraft(draft);
      setEmailContentReviewed(false);
      setSelectedEmailTemplate(draft.template_type);
      setEditedEmailSubject(draft.subject);
      setEditedEmailBody(draft.body);
      setEditingEmailDraft(false);
      success("Đã sinh bản nháp email phản hồi ứng viên!");
    } catch (err: any) {
      toastError(err.message || "Lỗi sinh bản nháp email");
    } finally {
      setGeneratingEmailDraft(false);
    }
  }

  async function handleSaveEmailDraft(approve = false) {
    if (!emailDraft) return;
    if (!editedEmailSubject.trim() || !editedEmailBody.trim()) {
      warning("Tiêu đề và nội dung email không được để trống.");
      return;
    }
    setSavingEmailDraft(true);
    try {
      const updated = await api.updateEmailDraft(id, editedEmailSubject, editedEmailBody, emailDraft.id, emailDraft.version_no, approve ? "approved" : "draft", approve && emailContentReviewed);
      setEmailDraft(updated);
      setEditingEmailDraft(false);
      setEmailContentReviewed(false);
      success(approve ? "Đã ghi nhận người duyệt và phiên bản thư." : "Đã lưu phiên bản nháp mới; thư chưa được duyệt.");
    } catch (err: any) {
      toastError(err.message || "Lỗi lưu bản nháp email");
    } finally {
      setSavingEmailDraft(false);
    }
  }

  async function handleCopyEmail() {
    if (!emailDraft || emailDraft.status !== "approved" || editingEmailDraft) return;
    try {
      const current = await api.getEmailDraft(id);
      if (current.id !== emailDraft.id || current.status !== "approved") {
        setEmailDraft(current);
        warning("Thư đã đổi. Kiểm tra và duyệt lại trước khi sao chép.");
        return;
      }
    } catch (err: any) {
      setEmailDraft(null);
      toastError(err.message || "Thư đã hết hiệu lực. Tạo và duyệt bản mới.");
      return;
    }
    const textToCopy = `Tiêu đề: ${editingEmailDraft ? editedEmailSubject : emailDraft?.subject}\n\n${editingEmailDraft ? editedEmailBody : emailDraft?.body}`;
    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopiedEmail(true);
      success("Đã sao chép nội dung email vào bộ nhớ tạm!");
      setTimeout(() => setCopiedEmail(false), 2500);
    } catch {
      toastError("Không thể sao chép vào bộ nhớ tạm.");
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

  async function handleSaveInterviewScorecard(submit=false) {
    if (!canInterview || !rubric || !scorecardCriteria.length) return;
    if (!validateScorecardRows(scorecardCriteria, submit)) return;
    if ((currentScorecard?.status === "finalized" && !amendingScorecard) || currentScorecard?.is_stale) {
      warning("Phiếu này đã khóa hoặc đã cũ. Hãy mở lượt phỏng vấn mới theo rubric hiện hành.");
      return;
    }
    setSavingScorecard(true);setScorecardsReady(false);
    try {
      const saved = amendingScorecard ? await api.amendInterviewScorecard(scorecardEditBase.id, {
        expected_version:scorecardEditBase.row_version,criteria:scorecardCriteria,change_reason:amendmentReason.trim(),
      }) : await api.saveInterviewScorecard(id, {
        round_no: scorecardRoundNo,
        submit,
        expected_version: scorecardEditBase.row_version,
        interview_draft_id: interviewDraft?.status === "succeeded" && !interviewDraft?.is_stale ? interviewDraft.id : null,
        criteria: scorecardCriteria,
      });
      setInterviewScorecards((cards) => [
        ...cards.filter((card) => !(card.interviewer_id === saved.interviewer_id
          && card.round_no === saved.round_no && card.rubric_version_id === saved.rubric_version_id)),
        saved,
      ]);
      setScorecardEditBase({id:saved.id,row_version:saved.row_version});
      setScorecardDirty(false);
      setAmendingScorecard(false);setAmendmentReason("");
      try {setInterviewScorecards(await refreshInterviewCards(api,id));setScorecardsReady(true);}
      catch {warning("Phiếu đã lưu, nhưng chưa tải đủ phiếu hội đồng. Làm mới trạng thái trước khi chốt kết luận.");}
      success(amendingScorecard?"Đã lưu điều chỉnh và giữ lịch sử phiếu.":submit?"Đã nộp phiếu phỏng vấn của bạn.":"Đã lưu phiếu phỏng vấn nháp của bạn.");
    } catch (err: any) {
      toastError(err.message || "Không thể lưu phiếu phỏng vấn.");
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
    <div className="candidate-workspace">
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

        <div className="page-header-actions" style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => void loadData(true)}>Làm mới trạng thái</button>
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
        <div><strong>{stageLabels[progress?.stage] || "Chưa xác định trạng thái"}</strong><p className="muted">{progress?.failure_code ? `Lỗi: ${progress.failure_code}. Kiểm tra nguồn trước khi thử lại.` : "Chọn bước bên dưới để xem hồ sơ, kiểm tra bằng chứng hoặc ghi quyết định của HR."}</p></div>
        {!progress?.pending && <button className="btn btn-primary" disabled={!!loadWarnings.length || !progress || application.status !== "active"} onClick={() => {
          if (["awaiting_upload", "reading", "needs_review"].includes(progress.stage)) setActiveTab("sanitization");
          else if (progress.stage === "ready_for_ai") { setActiveTab("assessment"); if (canManage) void handleTriggerAssessment(); }
          else setActiveTab(workflowTab(progress.stage));
        }}>{progress?.stage === "ready_for_ai" && canManage ? "Phân tích CV" : progress?.stage === "awaiting_interview" ? "Chuẩn bị phỏng vấn" : progress?.stage === "needs_review" ? "Rà soát CV" : "Xem bước cần xử lý"}</button>}
      </section>
      <nav className="tabs-container" aria-label="Các bước xử lý hồ sơ">
        {([['sanitization','1. Rà soát CV'],['assessment','2. Đánh giá và bằng chứng'],['revision','3. Kết luận sàng lọc'],['interview','4. Phỏng vấn']] as const).map(([tab,label]) =>
          <button key={tab} className={`tab-btn ${activeTab === tab ? "active" : ""}`} aria-current={activeTab === tab ? "step" : undefined} onClick={() => setActiveTab(tab)}>{label}</button>)}
      </nav>

      {/* Tab 1: Evidence-first Assessment */}
      {activeTab === "assessment" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
          {assessmentRun?.status === "failed" ? (
            <div className="card assessment-failure-card" role="alert">
              <div className="assessment-failure-icon"><IconAlertTriangle size={24} /></div>
              <h2>Không có đánh giá hợp lệ — hồ sơ cần HR xử lý thủ công</h2>
              <p>Hệ thống không sử dụng kết quả lỗi để chấm điểm hay thay đổi trạng thái ứng viên. Bạn có thể rà soát hồ sơ thủ công hoặc thử lại sau khi nguyên nhân được xử lý. Nếu lỗi lặp lại, gửi mã lượt đánh giá cho người phụ trách kỹ thuật.</p>
              <p className="muted">Mã lượt đánh giá: <code>{assessmentRun.id}</code></p>
              {canManage && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => void handleTriggerAssessment()}
                  disabled={!!loadWarnings.length || !!progress?.pending || triggeringAssessment || sanitizedVersion?.status !== "approved"}
                >
                  <IconRefresh size={15} />
                  {triggeringAssessment ? "Đang đưa vào hàng đợi…" : "Tạo lượt đánh giá mới"}
                </button>
              )}
            </div>
          ) : !assessmentRun ? (
            <div className="card" style={{ textAlign: "center", padding: "4rem 1.5rem" }}>
              <div style={{ width: "52px", height: "52px", borderRadius: "50%", background: "var(--accent-soft)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 1.25rem auto" }}>
                <IconSparkles size={28} color="var(--accent-olive)" />
              </div>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: "0.5rem" }}>
                {progress?.stage === "analyzing" ? "AI đang phân tích hồ sơ" : progress?.stage === "error" ? "Phân tích gặp lỗi" : "Hồ sơ chưa có kết quả đánh giá AI"}
              </h2>
              <p style={{ color: "var(--text-secondary)", maxWidth: "620px", margin: "0 auto 1.5rem auto", fontSize: "0.875rem", lineHeight: 1.6 }}>
                Hệ thống sẽ đối chiếu nội dung CV đã khử định danh với các tiêu chí trong rubric đã được HR duyệt. Mỗi nhận định đều có trích dẫn nguyên văn để con người kiểm chứng.
              </p>
              <button
                className="btn btn-primary"
                onClick={() => void handleTriggerAssessment()}
                disabled={!canManage || !!loadWarnings.length || progress?.pending || triggeringAssessment || sanitizedVersion?.status !== "approved" || !requisition?.current_rubric_version_id}
              >
                <IconSparkles size={16} />
                <span>{triggeringAssessment ? "Đang xử lý đánh giá AI…" : "Phân tích CV"}</span>
              </button>
              {sanitizedVersion?.status !== "approved" && (
                <p style={{ color: "var(--amber-text)", fontSize: "0.8rem", marginTop: "0.75rem" }}>
                  Cần HR duyệt bản đã che thông tin định danh trước khi chạy đánh giá.
                </p>
              )}
            </div>
          ) : (
            <div>
              {/* Quick Win 1: Candidate One-Page Summary (Executive Summary) */}
              <div className="card" style={{ marginBottom: "1.5rem", borderLeft: "4px solid var(--accent-cyan)", background: "linear-gradient(180deg, var(--accent-soft) 0%, var(--bg-surface) 100%)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem", marginBottom: "1rem" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.65rem" }}>
                    <div style={{ width: "34px", height: "34px", borderRadius: "8px", background: "var(--accent-soft)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <IconSparkles size={18} color="var(--accent-cyan)" />
                    </div>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <h2 className="card-title" style={{ fontSize: "1.05rem", fontWeight: 700, margin: 0 }}>
                          Tóm Tắt Hồ Sơ Ứng Viên · AI Executive Summary
                        </h2>
                        {executiveSummary?.recommendation_label && (
                          <span className={`badge ${
                            (executiveSummary.comparable_score ?? 0) >= 70 ? "badge-rec-advance" :
                            (executiveSummary.comparable_score ?? 0) < 50 ? "badge-rec-review" : "badge-rec-clarify"
                          }`} style={{ fontSize: "0.75rem", padding: "0.2rem 0.55rem" }}>
                            {executiveSummary.recommendation_label}
                          </span>
                        )}
                        {executiveSummary?.cached && (
                          <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", background: "rgba(255,255,255,0.05)", padding: "0.15rem 0.45rem", borderRadius: "4px" }}>
                            Cache
                          </span>
                        )}
                      </div>
                      <p style={{ color: "var(--text-secondary)", fontSize: "0.8rem", marginTop: "0.2rem" }}>
                        Bản tổng hợp 5 câu giúp HR và Hiring Manager nắm bắt năng lực cốt lõi trong 60 giây
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => void handleGenerateSummary()}
                    disabled={generatingSummary}
                    title="Cập nhật hoặc phân tích lại tóm tắt hồ sơ"
                  >
                    <IconRefresh size={14} className={generatingSummary ? "spin" : ""} />
                    <span>{generatingSummary ? "Đang phân tích…" : executiveSummary ? "Cập nhật tóm tắt" : "Tạo tóm tắt AI"}</span>
                  </button>
                </div>

                {executiveSummary ? (
                  <div>
                    {/* Headline */}
                    <div style={{ fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                      <span>💡</span>
                      <span>{executiveSummary.headline}</span>
                    </div>

                    {/* Summary Narrative */}
                    <div style={{
                      padding: "0.9rem 1.1rem",
                      background: "var(--bg-surface-elevated)",
                      borderRadius: "var(--radius-md)",
                      border: "1px solid var(--border-subtle)",
                      fontSize: "0.885rem",
                      lineHeight: 1.65,
                      color: "var(--text-primary)",
                      marginBottom: "1.25rem",
                      whiteSpace: "pre-line"
                    }}>
                      {executiveSummary.summary_paragraph}
                    </div>

                    {/* Strengths, Gaps, Interview Focus Grid */}
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "1rem" }}>
                      {/* Key Strengths */}
                      <div style={{
                        padding: "0.9rem",
                        background: "var(--emerald-bg)",
                        border: "1px solid var(--emerald-border)",
                        borderRadius: "var(--radius-md)"
                      }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.6rem", fontWeight: 700, fontSize: "0.825rem", color: "var(--emerald-text)" }}>
                          <IconCheckCircle size={15} color="var(--emerald-text)" />
                          <span>Điểm Mạnh Nổi Bật ({executiveSummary.key_strengths?.length || 0})</span>
                        </div>
                        {executiveSummary.key_strengths?.length ? (
                          <ul style={{ margin: 0, paddingLeft: "1.2rem", fontSize: "0.8rem", color: "var(--text-primary)", lineHeight: 1.55 }}>
                            {executiveSummary.key_strengths.map((s, idx) => (
                              <li key={idx} style={{ marginBottom: "0.35rem" }}>{s}</li>
                            ))}
                          </ul>
                        ) : (
                          <p style={{ margin: 0, fontSize: "0.78rem", color: "var(--text-muted)" }}>Chưa ghi nhận điểm mạnh vượt trội rõ ràng.</p>
                        )}
                      </div>

                      {/* Gaps / Questions */}
                      <div style={{
                        padding: "0.9rem",
                        background: "var(--amber-bg)",
                        border: "1px solid var(--amber-border)",
                        borderRadius: "var(--radius-md)"
                      }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.6rem", fontWeight: 700, fontSize: "0.825rem", color: "var(--amber-text)" }}>
                          <IconAlertTriangle size={15} color="var(--amber-text)" />
                          <span>Điểm Cần Lưu Ý / Làm Rõ ({executiveSummary.gaps_or_questions?.length || 0})</span>
                        </div>
                        {executiveSummary.gaps_or_questions?.length ? (
                          <ul style={{ margin: 0, paddingLeft: "1.2rem", fontSize: "0.8rem", color: "var(--text-primary)", lineHeight: 1.55 }}>
                            {executiveSummary.gaps_or_questions.map((g, idx) => (
                              <li key={idx} style={{ marginBottom: "0.35rem" }}>{g}</li>
                            ))}
                          </ul>
                        ) : (
                          <p style={{ margin: 0, fontSize: "0.78rem", color: "var(--text-muted)" }}>Không phát hiện khoảng trống năng lực đáng kể.</p>
                        )}
                      </div>

                      {/* Recommended Interview Focus */}
                      <div style={{
                        padding: "0.9rem",
                        background: "var(--accent-soft)",
                        border: "1px solid var(--border-glow)",
                        borderRadius: "var(--radius-md)"
                      }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.6rem", fontWeight: 700, fontSize: "0.825rem", color: "var(--accent-cyan)" }}>
                          <IconSliders size={15} color="var(--accent-cyan)" />
                          <span>Trọng Tâm Phỏng Vấn Kỹ Thuật</span>
                        </div>
                        {executiveSummary.recommended_interview_focus?.length ? (
                          <ul style={{ margin: 0, paddingLeft: "1.2rem", fontSize: "0.8rem", color: "var(--text-primary)", lineHeight: 1.55 }}>
                            {executiveSummary.recommended_interview_focus.map((f, idx) => (
                              <li key={idx} style={{ marginBottom: "0.35rem" }}>{f}</li>
                            ))}
                          </ul>
                        ) : (
                          <p style={{ margin: 0, fontSize: "0.78rem", color: "var(--text-muted)" }}>Theo sát các câu hỏi chuẩn trong rubric.</p>
                        )}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div style={{ padding: "1.25rem", background: "var(--bg-surface-elevated)", borderRadius: "var(--radius-md)", textAlign: "center" }}>
                    <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "0.75rem" }}>
                      Chưa có bản tóm tắt nhanh cho hồ sơ này. Nhấn nút bên dưới để tổng hợp điểm mạnh, khoảng trống và trọng tâm phỏng vấn.
                    </p>
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      onClick={() => void handleGenerateSummary()}
                      disabled={generatingSummary}
                    >
                      <IconSparkles size={14} />
                      <span>{generatingSummary ? "Đang phân tích…" : "Tạo tóm tắt 1 trang cho HR"}</span>
                    </button>
                  </div>
                )}
              </div>

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
                          <thead><tr><th scope="col">Tiêu chí</th><th scope="col">DeepSeek</th><th scope="col">Jev</th><th scope="col">Độ tin cậy Jev</th><th scope="col">Chênh lệch</th></tr></thead>
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
                    <h2 className="card-title">Đánh giá theo tiêu chí</h2>
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
                        changeReviewedIds(isAllSelected ? [] : allIds);
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

                <div
                  className="table-wrapper assessment-criteria-scroll"
                  role="region"
                  aria-label="Đánh giá theo tiêu chí và bằng chứng"
                  tabIndex={0}
                  style={{ border: "none" }}
                >
                  <table className="data-table assessment-criteria-table">
                    <thead>
                      <tr>
                        <th scope="col" style={{ width: "22%" }}>Tiêu Chí</th>
                        <th scope="col" style={{ width: "12%" }}>Trạng Thái</th>
                        <th scope="col" style={{ width: "10%" }}>Điểm (0..4)</th>
                        <th scope="col" style={{ width: "32%" }}>Giải Trình Đánh Giá Của AI</th>
                        <th scope="col">Bằng chứng và thao tác rà soát</th>
                      </tr>
                    </thead>
                    <tbody>
                      {assessmentRun.criteria.map((c) => (
                        <tr key={c.criterion_id}>
                          <td className="criterion-heading-cell">
                            <strong style={{ fontSize: "0.88rem", color: "var(--text-primary)" }}>{rubric?.criteria?.find((criterion: any) => criterion.id === c.criterion_id)?.label || c.criterion_id}</strong>
                          </td>
                          <td data-label="Trạng thái">
                            <span className={`badge ${c.status === "assessed" ? "badge-open" : "badge-draft"}`}>
                              {c.status === "assessed" ? "Có bằng chứng" : c.status === "insufficient_evidence" ? "Cần làm rõ" : "Bằng chứng mâu thuẫn"}
                            </span>
                          </td>
                          <td data-label="Điểm quan sát">
                            <span style={{
                              fontSize: "1.25rem",
                              fontWeight: 800,
                              fontFamily: "var(--font-mono)",
                              color: c.score !== null && c.score >= 2 ? "var(--emerald-text)" : "var(--amber-text)"
                            }}>
                              {c.score !== null ? `${c.score}/4` : "-"}
                            </span>
                          </td>
                          <td data-label="Nhận định" style={{ fontSize: "0.825rem", lineHeight: 1.55 }}>
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
                          <td data-label="Bằng chứng & rà soát">
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
                              {canManage && ["insufficient_evidence", "conflicting_evidence"].includes(c.status) && (
                                <button
                                  type="button"
                                  className="btn btn-secondary btn-sm evidence-followup-button"
                                  onClick={() => void handleTriggerAssessment([c.criterion_id])}
                                  disabled={assessmentRun.strategy !== "hybrid" || !!progress?.pending || triggeringAssessment || !!loadWarnings.length || sanitizedVersion?.status !== "approved"}
                                  title={assessmentRun.strategy === "hybrid" ? "Tìm thêm nguồn trong CV đã duyệt, tập trung vào tiêu chí này" : "Tính năng truy xuất thêm chỉ có khi bật Hybrid RAG"}
                                >
                                  <IconSparkles size={14} />
                                  {triggeringAssessment ? "Đang xử lý…" : assessmentRun.strategy === "hybrid" ? "Tìm thêm bằng chứng" : "Tìm thêm · cần Hybrid RAG"}
                                </button>
                              )}
                              <label className="rubric-ack"><input type="checkbox" checked={reviewedIds.includes(c.criterion_id)} onChange={event => changeReviewedIds(previous => event.target.checked ? [...previous.filter(x => x !== c.criterion_id), c.criterion_id] : previous.filter(x => x !== c.criterion_id))} />Tôi đã đối chiếu tiêu chí này</label>
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
                <p className="assessment-criteria-scroll-hint">
                  Mở trích dẫn để đối chiếu với CV, sau đó đánh dấu tiêu chí đã rà soát.
                </p>
              </div>
            </div>
          )}
          {assessmentRun?.status === "succeeded" && canManage && rubric && <HRRevisionEditor application={application} rubric={rubric} run={assessmentRun} revisions={hrRevisions} selectedCriterion={editingCriterion} onSaved={() => loadData(true)} />}
        </div>
      )}

      {reviewSaveError && <p role="alert" className="notice notice-error">Chưa lưu được tiến độ: {reviewSaveError}</p>}
      {/* Tab 2: Sanitization & Redaction Viewer */}
      {activeTab === "sanitization" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
          <div className="card">
            <div className="card-header" style={{ flexWrap: "wrap", gap: "0.85rem" }}>
              <div>
                <h2 className="card-title">CV đã che thông tin định danh</h2>
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
              <div className={"cv-review-grid" + (rawPreviewBlob ? " cv-review-grid--compare" : "")}>
                {application.current_document_id && (
                  <section className="cv-review-source" aria-label="Đối chiếu CV gốc">
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
                <div className="cv-review-redacted">
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
                  <div className="cv-redacted-text">
                    {sanitizedVersion.canonical_text}
                  </div>
                )}
                </div>
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
          <ScreeningDecision decisions={decisions} canManage={canManage} busy={submittingDecision}
            blocked={!!loadWarnings.length || (!assessmentRun && !effectiveRevision)} reviewed={reviewedIds.length} total={rubric?.criteria?.length || 0}
            outcome={decisionOutcome} setOutcome={setDecisionOutcome} reason={decisionReason} setReason={setDecisionReason}
            acknowledged={attestCheck1} setAcknowledged={setAttestCheck1} onSubmit={handleSubmitDecision}
            onEvidence={()=>setActiveTab("assessment")} recommendation={effectiveRevision?.recommendation || assessmentRun?.recommendation}
            basis={effectiveRevision?`Bản điều chỉnh HR #${effectiveRevision.revision_no}`:"Đánh giá AI và bằng chứng trên CV"}
            stale={!!decisions[0] && (decisions[0].document_id!==application.current_document_id || decisions[0].rubric_version_id!==requisition?.current_rubric_version_id || ["ready_for_ai","awaiting_decision","needs_review"].includes(progress?.stage))}/>

          {/* Versioned candidate correspondence templates */}
          {canManage && decisions.length > 0 && <details className="card" style={{ borderLeft: "4px solid var(--accent-olive)" }}>
            <summary style={{cursor:"pointer",fontWeight:650,marginBottom:"1rem"}}>Phản hồi ứng viên · Thư theo kết luận hiện hành</summary>
            <div className="card-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.65rem" }}>
                <div style={{ width: "36px", height: "36px", borderRadius: "8px", background: "var(--accent-soft)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <IconMail size={20} color="var(--accent-olive)" />
                </div>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <h2 className="card-title" style={{ fontSize: "1.05rem", fontWeight: 700, margin: 0 }}>
                      Thư phản hồi ứng viên
                    </h2>
                    <span className="badge" style={{ background: "var(--accent-soft)", color: "var(--accent-olive)", border: "1px solid var(--border-glow)" }}>
                      {emailDraft?.status === "approved" ? `HR đã duyệt · v${emailDraft.version_no}` : "Thư nháp — chưa duyệt"}
                    </span>
                  </div>
                  <p style={{ color: "var(--text-secondary)", fontSize: "0.8rem", marginTop: "0.2rem" }}>
                    Mẫu thư để HR chỉnh sửa và duyệt theo quyết định hiện hành. Hệ thống không gửi email và không gọi LLM để soạn thư.
                  </p>
                </div>
              </div>

              <p className="muted">Loại thư được chọn theo kết luận hiện hành của HR.</p>
            </div>

            {/* Email Content Box */}
            {emailDraft ? (
              <div>
                {/* Subject Line & Actions */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.75rem", marginBottom: "0.75rem", padding: "0.6rem 0.85rem", background: "var(--bg-surface-elevated)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-subtle)" }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.05em", marginRight: "0.5rem" }}>
                      Tiêu đề email:
                    </span>
                    {editingEmailDraft ? (
                      <input
                        type="text"
                        className="form-input"
                        style={{ marginTop: "0.25rem", width: "100%", fontSize: "0.85rem" }}
                        value={editedEmailSubject}
                        onChange={(e) => { setEditedEmailSubject(e.target.value); setEmailContentReviewed(false); }}
                      />
                    ) : (
                      <strong style={{ fontSize: "0.875rem", color: "var(--text-primary)" }}>{emailDraft.subject}</strong>
                    )}
                  </div>

                  <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
                    {editingEmailDraft ? (
                      <>
                        <button
                          type="button"
                          className="btn btn-primary btn-sm"
                          onClick={() => void handleSaveEmailDraft()}
                          disabled={savingEmailDraft}
                        >
                          <IconCheckCircle size={14} />
                          <span>{savingEmailDraft ? "Đang lưu…" : "Lưu thay đổi"}</span>
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => {
                            setEditingEmailDraft(false);
                            setEditedEmailSubject(emailDraft.subject);
                            setEditedEmailBody(emailDraft.body);
                          }}
                        >
                          <span>Hủy</span>
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => setEditingEmailDraft(true)}
                          title="Tự chỉnh sửa nội dung hoặc thêm thời gian phỏng vấn cụ thể"
                        >
                          <IconSliders size={14} />
                          <span>Chỉnh sửa</span>
                        </button>
                        <button
                          type="button"
                          className={`btn btn-sm ${copiedEmail ? "btn-primary" : "btn-secondary"}`}
                          onClick={() => void handleCopyEmail()}
                          disabled={emailDraft.status !== "approved" || editingEmailDraft}
                          title="Sao chép tiêu đề và nội dung thư vào bộ nhớ tạm"
                          style={{
                            background: copiedEmail ? "var(--emerald-border)" : undefined,
                            borderColor: copiedEmail ? "var(--emerald-border)" : undefined,
                            color: copiedEmail ? "var(--emerald-text)" : undefined,
                          }}
                        >
                          {copiedEmail ? <IconCheckCircle size={14} /> : <IconCopy size={14} />}
                          <span>{copiedEmail ? "Đã sao chép!" : "Sao chép email"}</span>
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => void handleGenerateEmailDraft()}
                          disabled={generatingEmailDraft}
                          title="Tạo lại bản thảo từ đầu"
                        >
                          <IconRefresh size={14} className={generatingEmailDraft ? "spin" : ""} />
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {/* Email Body */}
                {editingEmailDraft ? (
                  <textarea
                    className="form-textarea"
                    rows={14}
                    style={{ fontFamily: "var(--font-mono)", fontSize: "0.85rem", lineHeight: 1.6 }}
                    value={editedEmailBody}
                    onChange={(e) => { setEditedEmailBody(e.target.value); setEmailContentReviewed(false); }}
                  />
                ) : (
                  <div style={{
                    padding: "1.25rem",
                    background: "var(--bg-surface-elevated)",
                    borderRadius: "var(--radius-md)",
                    border: "1px solid var(--border-medium)",
                    fontFamily: "inherit",
                    fontSize: "0.875rem",
                    lineHeight: 1.7,
                    color: "var(--text-primary)",
                    whiteSpace: "pre-line",
                    maxHeight: "450px",
                    overflowY: "auto"
                  }}>
                    {emailDraft.body}
                  </div>
                )}

                {emailDraft.status !== "approved" && (
                  <div style={{ marginTop: "1rem", display: "grid", gap: "0.75rem" }}>
                    <label className="rubric-ack"><input type="checkbox" checked={emailContentReviewed} onChange={event => setEmailContentReviewed(event.target.checked)} />
                      Tôi đã kiểm tra nội dung thư và đối chiếu với quyết định hiện hành của HR.
                    </label>
                    <button type="button" className="btn btn-primary btn-sm" disabled={!canManage || !emailContentReviewed || !application.current_decision_id || savingEmailDraft}
                      onClick={() => void handleSaveEmailDraft(true)}>Duyệt phiên bản thư này</button>
                    {!application.current_decision_id && <p className="muted">Ghi nhận quyết định của HR trước khi duyệt thư.</p>}
                  </div>
                )}
                {emailDraft.approved_at && <p className="muted">Phiên bản {emailDraft.version_no} · Duyệt lúc {new Date(emailDraft.approved_at).toLocaleString("vi-VN")} · Người duyệt: {emailDraft.approved_by?.slice(0, 8)}</p>}

                {/* Privacy Safeguard Notice */}
                <div style={{ marginTop: "0.85rem", display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                  <IconShield size={14} color="var(--emerald-text)" />
                  <span>
                    Nội dung được kiểm tra để chặn điểm số và dữ liệu đánh giá nội bộ. HR vẫn cần rà soát người nhận, thời gian, nội dung trước khi duyệt. Không tự động gửi thư.
                  </span>
                </div>
              </div>
            ) : (
              <div style={{ textAlign: "center", padding: "1.75rem 1rem", background: "var(--bg-surface-elevated)", borderRadius: "var(--radius-md)" }}>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginBottom: "0.85rem" }}>
                  Chưa có thư nháp hiện hành. Chọn mẫu để soạn; chỉ duyệt thư sau khi HR đã ghi nhận quyết định phù hợp.
                </p>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  onClick={() => void handleGenerateEmailDraft()}
                  disabled={generatingEmailDraft}
                >
                  <IconMail size={14} />
                  <span>{generatingEmailDraft ? "Đang soạn thảo…" : "Tạo bản nháp email ngay"}</span>
                </button>
              </div>
            )}
          </details>}
        </div>
      )}

      {/* Tab 4: Interview Guide */}
      {activeTab === "interview" && (
        <InterviewWorkspace applicationId={id} roundNo={scorecardRoundNo} setRoundNo={setScorecardRoundNo}
          dirty={scorecardDirty || amendingScorecard} canManage={canManage} rubric={rubric} draft={interviewDraft} cardsReady={scorecardsReady}
          generating={triggeringInterview} onGenerate={handleTriggerInterview} cards={interviewScorecards}
          sourceKey={`${application.generation}:${application.current_document_id}:${application.current_sanitized_version_id}:${requisition?.current_jd_version_id}:${application.current_decision_id}`} userId={currentUser?.id} onFocus={setInterviewFocusIds} onRefresh={()=>loadData(true)}>
          <section className="card" aria-labelledby="interview-scorecard-title">
            <div className="card-header" style={{ alignItems: "flex-start", gap: "1rem", flexWrap: "wrap" }}>
              <div>
                <h2 className="card-title" id="interview-scorecard-title">Phiếu đánh giá sau phỏng vấn</h2>
                <p className="muted" style={{ maxWidth: 720, marginTop: "0.4rem" }}>
                  Điểm này do phỏng vấn viên ghi từ câu trả lời trong buổi phỏng vấn. Phiếu tách biệt với điểm AI trên CV và không tự động quyết định tuyển dụng.
                </p>
              </div>

            </div>

            {!rubric?.criteria?.length ? (
              <p role="status" className="notice">Chưa có rubric hiện hành để tạo phiếu đánh giá.</p>
            ) : !canInterview ? (
              <p role="status" className="notice">Tài khoản của bạn chỉ có quyền xem hồ sơ, không được ghi phiếu phỏng vấn.</p>
            ) : (
              <>
                {currentScorecard?.is_stale && <p role="alert" className="notice notice-error">Rubric hoặc CV đã đổi sau khi tạo phiếu. Phiếu này được giữ để kiểm toán nhưng không thể sửa hoặc nộp; hãy chọn lượt mới.</p>}
                {currentScorecard?.status === "finalized" && !currentScorecard?.is_stale && <p role="status" className="notice">Phiếu lượt {scorecardRoundNo} đã nộp và khóa lúc {currentScorecard.finalized_at ? new Date(currentScorecard.finalized_at).toLocaleString("vi-VN") : ""}.</p>}

                <div className="interview-actions" style={{marginTop:"1rem"}}>
                  <button className="btn btn-secondary btn-sm" onClick={()=>setShowAllInterviewCriteria(!showAllInterviewCriteria)}>{showAllInterviewCriteria?"Chỉ xem tiêu chí trọng tâm":"Xem thêm các tiêu chí khác"}</button>
                  <span className="muted">Ghi nhận trọng tâm được phân công; phần chưa quan sát giữ điểm trống.</span>
                  {currentScorecard?.status === "finalized" && !currentScorecard?.is_stale && !amendingScorecard && <button className="btn btn-secondary btn-sm" onClick={()=>{setAmendingScorecard(true);setAmendmentReason("");}}>Điều chỉnh phiếu đã nộp</button>}
                </div>
                <div style={{ display: "grid", gap: "1rem", marginTop: "1rem" }}>
                  {rubric.criteria.filter((criterion:any)=>showAllInterviewCriteria || !interviewFocusIds.length || interviewFocusIds.includes(criterion.id)).map((criterion: any) => {
                    const row = scorecardCriteria.find((entry) => entry.criterion_id === criterion.id);
                    const readOnly = (currentScorecard?.status === "finalized" && !amendingScorecard) || !!currentScorecard?.is_stale;
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
                        {<label style={{ display: "grid", gap: "0.3rem" }}>
                          <span className="form-label">Tóm tắt câu trả lời / căn cứ quan sát {row?.outcome === "assessed" ? "(bắt buộc, ít nhất 20 ký tự)" : "(ghi lý do chưa quan sát nếu là tiêu chí trọng tâm)"}</span>
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
                {amendingScorecard && <label className="form-label" style={{marginTop:"1rem"}}>Lý do điều chỉnh phiếu (ít nhất 20 ký tự)<textarea rows={2} maxLength={1000} value={amendmentReason} onChange={e=>setAmendmentReason(e.target.value)}/></label>}
                <div className="interview-actions" style={{marginTop:"1rem"}}>
                  {!amendingScorecard && <button className="btn btn-secondary" onClick={()=>void handleSaveInterviewScorecard(false)} disabled={savingScorecard || !scorecardDirty || currentScorecard?.status === "finalized" || !!currentScorecard?.is_stale}>Lưu nháp phiếu</button>}
                  <button className="btn btn-primary" onClick={()=>void handleSaveInterviewScorecard(true)} disabled={savingScorecard || !!currentScorecard?.is_stale || (currentScorecard?.status === "finalized" && !amendingScorecard) || (amendingScorecard && amendmentReason.trim().length<20)}>
                    {savingScorecard?"Đang lưu…":amendingScorecard?"Lưu điều chỉnh có lịch sử":"Lưu và nộp phiếu"}</button>
                  {amendingScorecard && <button className="btn btn-secondary" disabled={savingScorecard} onClick={()=>{setAmendingScorecard(false);setScorecardDirty(false);setScorecardCriteria(currentScorecard.criteria);}}>Hủy điều chỉnh</button>}
                  {scorecardDirty&&<span role="status" className="muted">Có thay đổi chưa lưu.</span>}
                </div>
              </>
            )}

          </section>
        </InterviewWorkspace>
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
                background: "var(--accent-soft)",
                border: "1px solid var(--border-glow)",
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
