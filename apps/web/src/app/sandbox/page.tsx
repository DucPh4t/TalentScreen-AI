"use client";

import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface Scenario {
  id: string;
  title: string;
  category: string;
  description: string;
  learning_objective: string;
  candidate_profile: {
    public_label: string;
    experience_summary: string;
    skills: string[];
  };
  ai_preliminary_assessment: any;
  instructions: string[];
}

export default function SandboxPage() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [onboardingStatus, setOnboardingStatus] = useState<any>(null);
  const [activeStepIndex, setActiveStepIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  // Quote Drawer State (Scenario 1)
  const [isQuoteDrawerOpen, setIsQuoteDrawerOpen] = useState(false);

  // HR Override State (Scenario 3)
  const [overrideScore, setOverrideScore] = useState<number>(3);
  const [overrideReason, setOverrideReason] = useState<string>("");

  // Attested Decision State (Scenario 4)
  const [attestationAccepted, setAttestationAccepted] = useState(false);
  const [selectedOutcome, setSelectedOutcome] = useState<string>("advance");

  const stepKeys = [
    "step_1_inspect_source",
    "step_2_missing_evidence",
    "step_3_hr_override",
    "step_4_attested_decision",
    "step_5_audit_trail",
  ];

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [scenariosData, statusData] = await Promise.all([
        api.getSandboxScenarios(),
        api.getOnboardingStatus().catch(() => ({
          completed_steps: {},
          is_completed: false,
          remaining_steps: stepKeys,
        })),
      ]);
      setScenarios(scenariosData);
      setOnboardingStatus(statusData);

      // Set active step to first incomplete step
      const completed = statusData.completed_steps || {};
      const firstIncomplete = stepKeys.findIndex((k) => !completed[k]);
      if (firstIncomplete >= 0) {
        setActiveStepIndex(firstIncomplete);
      }
    } catch (err: any) {
      console.error("Failed to load sandbox data:", err);
    } finally {
      setLoading(false);
    }
  }

  async function completeStep(stepId: string, resultData: any) {
    try {
      const updated = await api.completeOnboardingStep(stepId, resultData);
      setOnboardingStatus(updated);
      setActionMessage(`Đã hoàn thành bước: ${stepId}`);
      if (activeStepIndex < 4) {
        setActiveStepIndex(activeStepIndex + 1);
      }
    } catch (err: any) {
      alert("Lỗi khi ghi nhận hoàn thành bước: " + (err.message || String(err)));
    }
  }

  async function handleReset() {
    if (!confirm("Bạn có chắc chắn muốn làm lại bài tập huấn luyện Sandbox từ đầu?")) return;
    try {
      const resetData = await api.resetOnboarding();
      setOnboardingStatus(resetData);
      setActiveStepIndex(0);
      setActionMessage("Đã đặt lại tiến độ huấn luyện Sandbox.");
    } catch (err: any) {
      alert("Lỗi reset: " + err.message);
    }
  }

  if (loading) {
    return (
      <div style={{ padding: "3rem", textAlign: "center" }}>
        <p style={{ color: "#94a3b8" }}>Đang tải môi trường Sandbox Huấn Luyện...</p>
      </div>
    );
  }

  const currentScenario = scenarios[activeStepIndex];
  const completedSteps = onboardingStatus?.completed_steps || {};
  const isAllCompleted = onboardingStatus?.is_completed || false;

  return (
    <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "1.5rem" }}>
      {/* Header & Isolation Banner */}
      <div style={{ marginBottom: "2rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.75rem" }}>
          <div>
            <h1 style={{ fontSize: "1.875rem", fontWeight: 700, color: "#f8fafc", marginBottom: "0.5rem" }}>
              Sandbox Huấn Luyện & Mô Phỏng HR (Onboarding Walkthrough)
            </h1>
            <p style={{ color: "#94a3b8", fontSize: "0.95rem", maxWidth: "800px" }}>
              Môi trường giả lập an toàn, tách biệt 100% với dữ liệu tuyển dụng thật. Dành cho HR và thành viên hội đồng
              thực hành 5 tình huống then chốt: kiểm tra xuất xứ bằng chứng, phát hiện thiếu thông tin, ghi đè đánh giá,
              ký duyệt quyết định thẩm định và tra cứu nhật ký kiểm toán.
            </p>
          </div>
          <button
            onClick={handleReset}
            style={{
              padding: "0.5rem 1rem",
              background: "#334155",
              color: "#cbd5e1",
              border: "1px solid #475569",
              borderRadius: "0.375rem",
              fontSize: "0.85rem",
              cursor: "pointer",
            }}
          >
            Làm lại từ đầu
          </button>
        </div>

        {actionMessage && (
          <div
            style={{
              background: "rgba(16, 185, 129, 0.15)",
              border: "1px solid #10b981",
              color: "#34d399",
              padding: "0.75rem 1rem",
              borderRadius: "0.375rem",
              marginBottom: "1rem",
              fontSize: "0.9rem",
            }}
          >
            {actionMessage}
          </div>
        )}

        {/* Stepper Bar */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(5, 1fr)",
            gap: "0.75rem",
            marginTop: "1.5rem",
          }}
        >
          {scenarios.map((sc, idx) => {
            const stepKey = stepKeys[idx];
            const isDone = !!completedSteps[stepKey];
            const isActive = idx === activeStepIndex;

            return (
              <div
                key={sc.id}
                onClick={() => setActiveStepIndex(idx)}
                style={{
                  background: isActive ? "#1e293b" : "#0f172a",
                  border: isActive ? "2px solid #38bdf8" : isDone ? "1px solid #10b981" : "1px solid #334155",
                  padding: "0.875rem",
                  borderRadius: "0.5rem",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.35rem" }}>
                  <span style={{ fontSize: "0.75rem", fontWeight: 700, color: isActive ? "#38bdf8" : "#94a3b8" }}>
                    BƯỚC {idx + 1}
                  </span>
                  {isDone ? (
                    <span style={{ color: "#34d399", fontSize: "0.8rem", fontWeight: 600 }}>✓ Xong</span>
                  ) : (
                    <span style={{ color: "#64748b", fontSize: "0.8rem" }}>Chưa làm</span>
                  )}
                </div>
                <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "#f1f5f9", lineHeight: 1.3 }}>
                  {sc.title.split(": ")[1] || sc.title}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Main Scenario Workspace */}
      {currentScenario && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
          {/* Left Column: Learning Objective & Candidate Context */}
          <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            <div
              style={{
                background: "#0f172a",
                border: "1px solid #334155",
                borderRadius: "0.5rem",
                padding: "1.25rem",
              }}
            >
              <span
                style={{
                  background: "#0369a1",
                  color: "#bae6fd",
                  padding: "0.2rem 0.5rem",
                  borderRadius: "0.25rem",
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  textTransform: "uppercase",
                }}
              >
                Mục Tiêu Huấn Luyện
              </span>
              <p style={{ color: "#e2e8f0", fontSize: "0.95rem", marginTop: "0.75rem", lineHeight: 1.5 }}>
                {currentScenario.learning_objective}
              </p>
              <div style={{ marginTop: "1rem", borderTop: "1px solid #1e293b", paddingTop: "0.75rem" }}>
                <span style={{ fontSize: "0.8rem", color: "#94a3b8", fontWeight: 600 }}>Bối cảnh tình huống:</span>
                <p style={{ color: "#cbd5e1", fontSize: "0.875rem", marginTop: "0.25rem" }}>
                  {currentScenario.description}
                </p>
              </div>
            </div>

            {/* Candidate Mock Data */}
            <div
              style={{
                background: "#0f172a",
                border: "1px solid #334155",
                borderRadius: "0.5rem",
                padding: "1.25rem",
              }}
            >
              <h3 style={{ fontSize: "1rem", fontWeight: 600, color: "#f8fafc", marginBottom: "0.75rem" }}>
                Hồ Sơ Ứng Viên Giả Lập:{" "}
                <span style={{ color: "#38bdf8", fontFamily: "monospace" }}>
                  {currentScenario.candidate_profile.public_label}
                </span>
              </h3>
              <p style={{ fontSize: "0.875rem", color: "#94a3b8", marginBottom: "0.75rem" }}>
                {currentScenario.candidate_profile.experience_summary}
              </p>
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                {currentScenario.candidate_profile.skills.map((s) => (
                  <span
                    key={s}
                    style={{
                      background: "#1e293b",
                      border: "1px solid #475569",
                      color: "#cbd5e1",
                      padding: "0.2rem 0.5rem",
                      borderRadius: "0.25rem",
                      fontSize: "0.75rem",
                    }}
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>

            {/* Instructions */}
            <div
              style={{
                background: "#0f172a",
                border: "1px solid #334155",
                borderRadius: "0.5rem",
                padding: "1.25rem",
              }}
            >
              <h4 style={{ fontSize: "0.9rem", fontWeight: 600, color: "#f8fafc", marginBottom: "0.5rem" }}>
                Hướng Dẫn Thực Hành:
              </h4>
              <ul style={{ paddingLeft: "1.25rem", color: "#94a3b8", fontSize: "0.875rem", lineHeight: 1.6 }}>
                {currentScenario.instructions.map((inst, i) => (
                  <li key={i}>{inst}</li>
                ))}
              </ul>
            </div>
          </div>

          {/* Right Column: Interactive Practice Area */}
          <div
            style={{
              background: "#0f172a",
              border: "1px solid #334155",
              borderRadius: "0.5rem",
              padding: "1.5rem",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
            }}
          >
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                <h3 style={{ fontSize: "1.1rem", fontWeight: 600, color: "#f8fafc" }}>
                  Khu Vực Thao Tác Thực Hành
                </h3>
                <span style={{ fontSize: "0.75rem", color: "#38bdf8" }}>Tình huống {activeStepIndex + 1} / 5</span>
              </div>

              {/* SCENARIO 1: Inspect Source Quote */}
              {activeStepIndex === 0 && (
                <div>
                  <p style={{ color: "#94a3b8", fontSize: "0.875rem", marginBottom: "1rem" }}>
                    Dưới đây là nhận định sơ bộ của AI cho tiêu chí{" "}
                    <strong>{currentScenario.ai_preliminary_assessment.criterion_label}</strong>. Nhấp nút bên dưới để mở
                    Quote Drawer và đối chiếu văn bản gốc:
                  </p>
                  <div
                    style={{
                      background: "#1e293b",
                      border: "1px solid #475569",
                      padding: "1rem",
                      borderRadius: "0.375rem",
                      marginBottom: "1.5rem",
                    }}
                  >
                    <div style={{ fontSize: "0.8rem", color: "#94a3b8", marginBottom: "0.5rem" }}>
                      Đoạn trích AI đính kèm:
                    </div>
                    <blockquote
                      style={{
                        margin: 0,
                        borderLeft: "3px solid #38bdf8",
                        paddingLeft: "0.75rem",
                        color: "#f1f5f9",
                        fontSize: "0.9rem",
                        fontStyle: "italic",
                      }}
                    >
                      "{currentScenario.ai_preliminary_assessment.evidence_quote}"
                    </blockquote>
                    <div style={{ marginTop: "0.75rem", fontSize: "0.75rem", color: "#64748b", fontFamily: "monospace" }}>
                      Span ID: {currentScenario.ai_preliminary_assessment.span_id}
                    </div>
                  </div>

                  <button
                    onClick={() => setIsQuoteDrawerOpen(true)}
                    style={{
                      width: "100%",
                      padding: "0.75rem",
                      background: "#0284c7",
                      color: "#fff",
                      border: "none",
                      borderRadius: "0.375rem",
                      fontWeight: 600,
                      cursor: "pointer",
                      marginBottom: "1rem",
                    }}
                  >
                    Mở Quote Drawer Đối Chiếu Bằng Chứng Gốc
                  </button>

                  {isQuoteDrawerOpen && (
                    <div
                      style={{
                        background: "#020617",
                        border: "1px solid #38bdf8",
                        borderRadius: "0.375rem",
                        padding: "1rem",
                        marginTop: "1rem",
                      }}
                    >
                      <h4 style={{ color: "#38bdf8", fontSize: "0.9rem", marginBottom: "0.5rem" }}>
                        Quote Drawer: Bằng Chứng Nguồn Xác Thực
                      </h4>
                      <div style={{ fontSize: "0.85rem", color: "#cbd5e1", lineHeight: 1.5, marginBottom: "0.75rem" }}>
                        <strong>Đoạn trích CV gốc:</strong> {currentScenario.ai_preliminary_assessment.evidence_quote}
                      </div>
                      <div style={{ fontSize: "0.75rem", color: "#94a3b8", fontFamily: "monospace", marginBottom: "1rem" }}>
                        Mã băm bảo toàn: {currentScenario.ai_preliminary_assessment.provenance_hash}
                      </div>
                      <button
                        onClick={() => {
                          setIsQuoteDrawerOpen(false);
                          completeStep("step_1_inspect_source", { verified: true });
                        }}
                        style={{
                          padding: "0.5rem 1rem",
                          background: "#10b981",
                          color: "#fff",
                          border: "none",
                          borderRadius: "0.25rem",
                          fontWeight: 600,
                          cursor: "pointer",
                        }}
                      >
                        Xác Nhận Bằng Chứng Đúng & Hoàn Thành Bước 1
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* SCENARIO 2: Missing Evidence */}
              {activeStepIndex === 1 && (
                <div>
                  <p style={{ color: "#94a3b8", fontSize: "0.875rem", marginBottom: "1rem" }}>
                    Ứng viên có kỹ năng Bảo mật nhưng AI phát hiện thiếu số liệu thực thi trong dự án thực tế:
                  </p>
                  <div
                    style={{
                      background: "#451a03",
                      border: "1px solid #b45309",
                      padding: "1rem",
                      borderRadius: "0.375rem",
                      marginBottom: "1.5rem",
                    }}
                  >
                    <div style={{ color: "#fde047", fontWeight: 600, fontSize: "0.9rem", marginBottom: "0.5rem" }}>
                      Cờ Cảnh Báo: Thiếu Thông Tin Chứng Minh
                    </div>
                    <ul style={{ margin: 0, paddingLeft: "1.25rem", color: "#fef08a", fontSize: "0.85rem" }}>
                      {currentScenario.ai_preliminary_assessment.missing_info.map((m: string, i: number) => (
                        <li key={i}>{m}</li>
                      ))}
                    </ul>
                  </div>

                  <p style={{ color: "#cbd5e1", fontSize: "0.875rem", marginBottom: "1rem" }}>
                    Nguyên tắc: Không suy diễn! Với các tiêu chí thiếu bằng chứng, hệ thống gợi ý chuyển sang Ngân Hàng Câu
                    Hỏi Phỏng Vấn Kỹ Thuật để đào sâu.
                  </p>

                  <button
                    onClick={() =>
                      completeStep("step_2_missing_evidence", {
                        action: "flagged_for_interview",
                        missing_count: currentScenario.ai_preliminary_assessment.missing_info.length,
                      })
                    }
                    style={{
                      width: "100%",
                      padding: "0.75rem",
                      background: "#d97706",
                      color: "#fff",
                      border: "none",
                      borderRadius: "0.375rem",
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
                  >
                    Gắn Cờ & Chuyển Thành Câu Hỏi Phỏng Vấn (Hoàn Thành Bước 2)
                  </button>
                </div>
              )}

              {/* SCENARIO 3: HR Override */}
              {activeStepIndex === 2 && (
                <div>
                  <p style={{ color: "#94a3b8", fontSize: "0.875rem", marginBottom: "1rem" }}>
                    Điểm sơ bộ AI hiện tại: <strong>1/4</strong>. Bạn đang xem xét năng lực thiết kế API gRPC/Protobuf của ứng
                    viên và muốn điều chỉnh lên mức thành thạo:
                  </p>
                  <div style={{ marginBottom: "1rem" }}>
                    <label style={{ display: "block", fontSize: "0.85rem", color: "#cbd5e1", marginBottom: "0.35rem" }}>
                      Chọn Điểm Số Mới (0 - 4):
                    </label>
                    <select
                      value={overrideScore}
                      onChange={(e) => setOverrideScore(Number(e.target.value))}
                      style={{
                        width: "100%",
                        padding: "0.5rem",
                        background: "#1e293b",
                        border: "1px solid #475569",
                        color: "#fff",
                        borderRadius: "0.375rem",
                      }}
                    >
                      <option value={0}>0 - Chưa có bằng chứng</option>
                      <option value={1}>1 - Nhận biết cơ bản</option>
                      <option value={2}>2 - Áp dụng được dưới hướng dẫn</option>
                      <option value={3}>3 - Thành thạo độc lập (Đề xuất)</option>
                      <option value={4}>4 - Chuyên gia / Tối ưu nâng cao</option>
                    </select>
                  </div>

                  <div style={{ marginBottom: "1.5rem" }}>
                    <label style={{ display: "block", fontSize: "0.85rem", color: "#cbd5e1", marginBottom: "0.35rem" }}>
                      Lý Do Ghi Đè (Bắt buộc, tối thiểu 10 ký tự, cấm thuộc tính nhân khẩu học):
                    </label>
                    <textarea
                      rows={3}
                      value={overrideReason}
                      onChange={(e) => setOverrideReason(e.target.value)}
                      placeholder="Ví dụ: Ứng viên có kinh nghiệm thực tế thiết kế hạ tầng RPC phân tán với Protobuf đạt chuẩn hiệu năng cao..."
                      style={{
                        width: "100%",
                        padding: "0.5rem",
                        background: "#1e293b",
                        border: "1px solid #475569",
                        color: "#fff",
                        borderRadius: "0.375rem",
                        fontSize: "0.85rem",
                      }}
                    />
                  </div>

                  <button
                    onClick={() => {
                      if (overrideReason.trim().length < 10) {
                        alert("Vui lòng nhập lý do ghi đè chi tiết tối thiểu 10 ký tự.");
                        return;
                      }
                      completeStep("step_3_hr_override", {
                        new_score: overrideScore,
                        reason: overrideReason,
                      });
                    }}
                    style={{
                      width: "100%",
                      padding: "0.75rem",
                      background: "#3b82f6",
                      color: "#fff",
                      border: "none",
                      borderRadius: "0.375rem",
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
                  >
                    Ghi Đè & Tính Lại Điểm Chuẩn Hóa (Hoàn Thành Bước 3)
                  </button>
                </div>
              )}

              {/* SCENARIO 4: Attested Decision */}
              {activeStepIndex === 3 && (
                <div>
                  <p style={{ color: "#94a3b8", fontSize: "0.875rem", marginBottom: "1rem" }}>
                    Hồ sơ sau khi tổng hợp đạt <strong>78.5/100</strong> (Vượt ngưỡng 70, thỏa mãn sàn điểm cốt lõi). Hãy ký
                    ReviewAttestation và phê duyệt quyết định:
                  </p>

                  <div
                    style={{
                      background: "#1e293b",
                      border: "1px solid #334155",
                      padding: "1rem",
                      borderRadius: "0.375rem",
                      marginBottom: "1rem",
                    }}
                  >
                    <label style={{ display: "flex", alignItems: "flex-start", gap: "0.75rem", cursor: "pointer" }}>
                      <input
                        type="checkbox"
                        checked={attestationAccepted}
                        onChange={(e) => setAttestationAccepted(e.target.checked)}
                        style={{ marginTop: "0.25rem" }}
                      />
                      <span style={{ fontSize: "0.85rem", color: "#e2e8f0", lineHeight: 1.4 }}>
                        Tôi xác nhận (ReviewAttestation) đã trực tiếp xem xét toàn bộ các đoạn trích bằng chứng, không đưa ra
                        quyết định dựa trên bất kỳ thuộc tính phân biệt đối xử nào, và chịu trách nhiệm với tư cách Requisition
                        Owner.
                      </span>
                    </label>
                  </div>

                  <div style={{ marginBottom: "1.5rem" }}>
                    <label style={{ display: "block", fontSize: "0.85rem", color: "#cbd5e1", marginBottom: "0.35rem" }}>
                      Quyết định tuyển dụng:
                    </label>
                    <select
                      value={selectedOutcome}
                      onChange={(e) => setSelectedOutcome(e.target.value)}
                      style={{
                        width: "100%",
                        padding: "0.5rem",
                        background: "#1e293b",
                        border: "1px solid #475569",
                        color: "#fff",
                        borderRadius: "0.375rem",
                      }}
                    >
                      <option value="advance">Chuyển tiếp phỏng vấn kỹ thuật (Advance)</option>
                      <option value="request_information">Yêu cầu bổ sung thông tin (Clarification)</option>
                      <option value="not_advance">Không chuyển tiếp (Not Advance)</option>
                    </select>
                  </div>

                  <button
                    disabled={!attestationAccepted}
                    onClick={() => {
                      completeStep("step_4_attested_decision", {
                        outcome: selectedOutcome,
                        attestation_signed: true,
                      });
                    }}
                    style={{
                      width: "100%",
                      padding: "0.75rem",
                      background: attestationAccepted ? "#10b981" : "#475569",
                      color: "#fff",
                      border: "none",
                      borderRadius: "0.375rem",
                      fontWeight: 600,
                      cursor: attestationAccepted ? "pointer" : "not-allowed",
                    }}
                  >
                    Ký Số & Lưu Quyết Định Bất Biến (Hoàn Thành Bước 4)
                  </button>
                </div>
              )}

              {/* SCENARIO 5: Audit Trail */}
              {activeStepIndex === 4 && (
                <div>
                  <p style={{ color: "#94a3b8", fontSize: "0.875rem", marginBottom: "1rem" }}>
                    Nhật ký kiểm toán ghi nhận mọi thay đổi theo thứ tự thời gian với mã băm bảo toàn tính toàn vẹn:
                  </p>

                  <div
                    style={{
                      background: "#020617",
                      border: "1px solid #334155",
                      borderRadius: "0.375rem",
                      padding: "0.75rem",
                      marginBottom: "1.5rem",
                      fontFamily: "monospace",
                      fontSize: "0.8rem",
                      color: "#94a3b8",
                      lineHeight: 1.6,
                    }}
                  >
                    <div>[2026-09-26T08:00:00Z] INTAKE_RECEIVED: CAND-SANDBOX-05 (Hash: a8f9...31c)</div>
                    <div>[2026-09-26T08:00:05Z] SANITIZATION_APPROVED: PII Stripped, 0 contact leaked</div>
                    <div>[2026-09-26T08:01:20Z] AI_ASSESSMENT_RUN: 6 criteria evaluated</div>
                    <div>[2026-09-26T08:05:42Z] HR_REVISION_LOGGED: Criteria sql_data modified by Owner</div>
                    <div>[2026-09-26T08:07:15Z] ATTESTATION_SIGNED: Signed by Owner (Signature valid)</div>
                  </div>

                  <div
                    style={{
                      background: "rgba(56, 189, 248, 0.1)",
                      border: "1px solid #0284c7",
                      padding: "0.75rem",
                      borderRadius: "0.375rem",
                      color: "#7dd3fc",
                      fontSize: "0.85rem",
                      marginBottom: "1.5rem",
                    }}
                  >
                    ✓ Cam kết bảo mật: Zero Demographic Attributes, Không lưu PII trong Audit Log, Chuỗi sự kiện bất biến.
                  </div>

                  <button
                    onClick={() => {
                      completeStep("step_5_audit_trail", {
                        audit_verified: true,
                        tamper_evident_checked: true,
                      });
                    }}
                    style={{
                      width: "100%",
                      padding: "0.75rem",
                      background: "#6366f1",
                      color: "#fff",
                      border: "none",
                      borderRadius: "0.375rem",
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
                  >
                    Xác Nhận Tính Toàn Vẹn Kiểm Toán & Hoàn Tất Huấn Luyện (Bước 5)
                  </button>
                </div>
              )}
            </div>

            {/* Bottom Status Card */}
            {isAllCompleted && (
              <div
                style={{
                  marginTop: "1.5rem",
                  background: "rgba(16, 185, 129, 0.15)",
                  border: "1px solid #10b981",
                  borderRadius: "0.5rem",
                  padding: "1rem",
                  textAlign: "center",
                }}
              >
                <div style={{ color: "#34d399", fontWeight: 700, fontSize: "1rem", marginBottom: "0.25rem" }}>
                  🎉 CHÚC MỪNG: BẠN ĐÃ HOÀN TẤT HUẤN LUYỆN HR ONBOARDING!
                </div>
                <div style={{ color: "#cbd5e1", fontSize: "0.85rem" }}>
                  Bạn đã nắm vững toàn bộ 5 nguyên tắc bất biến của hệ thống TalentScreen AI. Sẵn sàng tham gia thẩm định
                  đợt tuyển dụng chính thức.
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
