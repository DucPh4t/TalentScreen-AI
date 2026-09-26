"use client";

import React, { use, useEffect, useState } from "react";
import Link from "next/link";
import { api, RequisitionItem, ApplicationItem } from "@/lib/api";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function RequisitionDetailPage({ params }: PageProps) {
  const { id } = use(params);

  const [requisition, setRequisition] = useState<any>(null);
  const [applications, setApplications] = useState<ApplicationItem[]>([]);
  const [rubric, setRubric] = useState<any>(null);
  const [jdVersion, setJdVersion] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<"applications" | "jd_rubric">("applications");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Status update modal / form
  const [newStatus, setNewStatus] = useState<string>("");
  const [updatingStatus, setUpdatingStatus] = useState(false);

  // Upload candidate CV modal
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [candidateName, setCandidateName] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Rubric action state
  const [rubricActionLoading, setRubricActionLoading] = useState(false);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const req = await api.getRequisition(id);
      setRequisition(req);
      setNewStatus(req.status);

      // Fetch applications sorted by receipt time ascending (Spec 01 FIFO)
      try {
        const apps = await api.listApplications(id);
        const sorted = [...apps].sort(
          (a, b) => new Date(a.received_at).getTime() - new Date(b.received_at).getTime()
        );
        setApplications(sorted);
      } catch (err) {
        console.warn("Could not load applications:", err);
      }

      // Fetch Rubric if attached
      if (req.current_rubric_version_id) {
        try {
          const rub = await api.getRubric(req.current_rubric_version_id);
          setRubric(rub);
        } catch (e) {
          console.warn("Could not load rubric:", e);
        }
      }

      // Fetch JD if attached
      if (req.current_jd_version_id) {
        try {
          const jd = await api.getJDVersion(req.current_jd_version_id);
          setJdVersion(jd);
        } catch (e) {
          console.warn("Could not load JD:", e);
        }
      }
    } catch (err: any) {
      setError(err.message || "Không thể tải thông tin đợt tuyển dụng");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [id]);

  async function handleStatusChange(nextStatus: string) {
    if (!requisition) return;
    setUpdatingStatus(true);
    try {
      const updated = await api.patchRequisition(
        id,
        { status: nextStatus },
        requisition.row_version
      );
      setRequisition(updated);
      setNewStatus(updated.status);
    } catch (err: any) {
      alert("Lỗi cập nhật trạng thái: " + err.message);
    } finally {
      setUpdatingStatus(false);
    }
  }

  async function handleUploadCV(e: React.FormEvent) {
    e.preventDefault();
    if (!uploadFile) {
      setUploadError("Vui lòng chọn tệp CV (.pdf hoặc .docx)");
      return;
    }

    if (uploadFile.size > 10 * 1024 * 1024) {
      setUploadError("Tệp vượt quá giới hạn 10MB.");
      return;
    }

    setUploading(true);
    setUploadError(null);
    try {
      // 1. Create application intake record
      const app = await api.createApplication(id, candidateName || undefined);
      // 2. Upload file
      await api.uploadDocument(app.id, uploadFile);

      setShowUploadModal(false);
      setCandidateName("");
      setUploadFile(null);
      await loadData();
    } catch (err: any) {
      setUploadError(err.message || "Tải lên hồ sơ thất bại");
    } finally {
      setUploading(false);
    }
  }

  async function handleCreateSeedRubric() {
    if (!requisition) return;
    setRubricActionLoading(true);
    try {
      // Create seed standard 6 criteria rubric
      const newRubric = await api.createRubric(id, {
        name: `Rubric Tiêu chuẩn - ${requisition.title}`,
        is_seed_import: true,
      });
      setRubric(newRubric);
      await loadData();
    } catch (err: any) {
      alert("Không thể tạo Rubric mẫu: " + err.message);
    } finally {
      setRubricActionLoading(false);
    }
  }

  async function handleApproveRubric() {
    if (!rubric) return;
    setRubricActionLoading(true);
    try {
      await api.approveRubric(rubric.id, rubric.row_version);
      alert("Rubric đã được phê duyệt làm tiêu chuẩn chính thức!");
      await loadData();
    } catch (err: any) {
      alert("Không thể phê duyệt Rubric: " + err.message);
    } finally {
      setRubricActionLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="card" style={{ textAlign: "center", padding: "4rem" }}>
        <div style={{ color: "var(--text-muted)" }}>Đang tải dữ liệu đợt tuyển dụng...</div>
      </div>
    );
  }

  if (error || !requisition) {
    return (
      <div className="card" style={{ borderColor: "var(--danger)" }}>
        <h2 style={{ color: "var(--danger)", marginBottom: "0.5rem" }}>Lỗi truy cập</h2>
        <p style={{ color: "var(--text-muted)", marginBottom: "1rem" }}>{error}</p>
        <Link href="/requisitions" className="btn btn-secondary">
          Quay lại danh sách
        </Link>
      </div>
    );
  }

  return (
    <div>
      {/* Header bar */}
      <div style={{ marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
          <Link href="/requisitions" style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
            ← Đợt tuyển dụng
          </Link>
          <span style={{ color: "var(--text-muted)" }}>/</span>
          <span style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>{requisition.id.slice(0, 8)}</span>
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.25rem" }}>
              <h1 style={{ fontSize: "1.75rem", fontWeight: 700 }}>{requisition.title}</h1>
              <span className={`badge badge-${requisition.status}`}>{requisition.status.toUpperCase()}</span>
            </div>
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
              Phòng ban: <strong style={{ color: "var(--text-primary)" }}>{requisition.department || "Chưa phân loại"}</strong> • Phiên bản khóa lạc quan (v{requisition.row_version})
            </p>
          </div>

          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
            {/* State machine transitions */}
            {requisition.status === "draft" && (
              <button
                className="btn btn-primary"
                onClick={() => handleStatusChange("open")}
                disabled={updatingStatus}
              >
                Mở đợt tuyển dụng (OPEN)
              </button>
            )}
            {requisition.status === "open" && (
              <button
                className="btn btn-secondary"
                onClick={() => handleStatusChange("paused")}
                disabled={updatingStatus}
              >
                Tạm dừng (PAUSE)
              </button>
            )}
            {requisition.status === "paused" && (
              <button
                className="btn btn-primary"
                onClick={() => handleStatusChange("open")}
                disabled={updatingStatus}
              >
                Kích hoạt lại (RESUME)
              </button>
            )}
            {requisition.status !== "closed" && (
              <button
                className="btn btn-secondary"
                style={{ borderColor: "var(--border-subtle)" }}
                onClick={() => {
                  if (confirm("Bạn có chắc muốn đóng đợt tuyển dụng này? Không thể nhận thêm hồ sơ.")) {
                    handleStatusChange("closed");
                  }
                }}
                disabled={updatingStatus}
              >
                Đóng đợt (CLOSE)
              </button>
            )}

            <button className="btn btn-primary" onClick={() => setShowUploadModal(true)}>
              + Tiếp nhận hồ sơ CV
            </button>
          </div>
        </div>
      </div>

      {/* Tabs navigation */}
      <div className="tabs">
        <button
          className={`tab-btn ${activeTab === "applications" ? "active" : ""}`}
          onClick={() => setActiveTab("applications")}
        >
          Danh sách hồ sơ ({applications.length})
        </button>
        <button
          className={`tab-btn ${activeTab === "jd_rubric" ? "active" : ""}`}
          onClick={() => setActiveTab("jd_rubric")}
        >
          Mô tả công việc (JD) & Tiêu chí (Rubric)
        </button>
      </div>

      {/* Tab 1: Applications (Ordered by receipt time ascending) */}
      {activeTab === "applications" && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <div style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>
              Thứ tự hiển thị: <strong>Thời gian tiếp nhận tăng dần (FIFO)</strong> — Đảm bảo tính công bằng, không thiên vị điểm số.
            </div>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <span className="badge badge-received">Tổng: {applications.length}</span>
            </div>
          </div>

          {applications.length === 0 ? (
            <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
              <p style={{ color: "var(--text-muted)", marginBottom: "1rem" }}>
                Chưa có hồ sơ nào được nộp cho đợt tuyển dụng này.
              </p>
              <button className="btn btn-primary" onClick={() => setShowUploadModal(true)}>
                + Tải lên hồ sơ ứng viên đầu tiên
              </button>
            </div>
          ) : (
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Mã ẩn danh</th>
                    <th>Thời gian nộp (FIFO)</th>
                    <th>Trạng thái</th>
                    <th>Thế hệ (Gen)</th>
                    <th>Đánh giá AI</th>
                    <th>Quyết định</th>
                    <th style={{ textAlign: "right" }}>Thao tác</th>
                  </tr>
                </thead>
                <tbody>
                  {applications.map((app) => (
                    <tr key={app.id}>
                      <td>
                        <span style={{ fontFamily: "monospace", fontWeight: 600, color: "var(--accent-glow)" }}>
                          {app.public_label}
                        </span>
                      </td>
                      <td style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                        {new Date(app.received_at).toLocaleString("vi-VN")}
                      </td>
                      <td>
                        <span className={`badge badge-${app.status}`}>
                          {app.status.toUpperCase()}
                        </span>
                      </td>
                      <td>
                        <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                          g{app.generation}
                        </span>
                      </td>
                      <td>
                        {app.current_assessment_run_id ? (
                          <span style={{ color: "var(--success)", fontSize: "0.875rem", display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
                            ✓ Đã đánh giá
                          </span>
                        ) : (
                          <span style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Chưa chạy</span>
                        )}
                      </td>
                      <td>
                        {app.current_decision_id ? (
                          <span className="badge badge-open">Đã có quyết định</span>
                        ) : (
                          <span style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Chờ duyệt</span>
                        )}
                      </td>
                      <td style={{ textAlign: "right" }}>
                        <Link href={`/applications/${app.id}`} className="btn btn-secondary" style={{ padding: "0.35rem 0.75rem", fontSize: "0.8125rem" }}>
                          Xem không gian xét duyệt →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Tab 2: JD & Rubric */}
      {activeTab === "jd_rubric" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          {/* Job Description Card */}
          <div className="card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 600 }}>Mô tả công việc (Job Description)</h2>
              {jdVersion && (
                <span className="badge badge-open">Phiên bản v{jdVersion.version_no} (Hash: {jdVersion.content_hash?.slice(0, 8)})</span>
              )}
            </div>
            {jdVersion ? (
              <div style={{
                background: "var(--bg-main)",
                padding: "1rem",
                borderRadius: "var(--radius-sm)",
                fontSize: "0.875rem",
                lineHeight: 1.6,
                maxHeight: "300px",
                overflowY: "auto",
                whiteSpace: "pre-wrap",
                fontFamily: "inherit",
              }}>
                {jdVersion.canonical_text}
              </div>
            ) : (
              <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
                Chưa có văn bản JD chuẩn hóa được liên kết.
              </p>
            )}
          </div>

          {/* Rubric Card */}
          <div className="card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem", flexWrap: "wrap", gap: "0.5rem" }}>
              <div>
                <h2 style={{ fontSize: "1.25rem", fontWeight: 600 }}>Rubric đánh giá (6 Tiêu chí chuẩn hóa)</h2>
                <p style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>
                  Tổng trọng số phải bằng đúng 100%. Nghiêm cấm mọi đặc tính nhân khẩu học (tuổi, giới tính, trường học, hình ảnh).
                </p>
              </div>

              <div style={{ display: "flex", gap: "0.5rem" }}>
                {!rubric ? (
                  <button
                    className="btn btn-primary"
                    onClick={handleCreateSeedRubric}
                    disabled={rubricActionLoading}
                  >
                    + Khởi tạo 6 Tiêu chí Mẫu
                  </button>
                ) : rubric.status === "draft" ? (
                  <button
                    className="btn btn-primary"
                    onClick={handleApproveRubric}
                    disabled={rubricActionLoading}
                  >
                    Phê duyệt Rubric (Owner)
                  </button>
                ) : (
                  <span className="badge badge-open">✓ Đã phê duyệt chính thức</span>
                )}
              </div>
            </div>

            {rubric && rubric.criteria ? (
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th style={{ width: "25%" }}>Tiêu chí</th>
                      <th style={{ width: "10%" }}>Trọng số</th>
                      <th style={{ width: "15%" }}>Bắt buộc</th>
                      <th>Thang đo mức độ (Anchors 0..4)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rubric.criteria.map((c: any) => (
                      <tr key={c.id}>
                        <td>
                          <strong>{c.name}</strong>
                          <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                            {c.description}
                          </div>
                        </td>
                        <td>
                          <span style={{ fontWeight: 600, color: "var(--accent-glow)" }}>
                            {c.weight}%
                          </span>
                        </td>
                        <td>
                          {c.is_core ? (
                            <span className="badge badge-paused">Tiêu chí cốt lõi (Sàn 2.0)</span>
                          ) : (
                            <span style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>Tiêu chuẩn</span>
                          )}
                        </td>
                        <td style={{ fontSize: "0.8125rem" }}>
                          {c.scoring_anchors && (
                            <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                              <div><strong>0:</strong> {c.scoring_anchors["0"] || "Chưa đạt"}</div>
                              <div><strong>2:</strong> {c.scoring_anchors["2"] || "Đạt chuẩn cơ bản"}</div>
                              <div><strong>4:</strong> {c.scoring_anchors["4"] || "Vượt trội"}</div>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
                Chưa có Rubric nào được liên kết với đợt tuyển dụng này. Vui lòng bấm &quot;Khởi tạo 6 Tiêu chí Mẫu&quot; để thiết lập.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Upload CV Modal */}
      {showUploadModal && (
        <div className="modal-backdrop">
          <div className="modal-content">
            <h2 style={{ fontSize: "1.25rem", fontWeight: 600, marginBottom: "0.5rem" }}>
              Tiếp nhận hồ sơ ứng viên mới
            </h2>
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", marginBottom: "1.5rem" }}>
              Hệ thống sẽ lưu trữ an toàn trong kho bảo mật cách ly, tự động trích xuất NFC Unicode và gán mã ẩn danh.
            </p>

            {uploadError && (
              <div style={{ padding: "0.75rem", background: "rgba(239, 68, 68, 0.1)", border: "1px solid var(--danger)", borderRadius: "var(--radius-sm)", color: "var(--danger)", fontSize: "0.875rem", marginBottom: "1rem" }}>
                {uploadError}
              </div>
            )}

            <form onSubmit={handleUploadCV}>
              <div className="form-group">
                <label className="form-label">Tên ứng viên (Tùy chọn ghi nhận):</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Ví dụ: Nguyễn Văn A (sẽ được ẩn danh)"
                  value={candidateName}
                  onChange={(e) => setCandidateName(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Tệp CV đính kèm (*.pdf, *.docx, tối đa 10MB):</label>
                <input
                  type="file"
                  className="form-input"
                  accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  onChange={(e) => {
                    if (e.target.files && e.target.files[0]) {
                      setUploadFile(e.target.files[0]);
                    }
                  }}
                  required
                />
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "1.5rem" }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowUploadModal(false)}
                  disabled={uploading}
                >
                  Hủy
                </button>
                <button type="submit" className="btn btn-primary" disabled={uploading}>
                  {uploading ? "Đang xử lý tiếp nhận..." : "Tải lên & Khởi tạo"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
