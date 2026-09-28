"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { 
  IconShield, 
  IconLock, 
  IconTrash, 
  IconCheckCircle, 
  IconAlertTriangle, 
  IconFileText,
  IconArrowRight
} from "@/components/Icons";
import { useToast } from "@/components/Toast";

export default function RetentionPage() {
  const { success, error: toastError, warning } = useToast();
  const [targetId, setTargetId] = useState("");
  const [scope, setScope] = useState<"application" | "candidate">("application");
  const [reasonCategory, setReasonCategory] = useState("candidate_request");
  const [submitting, setSubmitting] = useState(false);
  const [successMsg, setSuccessMsg] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [policy, setPolicy] = useState<{ sandbox_ttl_days: number; temp_file_ttl_hours: number; backup_retention_days: number; active_policy_name: string } | null>(null);
  const [deletionId, setDeletionId] = useState<string | null>(null);
  const [deletionStatus, setDeletionStatus] = useState<string | null>(null);

  useEffect(() => {
    void api.getRetentionPolicy().then(setPolicy).catch(() => setErrorMsg("Không tải được chính sách lưu giữ hiện hành."));
  }, []);

  async function refreshDeletionStatus() {
    if (!deletionId) return;
    try {
      const result = await api.getDeletionRequest(deletionId);
      setDeletionStatus(result.status);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Không lấy được trạng thái yêu cầu xóa.");
    }
  }

  async function handleManualDeletion(e: React.FormEvent) {
    e.preventDefault();
    if (!targetId.trim()) {
      warning("Vui lòng nhập UUID của hồ sơ hoặc ứng viên cần xóa.");
      return;
    }

    setSubmitting(true);
    setErrorMsg("");
    setSuccessMsg("");
    try {
      const result = await api.requestDeletion(scope, targetId.trim(), reasonCategory);
      setDeletionId(result.id);
      setDeletionStatus(result.status);
      const msg = `Đã tạo yêu cầu xóa ${result.id}. Trạng thái: ${result.status}`;
      setSuccessMsg(msg);
      success(msg, "Đã Đưa Vào Hàng Đợi Xóa");
      setTargetId("");
    } catch (err: any) {
      const msg = err.message || "Không thể thực hiện yêu cầu xóa dữ liệu.";
      setErrorMsg(msg);
      toastError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      {/* Page Header */}
      <div className="page-header">
        <div>
          <div className="breadcrumbs">
            <Link href="/">Trang chủ</Link>
            <span>/</span>
            <span style={{ color: "var(--text-primary)" }}>Lưu giữ dữ liệu</span>
          </div>
          <h1 className="page-title">Lưu giữ và xóa dữ liệu</h1>
          <p className="page-subtitle">
            Xem cấu hình thời hạn hiện hành và theo dõi yêu cầu xóa hồ sơ.
          </p>
        </div>
      </div>

      {/* KPI Policy Cards Grid */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-header">
            <span className="kpi-label">Dữ liệu tập huấn</span>
            <div className="kpi-icon-pill">
              <IconLock size={18} />
            </div>
          </div>
          <div className="kpi-val">{policy ? `${policy.sandbox_ttl_days} ngày` : "—"}</div>
          <div className="kpi-subtext">
            <span>Thời hạn của dữ liệu sandbox; không áp dụng cho CV thật.</span>
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-header">
            <span className="kpi-label">Tệp tạm</span>
            <div className="kpi-icon-pill" style={{ background: "rgba(16, 185, 129, 0.1)", color: "#34d399" }}>
              <IconTrash size={18} color="#34d399" />
            </div>
          </div>
          <div className="kpi-val">{policy ? `${policy.temp_file_ttl_hours} giờ` : "—"}</div>
          <div className="kpi-subtext">
            <span>Thời hạn xử lý tệp tạm theo cấu hình.</span>
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-header">
            <span className="kpi-label">Bản sao lưu</span>
            <div className="kpi-icon-pill" style={{ background: "rgba(99, 102, 241, 0.1)", color: "#818cf8" }}>
              <IconShield size={18} color="#818cf8" />
            </div>
          </div>
          <div className="kpi-val">{policy ? `${policy.backup_retention_days} ngày` : "—"}</div>
          <div className="kpi-subtext">
            <span>Thời gian lưu giữ bản sao theo cấu hình.</span>
          </div>
        </div>
      </div>

      {/* Policy Details & Right to Erasure */}
      <div className="retention-grid">
        {/* Left Column: Formal Policy Specifications */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          <div className="card">
            <div className="card-header">
              <h2 className="card-title">Quy trình xử lý dữ liệu</h2>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
              <div style={{ display: "flex", gap: "1rem", alignItems: "flex-start" }}>
                <div style={{ width: "32px", height: "32px", borderRadius: "var(--radius-sm)", background: "rgba(56, 189, 248, 0.1)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <IconLock size={16} color="var(--accent-cyan)" />
                </div>
                <div>
                  <h3 style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.25rem" }}>
                    1. Kiểm tra bản đã che thông tin
                  </h3>
                  <p style={{ fontSize: "0.835rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
                    Hệ thống tạo bản đã che; HR cần kiểm tra và phê duyệt trước khi dùng để đánh giá AI. Dữ liệu có thể vẫn chứa thông tin định danh sót lại.
                  </p>
                </div>
              </div>

              <div style={{ display: "flex", gap: "1rem", alignItems: "flex-start" }}>
                <div style={{ width: "32px", height: "32px", borderRadius: "var(--radius-sm)", background: "rgba(16, 185, 129, 0.1)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <IconCheckCircle size={16} color="#34d399" />
                </div>
                <div>
                  <h3 style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.25rem" }}>
                    2. Đối chiếu bằng chứng
                  </h3>
                  <p style={{ fontSize: "0.835rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
                    Điểm AI chỉ hỗ trợ rà soát. HR đối chiếu trích dẫn với CV và JD trước khi đưa ra quyết định.
                  </p>
                </div>
              </div>

              <div style={{ display: "flex", gap: "1rem", alignItems: "flex-start" }}>
                <div style={{ width: "32px", height: "32px", borderRadius: "var(--radius-sm)", background: "rgba(244, 63, 94, 0.1)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <IconTrash size={16} color="var(--rose-text)" />
                </div>
                <div>
                  <h3 style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.25rem" }}>
                    3. Theo dõi yêu cầu xóa
                  </h3>
                  <p style={{ fontSize: "0.835rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
                    Yêu cầu xóa đánh dấu hồ sơ và đưa tác vụ xóa vào hàng đợi. Chỉ xác nhận hoàn tất sau khi trạng thái và báo cáo xác minh được cập nhật.
                  </p>
                </div>
              </div>

              <div style={{ display: "flex", gap: "1rem", alignItems: "flex-start" }}>
                <div style={{ width: "32px", height: "32px", borderRadius: "var(--radius-sm)", background: "rgba(99, 102, 241, 0.1)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <IconShield size={16} color="#818cf8" />
                </div>
                <div>
                  <h3 style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.25rem" }}>
                    4. Quyền truy cập và lưu vết
                  </h3>
                  <p style={{ fontSize: "0.835rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
                    Chỉ người có quyền phù hợp mới được xử lý yêu cầu. Các thao tác cần được ghi nhận để kiểm tra sau này.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: On-demand Deletion Tool */}
        <div className="card" style={{ border: "1px solid var(--border-medium)" }}>
          <div className="card-header">
            <div>
              <h2 className="card-title">Tạo yêu cầu xóa dữ liệu</h2>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.825rem", marginTop: "0.2rem" }}>
                Nhập mã hồ sơ hoặc ứng viên và theo dõi tiến độ xử lý.
              </p>
            </div>
          </div>

          {successMsg && (
            <div style={{
              backgroundColor: "var(--emerald-bg)",
              color: "var(--emerald-text)",
              border: "1px solid var(--emerald-border)",
              padding: "0.85rem 1rem",
              borderRadius: "var(--radius-sm)",
              marginBottom: "1.25rem",
              fontSize: "0.85rem",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem"
            }}>
              <IconCheckCircle size={16} color="var(--emerald-text)" />
              <span>{successMsg}</span>
            </div>
          )}
          {deletionId && <div className="notice notice-warning" style={{ marginBottom: "1rem" }}><span>Mã yêu cầu: <code>{deletionId}</code><br />Trạng thái hiện tại: <strong>{deletionStatus || "Đang kiểm tra"}</strong></span><button type="button" className="btn btn-sm btn-outline" onClick={() => void refreshDeletionStatus()}>Cập nhật</button></div>}

          {errorMsg && (
            <div style={{
              backgroundColor: "var(--rose-bg)",
              color: "var(--rose-text)",
              border: "1px solid var(--rose-border)",
              padding: "0.85rem 1rem",
              borderRadius: "var(--radius-sm)",
              marginBottom: "1.25rem",
              fontSize: "0.85rem",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem"
            }}>
              <IconAlertTriangle size={16} color="var(--rose-text)" />
              <span>{errorMsg}</span>
            </div>
          )}

          <form onSubmit={handleManualDeletion}>
            <div className="form-group">
              <label className="form-label" htmlFor="targetId">Mã định danh đối tượng (UUID)</label>
              <input
                id="targetId"
                className="form-input"
                type="text"
                placeholder="Ví dụ: b7e91240-3b4c-4e89-a021-..."
                value={targetId}
                onChange={(e) => setTargetId(e.target.value)}
                required
              />
              <span className="form-helper">
                Nhập UUID của Hồ sơ ứng tuyển (Application ID) hoặc Ứng viên (Candidate ID)
              </span>
            </div>

            <div className="form-group">
              <label className="form-label">Phạm vi thực hiện</label>
              <select
                className="form-select"
                value={scope}
                onChange={(e: any) => setScope(e.target.value)}
              >
                <option value="application">Chỉ xóa Hồ sơ ứng tuyển này (Application)</option>
                <option value="candidate">Xóa toàn bộ Ứng viên và tất cả hồ sơ liên quan (Candidate)</option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Căn cứ pháp lý / Lý do xóa</label>
              <select
                className="form-select"
                value={reasonCategory}
                onChange={(e) => setReasonCategory(e.target.value)}
              >
                <option value="candidate_request">Yêu cầu từ ứng viên</option>
                <option value="retention_expired">Hết hạn theo chính sách hiện hành</option>
                <option value="legal_obligation">Yêu cầu pháp lý hoặc cơ quan quản lý</option>
              </select>
            </div>

            <button
              type="submit"
              className="btn btn-danger"
              style={{ width: "100%", marginTop: "0.5rem" }}
              disabled={submitting}
            >
              <IconTrash size={16} />
              <span>{submitting ? "Đang tạo yêu cầu…" : "Tạo yêu cầu xóa"}</span>
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
