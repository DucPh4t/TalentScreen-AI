"use client";

import React, { use, useEffect, useState } from "react";
import Link from "next/link";
import { api, RequisitionItem, ApplicationItem, ReviewQueueItem, CandidateComparison } from "@/lib/api";
import {
  IconFileText,
  IconSparkles,
  IconArrowRight,
  IconUpload,
  IconX,
  IconCheckCircle,
  IconAlertTriangle,
  IconLock,
  IconShield,
  IconUserCheck,
  IconPlus
} from "@/components/Icons";
import { useToast } from "@/components/Toast";
import { SkeletonTable, Skeleton } from "@/components/Skeleton";
import QuestionBankSetup from "@/components/QuestionBankSetup";
import { stageLabels } from "@/lib/workflow";
import BatchDropzone from "@/components/BatchDropzone";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function RequisitionDetailPage({ params }: PageProps) {
  const { id } = use(params);
  const { success, error: toastError, warning, info } = useToast();
  const [showCloseModal, setShowCloseModal] = useState(false);

  const [requisition, setRequisition] = useState<any>(null);
  const [applications, setApplications] = useState<ApplicationItem[]>([]);
  const [reviewQueue, setReviewQueue] = useState<ReviewQueueItem[]>([]);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [stageFilter, setStageFilter] = useState("");
  const [uploadBusy, setUploadBusy] = useState(false);
  const [pendingOnly, setPendingOnly] = useState(false);
  const [comparison, setComparison] = useState<CandidateComparison | null>(null);
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  const [rubric, setRubric] = useState<any>(null);
  const [jdVersion, setJdVersion] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<"applications" | "jd_rubric" | "comparison">("applications");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [applicationsLoadError, setApplicationsLoadError] = useState<string | null>(null);
  const [rubricLoadError, setRubricLoadError] = useState<string | null>(null);
  const [jdLoadError, setJdLoadError] = useState<string | null>(null);

  // Status update
  const [updatingStatus, setUpdatingStatus] = useState(false);

  // Upload modal
  const [showUploadModal, setShowUploadModal] = useState(false);

  // Rubric action state
  const [rubricActionLoading, setRubricActionLoading] = useState(false);
  const [acknowledgedRubric, setAcknowledgedRubric] = useState(false);
  const [jdDraftText, setJdDraftText] = useState("");
  const [savingJD, setSavingJD] = useState(false);
  const canManage = requisition?.my_role === "owner" || requisition?.my_role === "admin";
  const canCompare = requisition?.my_role === "owner";
  const canReviewIndependently = requisition?.my_role === "reviewer";

  const rubricJDAligned = Boolean(rubric && jdVersion && rubric.jd_version_id === jdVersion.id && rubric.criteria?.length > 0 && rubric.criteria.every((criterion: any) =>
    criterion.source_requirements?.length > 0 && criterion.source_requirements.every((ref: any) =>
      typeof ref.quote === "string" && ref.quote.length > 0 && jdVersion.source_text.includes(ref.quote)
    )
  ));

  async function loadData(silent = false) {
    if (!silent) setLoading(true);
    setError(null);
    setApplicationsLoadError(null);
    setRubricLoadError(null);
    setJdLoadError(null);
    setQueueError(null);
    setReviewQueue([]);

    setComparison(null);
    try {
      const req = await api.getRequisition(id);
      setRequisition(req);

      // FIFO sorted applications by received_at asc
      try {
        const apps = await api.listApplications(id);
        const sorted = [...apps].sort(
          (a, b) => new Date(a.received_at).getTime() - new Date(b.received_at).getTime()
        );
        setApplications(sorted);
        try {
          setReviewQueue(await api.getReviewQueue(id));
        } catch (queueErr) {
          console.warn("Could not load review queue:", queueErr);
          setQueueError("Không tải được trạng thái rà soát CV.");
        }
      } catch (err) {
        console.warn("Could not load applications:", err);
        setApplicationsLoadError("Không tải được danh sách hồ sơ. Thử lại trước khi tiếp tục.");
      }

      try {
        const versions = await api.listRubrics(id);
        setRubric(versions.find((version) => version.status === "draft") || versions.find((version) => version.id === req.current_rubric_version_id) || null);
        setAcknowledgedRubric(false);
      } catch (e) {
        console.warn("Could not load rubrics:", e);
        setRubric(null);
        setRubricLoadError("Không tải được rubric. Thử lại trước khi tạo hoặc duyệt bản mới.");
      }

      if (req.current_jd_version_id) {
        try {
          const jd = await api.getJDVersion(req.current_jd_version_id);
          setJdVersion(jd);
        } catch (e) {
          console.warn("Could not load JD:", e);
          setJdVersion(null);
          setJdLoadError("Không tải được JD hiện hành. Thử lại trước khi tạo phiên bản khác.");
        }
      }
    } catch (err: any) {
      setError(err.message || "Không thể tải thông tin đợt tuyển dụng");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (new URLSearchParams(window.location.search).has("setup")) setActiveTab("jd_rubric");
    loadData();
  }, [id]);

  useEffect(() => {
    if (activeTab !== "comparison" || !canCompare) return;
    let active = true;
    setComparisonError(null);
    api.getCandidateComparison(id)
      .then((data) => { if (active) setComparison(data); })
      .catch((err) => { if (active) setComparisonError(err.message || "Không tải được ma trận so sánh."); });
    return () => { active = false; };
  }, [activeTab, id, applications, canCompare]);

  useEffect(() => {
    if (!reviewQueue.some(item => ["reading", "analyzing"].includes(item.workflow_stage || ""))) return;
    let active = true; let running = false;
    const timer = window.setInterval(async () => {
      if (running || document.visibilityState !== "visible") return; running = true;
      try { const [queue, apps] = await Promise.all([api.getReviewQueue(id), api.listApplications(id)]); if (active) { setReviewQueue(queue); setApplications(apps); setQueueError(null); } }
      catch { if (active) setQueueError("Không cập nhật được tiến độ. Thử làm mới danh sách."); } finally { running = false; }
    }, 5000);
    return () => { active = false; window.clearInterval(timer); };
  }, [id, reviewQueue]);

  const queueByApplication = new Map(reviewQueue.map((item) => [item.application_id, item]));
  const displayedApplications = pendingOnly
    ? applications.filter((item) => {
        const queueItem = queueByApplication.get(item.id);
        return queueItem && (queueItem.sanitized_status !== "approved" || queueItem.risk_flags.length > 0);
      })
    : applications;

  async function handleStatusChange(nextStatus: string) {
    if (!requisition) return;
    setUpdatingStatus(true);
    try {
      const updated = await api.patchRequisition(
        id,
        { status: nextStatus, reason: `HR cập nhật trạng thái đợt tuyển dụng: ${nextStatus}` },
        requisition.row_version
      );
      setRequisition((previous: any) => ({ ...previous, ...updated, my_role: previous?.my_role }));
      success(`Đã cập nhật trạng thái đợt tuyển dụng: ${nextStatus.toUpperCase()}`);
    } catch (err: any) {
      toastError(err.message || "Lỗi cập nhật trạng thái");
    } finally {
      setUpdatingStatus(false);
    }
  }


  async function handleCreateSeedRubric() {
    if (!requisition) return;
    setRubricActionLoading(true);
    try {
      const newRubric = await api.createRubric(id, { source: "seed", jd_version_id: requisition.current_jd_version_id });
      setRubric(newRubric);
      success("Đã khởi tạo bộ 6 tiêu chí Rubric mẫu!");
      await loadData();
    } catch (err: any) {
      toastError(err.message || "Không thể tạo Rubric mẫu");
    } finally {
      setRubricActionLoading(false);
    }
  }

  async function handleApproveRubric() {
    if (!rubric || !acknowledgedRubric || !rubricJDAligned) return;
    setRubricActionLoading(true);
    try {
      if (!requisition?.current_jd_version_id) throw new Error("Cần có JD hiện hành trước khi duyệt rubric.");
      await api.approveRubric(rubric.id, requisition.row_version, requisition.current_jd_version_id);
      success("Rubric đã được phê duyệt làm tiêu chuẩn chính thức!");
      await loadData();
    } catch (err: any) {
      toastError(err.message || "Không thể phê duyệt Rubric");
    } finally {
      setRubricActionLoading(false);
    }
  }

  async function handleCreateJD(event: React.FormEvent) {
    event.preventDefault();
    if (!requisition) return;
    setSavingJD(true);
    try {
      await api.createJDVersion(id, jdDraftText, requisition.row_version);
      setJdDraftText("");
      success("Đã lưu văn bản Mô tả công việc (JD) mới!");
      await loadData();
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Không thể lưu JD");
    } finally {
      setSavingJD(false);
    }
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
        <div className="card" style={{ padding: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', flex: 1 }}>
            <Skeleton width="180px" height="14px" />
            <Skeleton width="340px" height="28px" />
            <Skeleton width="220px" height="14px" />
          </div>
          <Skeleton width="120px" height="38px" borderRadius="10px" />
        </div>
        <SkeletonTable rows={5} cols={7} />
      </div>
    );
  }

  if (error || !requisition) {
    return (
      <div className="card" style={{ borderColor: "var(--rose-border)", maxWidth: "600px", margin: "3rem auto", textAlign: "center" }}>
        <div style={{ width: "48px", height: "48px", borderRadius: "50%", background: "var(--rose-bg)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 1rem auto" }}>
          <IconAlertTriangle size={24} color="var(--rose-text)" />
        </div>
        <h2 style={{ color: "var(--rose-text)", marginBottom: "0.5rem" }}>Không Thể Mở Đợt Tuyển Dụng</h2>
        <p style={{ color: "var(--text-secondary)", marginBottom: "1.5rem" }}>{error}</p>
        <Link href="/requisitions" className="btn btn-secondary">
          Quay lại danh sách đợt tuyển dụng
        </Link>
      </div>
    );
  }

  return (
    <div>
      {/* Top Breadcrumb & Header */}
      <div className="page-header">
        <div>
          <div className="breadcrumbs">
            <Link href="/">Trang chủ</Link>
            <span>/</span>
            <Link href="/requisitions">Đợt tuyển dụng</Link>
            <span>/</span>
            <span style={{ color: "var(--text-primary)", fontFamily: "var(--font-mono)" }}>
              {requisition.id.slice(0, 8)}…
            </span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.85rem", flexWrap: "wrap" }}>
            <h1 className="page-title">{requisition.title}</h1>
            <span className={`badge badge-${requisition.status}`}>
              {requisition.status === "open" && "ĐANG MỞ (OPEN)"}
              {requisition.status === "draft" && "BẢN NHÁP (DRAFT)"}
              {requisition.status === "paused" && "TẠM DỪNG (PAUSED)"}
              {requisition.status === "closed" && "ĐÃ ĐÓNG (CLOSED)"}
            </span>
          </div>

          <p className="page-subtitle">
            Mã đợt: <strong style={{ color: "var(--text-primary)" }}>{requisition.id.slice(0, 8)}</strong> • Phiên bản dữ liệu: <span style={{ fontFamily: "var(--font-mono)", color: "var(--accent-cyan)" }}>v{requisition.row_version}</span>
          </p>
        </div>

        {/* Action Controls */}
        <div style={{ display: "flex", gap: "0.65rem", flexWrap: "wrap", alignItems: "center" }}>
          <button type="button" className="btn btn-secondary" onClick={() => void loadData()}>Làm mới trạng thái</button>
          {canManage && requisition.status === "draft" && (
            <button
              className="btn btn-primary"
              onClick={() => handleStatusChange("open")}
              disabled={updatingStatus}
            >
              Mở Nhận Hồ Sơ
            </button>
          )}
          {canManage && requisition.status === "open" && (
            <button
              className="btn btn-secondary"
              onClick={() => handleStatusChange("paused")}
              disabled={updatingStatus}
            >
              Tạm Dừng Tuyển
            </button>
          )}
          {canManage && requisition.status === "paused" && (
            <button
              className="btn btn-primary"
              onClick={() => handleStatusChange("open")}
              disabled={updatingStatus}
            >
              Tiếp Tục Mở Lại
            </button>
          )}
          {canManage && requisition.status !== "closed" && (
            <button
              className="btn btn-outline"
              onClick={() => setShowCloseModal(true)}
              disabled={updatingStatus}
            >
              Đóng Đợt
            </button>
          )}

          {canManage && requisition.status === "open" && <button className="btn btn-primary" onClick={() => setShowUploadModal(true)}>
            <IconUpload size={16} />
            <span>Tiếp Nhận Hồ Sơ CV</span>
          </button>}
        </div>
      </div>

      {/* Tabs Switcher */}
      <div className="tabs-container">
        <button
          className={`tab-btn ${activeTab === "applications" ? "active" : ""}`}
          onClick={() => setActiveTab("applications")}
        >
          <IconFileText size={16} />
          <span>Danh Sách Ứng Viên ({applicationsLoadError ? "—" : applications.length})</span>
        </button>
        <button
          className={`tab-btn ${activeTab === "jd_rubric" ? "active" : ""}`}
          onClick={() => setActiveTab("jd_rubric")}
        >
          <IconSparkles size={16} />
          <span>Thiết lập JD, tiêu chí và câu hỏi</span>
        </button>
        <button
          className={`tab-btn ${activeTab === "comparison" ? "active" : ""}`}
          onClick={() => setActiveTab("comparison")}
          title={!canCompare ? "Chỉ Owner đợt tuyển dụng mới có quyền xem Ma trận so sánh" : undefined}
        >
          <IconUserCheck size={16} />
          <span>Ma trận so sánh</span>
          {!canCompare && (
            <span className="badge badge-subtle" style={{ fontSize: "0.65rem", padding: "0.15rem 0.4rem", marginLeft: "0.35rem" }}>
              Owner
            </span>
          )}
        </button>
      </div>

      {/* Tab 1: Applications (Strict Spec 01 FIFO Order) */}
      {activeTab === "applications" && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem", flexWrap: "wrap", gap: "0.5rem" }}>
            <div style={{ fontSize: "0.85rem", color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <IconShield size={14} color="#34d399" />
              <span>Thứ tự hiển thị: <strong style={{ color: "var(--text-primary)" }}>Thời gian tiếp nhận tăng dần (FIFO)</strong>. HR vẫn cần rà soát từng hồ sơ.</span>
            </div>
            <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
              <span className="badge badge-subtle">Tổng: {applicationsLoadError ? "—" : applications.length} hồ sơ</span>
              <button type="button" className="btn btn-secondary btn-sm" disabled={Boolean(queueError)} onClick={() => setPendingOnly(!pendingOnly)}>
                {pendingOnly ? "Hiện tất cả" : `Chờ rà soát (${reviewQueue.filter((item) => item.sanitized_status !== "approved" || item.risk_flags.length > 0).length})`}
              </button>
            </div>
          </div>

          <div className="workflow-actions"><label>Tìm mã hồ sơ<input className="form-input" value={search} onChange={e => setSearch(e.target.value)} placeholder="CAND-…" /></label><label>Lọc công việc<select className="form-input" value={stageFilter} onChange={e => setStageFilter(e.target.value)}><option value="">Tất cả trạng thái</option>{Object.entries(stageLabels).map(([stage,label]) => <option key={stage} value={stage}>{label}</option>)}</select></label><button className="btn btn-secondary" onClick={() => void loadData(true)}>Làm mới danh sách</button></div>
          {queueError && <p role="alert" className="notice notice-error">{queueError}</p>}

          {applicationsLoadError ? (
            <div className="card" role="alert"><h3>Không tải được danh sách hồ sơ</h3><p className="muted">{applicationsLoadError}</p><button type="button" className="btn btn-secondary" onClick={() => void loadData()}>Thử lại</button></div>
          ) : applications.length === 0 ? (
            <div className="card" style={{ padding: "2.5rem 1.5rem", textAlign: "center" }}>
              <div style={{ width: "48px", height: "48px", borderRadius: "50%", background: "rgba(56, 189, 248, 0.12)", color: "var(--accent-cyan)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 1rem auto" }}>
                <IconUpload size={24} color="var(--accent-cyan)" />
              </div>
              <h3 style={{ fontSize: "1.15rem", fontWeight: 700, marginBottom: "0.35rem" }}>Chưa có hồ sơ nào được tiếp nhận</h3>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", maxWidth: "520px", margin: "0 auto 1.5rem auto", lineHeight: 1.6 }}>
                Đợt tuyển dụng chưa có hồ sơ ứng viên. Bạn có thể kéo thả hàng loạt 10–50 tệp CV (PDF hoặc DOCX) để hệ thống tự động bóc tách và che thông tin định danh PII.
              </p>
              {canManage && requisition.status === "open" && (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => setShowUploadModal(true)}
                  style={{ margin: "0 auto" }}
                >
                  <IconUpload size={16} />
                  <span>Kéo thả / Tiếp nhận hồ sơ CV ngay</span>
                </button>
              )}
            </div>
          ) : (
            <div className="card" style={{ padding: "0.5rem" }}>
              <div className="table-wrapper" style={{ border: "none" }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Mã hồ sơ</th>
                      <th>Thời Gian Nộp (FIFO)</th>
                      <th>Trạng Thái Hồ Sơ</th>
                      <th>CV đã che / Cảnh báo</th>
                      {!canReviewIndependently && <><th>Tiến độ công việc</th><th>Đánh giá AI</th><th>Quyết định HR</th></>}
                      <th style={{ textAlign: "right" }}>Thao Tác</th>
                    </tr>
                  </thead>
                  <tbody>
                    {displayedApplications.filter(app => app.public_label.toLowerCase().includes(search.trim().toLowerCase()) && (!stageFilter || queueByApplication.get(app.id)?.workflow_stage === stageFilter)).map((app, index) => (
                      <tr key={app.id}>
                        <td>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                              #{index + 1}
                            </span>
                            <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700, color: "var(--accent-cyan)", fontSize: "0.9rem" }}>
                              {app.public_label}
                            </span>
                          </div>
                        </td>
                        <td style={{ fontSize: "0.825rem", color: "var(--text-secondary)" }}>
                          {new Date(app.received_at).toLocaleString("vi-VN")}
                        </td>
                        <td>
                          <span className={`badge badge-${app.status}`}>
                            {app.status === "active" ? "ĐANG XỬ LÝ" : app.status === "tombstoned" ? "ĐÃ ĐÁNH DẤU XÓA" : app.status.toUpperCase()}
                          </span>
                        </td>
                        <td>
                          <span className={`badge ${queueByApplication.get(app.id)?.sanitized_status === "approved" ? "badge-open" : "badge-paused"}`}>
                            {queueError ? "Chưa xác định" : queueByApplication.get(app.id)?.sanitized_status === "approved" ? "Đã rà soát" : queueByApplication.get(app.id)?.sanitized_status === "draft" ? "Chờ rà soát" : "Chưa sẵn sàng"}
                          </span>
                          {queueByApplication.get(app.id)?.risk_flags.includes("contact_data") && <small role="alert" style={{ display: "block", color: "var(--rose-text)" }}>Còn dấu hiệu thông tin liên hệ</small>}
                          {queueByApplication.get(app.id)?.risk_flags.includes("parse_quality") && <small style={{ display: "block", color: "var(--rose-text)" }}>Cần kiểm tra chất lượng trích xuất</small>}
                        </td>
                        {!canReviewIndependently && <><td>
                          <span className="badge badge-subtle" style={{ fontFamily: "var(--font-mono)", fontSize: "0.725rem" }}>
                            {stageLabels[queueByApplication.get(app.id)?.workflow_stage || ""] || "Chưa xác định"}
                          </span>
                        </td>
                        <td>
                          {app.current_assessment_run_id ? (
                            <span className="badge badge-open">
                              <IconCheckCircle size={12} color="#34d399" />
                              <span>Có bản đánh giá</span>
                            </span>
                          ) : (
                            <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Chưa chạy</span>
                          )}
                        </td>
                        <td>
                          {app.current_decision_id ? (
                            <span className="badge badge-rec-advance">Đã Có Quyết Định</span>
                          ) : (
                            <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Chờ duyệt</span>
                          )}
                        </td></>}
                        <td style={{ textAlign: "right" }}>
                          {canReviewIndependently && <Link href={`/applications/${app.id}/independent-review`} className="btn btn-outline btn-sm" style={{ marginRight: "0.4rem" }}>
                            Chấm độc lập
                          </Link>}
                          {!canReviewIndependently && <Link href={`/applications/${app.id}`} className="btn btn-secondary btn-sm">
                            <span>Không Gian Xét Duyệt</span>
                            <IconArrowRight size={14} />
                          </Link>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === "comparison" && (
        <div className="card" style={{ padding: "1.25rem" }}>
          {!canCompare ? (
            <div style={{ textAlign: "center", padding: "2.5rem 1rem" }}>
              <div style={{ width: "48px", height: "48px", borderRadius: "50%", background: "rgba(245, 158, 11, 0.12)", color: "var(--amber-text)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 1rem auto" }}>
                <IconShield size={24} color="var(--amber-text)" />
              </div>
              <h3 style={{ fontSize: "1.15rem", fontWeight: 700, marginBottom: "0.5rem" }}>
                Quyền Xem Ma Trận So Sánh Ứng Viên
              </h3>
              <p style={{ color: "var(--text-secondary)", maxWidth: "540px", margin: "0 auto 1.25rem auto", fontSize: "0.875rem", lineHeight: 1.6 }}>
                Bảng ma trận so sánh đa chiều và điểm xếp hạng được bảo vệ theo nguyên tắc phòng ngừa thiên kiến đối chiếu. Chỉ <strong>Chủ sở hữu đợt tuyển dụng (Owner)</strong> mới có quyền tổng hợp và đối chiếu toàn bộ ứng viên.
              </p>
              <div style={{ display: "inline-block", padding: "0.4rem 0.85rem", background: "var(--bg-surface-elevated)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-subtle)", fontSize: "0.8rem", color: "var(--text-muted)" }}>
                Vai trò hiện tại của bạn: <strong style={{ color: "var(--accent-cyan)", fontFamily: "var(--font-mono)" }}>{requisition.my_role?.toUpperCase() || "THÀNH VIÊN"}</strong>
              </div>
            </div>
          ) : (
            <div>
              <h2>So sánh theo rubric hiện hành</h2>
              <p className="muted">Chỉ Owner xem được bảng này. Điểm không đủ bằng chứng hoặc đánh giá đã cũ không được xếp hạng.</p>
              {comparisonError ? <p role="alert" className="notice notice-error">{comparisonError}</p> : !comparison ? <p>Đang tải ma trận…</p> : (
                <div className="table-wrapper">
                  <table className="data-table">
                    <thead><tr><th>Ứng viên</th>{comparison.criteria.map((criterion) => <th key={criterion.id}>{criterion.label}</th>)}<th>Độ phủ</th><th>Điểm so sánh</th><th>Trạng thái</th></tr></thead>
                    <tbody>{comparison.candidates.map((candidate) => (
                      <tr key={candidate.application_id}>
                        <td><Link href={`/applications/${candidate.application_id}`}>{candidate.public_label}</Link></td>
                        {comparison.criteria.map((criterion) => {
                          const value = candidate.criteria[criterion.id];
                          return <td key={criterion.id}>{value?.status === "assessed" && value.score !== null ? `${value.score}/4` : "Cần làm rõ"}</td>;
                        })}
                        <td>{candidate.coverage === null ? "—" : `${Math.round(candidate.coverage * 100)}%`}</td>
                        <td>{candidate.comparable_score === null ? "Không so sánh" : `${candidate.comparable_score.toFixed(1)}/100`}</td>
                        <td>{candidate.assessment_status === "succeeded" ? (candidate.recommendation || "Đã đánh giá") : "Chưa có đánh giá hiện hành"}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Job Description & 6-Criteria Rubric */}
      {activeTab === "jd_rubric" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
          {/* Job Description Card */}
          <div className="card">
            <div className="card-header">
              <div>
                <h2 className="card-title">Bản Mô Tả Công Việc (Job Description)</h2>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.825rem", marginTop: "0.2rem" }}>
                  Văn bản nguồn để trích xuất bằng chứng kỹ thuật và đối chiếu tiêu chuẩn
                </p>
              </div>
              {jdVersion && (
                <span className="badge badge-subtle" style={{ fontFamily: "var(--font-mono)" }}>
                  Phiên bản v{jdVersion.version_no} (Hash: {jdVersion.text_hash?.slice(0, 8)})
                </span>
              )}
            </div>

            {jdLoadError ? <div className="notice notice-error" role="alert">{jdLoadError}<button type="button" className="btn btn-sm btn-outline" onClick={() => void loadData()}>Thử lại</button></div> : jdVersion ? (
              <div style={{
                background: "var(--bg-surface-elevated)",
                border: "1px solid var(--border-subtle)",
                padding: "1.25rem",
                borderRadius: "var(--radius-sm)",
                fontSize: "0.875rem",
                lineHeight: 1.65,
                maxHeight: "350px",
                overflowY: "auto",
                whiteSpace: "pre-wrap",
                fontFamily: "var(--font-sans)",
                color: "var(--text-primary)"
              }}>
                {jdVersion.source_text}
              </div>
            ) : (
              <form onSubmit={handleCreateJD}>
                <p className="muted" style={{ marginBottom: "0.8rem" }}>Chưa có JD. Bổ sung văn bản nguồn trước khi tạo rubric.</p>
                <label className="form-label" htmlFor="jdDraftText">Nội dung JD</label>
                <textarea id="jdDraftText" className="form-textarea" rows={8} minLength={50} required value={jdDraftText} onChange={(event) => setJdDraftText(event.target.value)} placeholder="Mô tả vị trí, nhiệm vụ và yêu cầu năng lực…" />
                <button type="submit" className="btn btn-primary" style={{ marginTop: "0.85rem" }} disabled={savingJD}>{savingJD ? "Đang lưu…" : "Lưu JD"}</button>
              </form>
            )}
          </div>

          {requisition.current_rubric_version_id && <QuestionBankSetup rubricId={requisition.current_rubric_version_id} canManage={canCompare && requisition.status !== "closed"} />}
          {/* Rubric Card */}
          <div className="card">
            <div className="card-header" style={{ flexWrap: "wrap", gap: "0.75rem" }}>
              <div>
                <h2 className="card-title">Bộ Tiêu Chí Đánh Giá Chuẩn Hóa (Rubric)</h2>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.825rem", marginTop: "0.2rem" }}>
                  Sáu tiêu chí kỹ thuật và trọng số cần được HR, chuyên môn IT kiểm tra trước khi duyệt.
                </p>
              </div>

              <div>
                {!rubric ? (
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={handleCreateSeedRubric}
                    disabled={rubricActionLoading || !jdVersion || Boolean(rubricLoadError)}
                  >
                    <IconPlus size={14} />
                    <span>Khởi Tạo 6 Tiêu Chí Mẫu</span>
                  </button>
                ) : rubric.status === "draft" ? (
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={handleApproveRubric}
                    disabled={rubricActionLoading || !acknowledgedRubric || !rubricJDAligned}
                  >
                    <IconCheckCircle size={14} />
                    <span>Phê Duyệt Rubric (Owner)</span>
                  </button>
                ) : (
                  <span className="badge badge-open">
                    <IconCheckCircle size={12} color="#34d399" />
                    <span>Đã Duyệt Chính Thức</span>
                  </span>
                )}
              </div>
            </div>

            {rubricLoadError && <div className="notice notice-error" role="alert">{rubricLoadError}<button type="button" className="btn btn-sm btn-outline" onClick={() => void loadData()}>Thử lại</button></div>}
            {rubric?.status === "draft" && (
              <div className="notice notice-warning" style={{ marginBottom: "1rem" }}>
                Bản nháp chưa được dùng để đánh giá. Kiểm tra từng tiêu chí, thang điểm và ngưỡng bên dưới trước khi phê duyệt.
              </div>
            )}
            {rubric?.status === "draft" && !rubricJDAligned && <div className="notice notice-error" role="alert">Trích dẫn nguồn trong rubric seed chưa khớp nguyên văn với JD hiện hành. Không thể phê duyệt rubric này; cần JD phù hợp hoặc chỉnh rubric theo JD thật.</div>}

            {rubric?.threshold_config && (
              <div className="rubric-policy">
                <strong>Quy tắc gợi ý</strong>
                <span>Ngưỡng điểm: {rubric.threshold_config.threshold ?? "—"}/100</span>
                <span>Điểm tối thiểu tiêu chí cốt lõi: {Object.entries(rubric.threshold_config.core_minimum_scores || {}).map(([key, value]) => `${key}: ${value}`).join(", ") || "Không cấu hình"}</span>
                <span>Yêu cầu đủ bằng chứng: {rubric.threshold_config.require_full_coverage ? "Có" : "Không"}</span>
              </div>
            )}

            {rubric && rubric.criteria && rubric.criteria.length > 0 ? (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "1rem" }}>
                {rubric.criteria.map((c: any) => (
                  <div
                    key={c.id}
                    style={{
                      background: "var(--bg-surface-elevated)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "var(--radius-md)",
                      padding: "1.15rem",
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "space-between"
                    }}
                  >
                    <div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.5rem" }}>
                        <h3 style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--text-primary)" }}>{c.label}</h3>
                        <span className="badge badge-subtle" style={{ fontFamily: "var(--font-mono)", fontWeight: 700, color: "var(--accent-cyan)" }}>
                          {c.weight}%
                        </span>
                      </div>
                      <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)", lineHeight: 1.5, marginBottom: "0.75rem" }}>
                        {c.description}
                      </p>
                      {c.source_requirements?.map((ref: any) => <p className="rubric-source" key={ref.requirement_id}><strong>{ref.requirement_id}</strong> · {ref.quote}</p>)}
                    </div>

                    <div className="rubric-anchors"><strong>{c.core ? "Tiêu chí cốt lõi" : "Tiêu chí bổ trợ"}</strong>{c.scoring_anchors?.map((anchor: any) => <p key={anchor.score}><b>{anchor.score}/4</b> {anchor.description}</p>)}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ textAlign: "center", padding: "2.5rem 1rem" }}>
                <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", marginBottom: "1rem" }}>
                  Chưa có tiêu chí Rubric nào được gán. Hãy khởi tạo bộ 6 tiêu chí chuẩn hóa mẫu.
                </p>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={handleCreateSeedRubric}
                  disabled={rubricActionLoading || !jdVersion || Boolean(rubricLoadError)}
                >
                  <IconPlus size={14} />
                  <span>Khởi Tạo 6 Tiêu Chí Mẫu Ngay</span>
                </button>
              </div>
            )}
            {rubric?.status === "draft" && <label className="rubric-ack"><input type="checkbox" checked={acknowledgedRubric} onChange={(event) => setAcknowledgedRubric(event.target.checked)} /><span>Tôi đã đối chiếu tiêu chí, trọng số và ngưỡng với JD. Tôi xác nhận rubric này để HR sử dụng khi rà soát.</span></label>}
          </div>
        </div>
      )}

      {/* Modal: Batch Upload Candidate CVs */}
      {showUploadModal && (
        <div className="modal-overlay">
          <div className="modal-card" style={{ maxWidth: "640px" }}>
            <div className="modal-header">
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <div style={{ width: "32px", height: "32px", borderRadius: "var(--radius-sm)", background: "var(--accent-gradient)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <IconUpload size={18} color="#fff" />
                </div>
                <div>
                  <h2 className="modal-title">Tiếp Nhận Hồ Sơ CV Hàng Loạt</h2>
                  <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>Kéo thả đồng thời 10–50 tệp PDF/DOCX; hệ thống tự động bóc tách &amp; che PII.</p>
                </div>
              </div>
              <button
                disabled={uploadBusy}
                onClick={() => setShowUploadModal(false)}
                style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer" }}
                aria-label="Đóng hộp thoại"
              >
                <IconX size={20} />
              </button>
            </div>

            <div style={{
              background: "rgba(56, 189, 248, 0.08)",
              border: "1px solid rgba(56, 189, 248, 0.2)",
              padding: "0.75rem 1rem",
              borderRadius: "var(--radius-sm)",
              fontSize: "0.8rem",
              color: "var(--text-secondary)",
              marginBottom: "1.25rem"
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", color: "var(--accent-cyan)", fontWeight: 600, marginBottom: "0.2rem" }}>
                <IconLock size={14} color="var(--accent-cyan)" />
                <span>Tự động che thông tin · HR cần rà soát</span>
              </div>
              Tất cả file được tiếp nhận vào hàng đợi xử lý độc lập. HR sẽ kiểm tra bản che trước khi kích hoạt đánh giá.
            </div>

            <BatchDropzone
              requisitionId={id}
              onUploadComplete={async () => {
                await loadData(true);
              }}
              onBusyChange={setUploadBusy}
              onClose={() => setShowUploadModal(false)}
            />

            <div className="modal-footer" style={{ marginTop: "1rem" }}>
              <button
                type="button"
                disabled={uploadBusy}
                onClick={() => setShowUploadModal(false)}
                className="btn btn-secondary"
              >
                Đóng hộp thoại
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Confirm Closing Requisition */}
      {showCloseModal && (
        <div className="modal-overlay">
          <div className="modal-card" style={{ maxWidth: "460px" }}>
            <div className="modal-header">
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <div style={{ width: "32px", height: "32px", borderRadius: "var(--radius-sm)", background: "rgba(244, 63, 94, 0.12)", color: "#be123c", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <IconAlertTriangle size={18} color="#be123c" />
                </div>
                <h2 className="modal-title">Xác Nhận Đóng Đợt Tuyển Dụng</h2>
              </div>
            </div>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", lineHeight: 1.5, margin: "1rem 0 1.5rem 0" }}>
              Bạn có chắc chắn muốn đóng đợt tuyển dụng này? Hệ thống sẽ tạm dừng tiếp nhận hồ sơ ứng viên mới.
            </p>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setShowCloseModal(false)} disabled={updatingStatus}>
                Hủy bỏ
              </button>
              <button
                className="btn btn-danger"
                onClick={async () => {
                  setShowCloseModal(false);
                  await handleStatusChange("closed");
                }}
                disabled={updatingStatus}
              >
                Đồng ý Đóng Đợt
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
