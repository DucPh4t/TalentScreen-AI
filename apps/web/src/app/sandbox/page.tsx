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

const FALLBACK_SCENARIOS: Scenario[] = [
  {
    id: "scenario_1_evidence_inspection",
    title: "Tình huống 1: Mở Bằng Chứng & Kiểm Tra Trích Dẫn",
    category: "evidence_provenance",
    learning_objective: "Hiểu nguyên tắc trích xuất bằng chứng: Tuyệt đối không tin tưởng điểm số tổng quan mà phải nhấp mở từng SourceSpan trong Quote Drawer để đối chiếu văn bản gốc.",
    description: "Ứng viên có trích dẫn về tối ưu hóa cơ sở dữ liệu PostgreSQL. Bạn cần kiểm tra xem đoạn trích dẫn có đúng vị trí và ngữ cảnh thực tế trong CV hay không.",
    candidate_profile: {
      public_label: "SANDBOX-CAND-01",
      experience_summary: "4 năm phát triển Backend Python, cơ sở dữ liệu phân tán.",
      skills: ["Python", "FastAPI", "PostgreSQL", "Docker"],
    },
    ai_preliminary_assessment: {
      criterion_id: "sql_data",
      criterion_label: "Cơ Sở Dữ Liệu & Tối Ưu Hóa SQL",
      ai_score: 3,
      evidence_quote: "Đã thực hiện thiết kế schema và đánh chỉ mục B-tree/GIN giúp giảm thời gian truy vấn báo cáo từ 4.2s xuống 180ms trên cụm PostgreSQL 100GB.",
      span_id: "spn_sandbox_01_sql",
      provenance_hash: "sha256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
      missing_info: [],
    },
    instructions: [
      "1. Nhấp vào trích dẫn bằng chứng của tiêu chí sql_data.",
      "2. Đọc đối chiếu đoạn trích trong Quote Drawer để xác thực metrics '180ms' và 'PostgreSQL 100GB'.",
      "3. Xác nhận bằng chứng hợp lệ và đánh dấu hoàn thành bước 1.",
    ],
  },
  {
    id: "scenario_2_missing_evidence",
    title: "Tình huống 2: Nhận Diện Thiếu Thông Tin & Bằng Chứng Yếu",
    category: "missing_information",
    learning_objective: "Học cách phát hiện các nhận định chung chung trong CV thiếu số liệu đo lường, không tự suy diễn năng lực khi CV không có căn cứ.",
    description: "Ứng viên ghi kỹ năng 'Bảo mật & Phân quyền', nhưng nội dung CV chỉ có danh sách gạch đầu dòng liệt kê từ khóa mà không có dự án chứng minh.",
    candidate_profile: {
      public_label: "SANDBOX-CAND-02",
      experience_summary: "3 năm lập trình viên Fullstack, tham gia nhiều dự án gia công phần mềm.",
      skills: ["JavaScript", "Python", "OAuth2", "Security"],
    },
    ai_preliminary_assessment: {
      criterion_id: "security_privacy",
      criterion_label: "Bảo Mật & Quyền Riêng Tư",
      ai_score: 1,
      evidence_quote: "Hiểu biết về bảo mật hệ thống và OWASP Top 10.",
      span_id: "spn_sandbox_02_sec",
      provenance_hash: "sha256:2c624232cdd221771294dfbb310aca000a0df6ec8b660466192ac11425b4fa66",
      missing_info: [
        "Không có bằng chứng triển khai cơ chế xác thực JWT, RBAC hoặc mã hóa dữ liệu trong thực tế.",
        "Chưa nêu phương pháp phòng ngừa SQL Injection hoặc XSS ngoài việc liệt kê từ khóa OWASP.",
      ],
    },
    instructions: [
      "1. Đọc cờ cảnh báo 'Thiếu thông tin chứng minh' do hệ thống gắn.",
      "2. Kiểm tra danh sách thiếu thông tin để chuẩn bị câu hỏi phỏng vấn kỹ thuật tương ứng.",
      "3. Đánh dấu hoàn thành bước 2.",
    ],
  },
  {
    id: "scenario_3_hr_override",
    title: "Tình huống 3: Ghi Đè Đánh Giá (HR Revision Override)",
    category: "human_override",
    learning_objective: "Thực hành quyền can thiệp của con người: Khi phát hiện AI đánh giá khắt khe hoặc bỏ sót dự án mã nguồn mở uy tín, HR điều chỉnh điểm và ghi rõ lý do bắt buộc.",
    description: "AI chỉ chấm 1/4 cho tiêu chí API Design vì CV dùng từ 'Microservices RPC nội bộ', nhưng HR qua phỏng vấn sơ bộ biết ứng viên là maintainer của một framework mã nguồn mở.",
    candidate_profile: {
      public_label: "SANDBOX-CAND-03",
      experience_summary: "5 năm chuyên sâu kiến trúc hệ thống phân tán và protocol thiết kế.",
      skills: ["Python", "gRPC", "Protobuf", "FastAPI"],
    },
    ai_preliminary_assessment: {
      criterion_id: "api_design",
      criterion_label: "Thiết Kế API & Chuẩn Hóa",
      ai_score: 1,
      evidence_quote: "Xây dựng microservices giao tiếp qua gRPC và Protobuf.",
      span_id: "spn_sandbox_03_api",
      provenance_hash: "sha256:4813494d137e1631bba301d5acab6e7bb7aa74ce1185d456565ef51d737677b2",
      missing_info: ["CV không đề cập REST OpenAPI spec."],
    },
    instructions: [
      "1. Nhập điểm mới điều chỉnh: 3 (Thành thạo kiến trúc API gRPC/Protobuf hiệu năng cao).",
      "2. Nhập lý do ghi đè bắt buộc (tối thiểu 10 ký tự, không chứa thuộc tính nhân khẩu học).",
      "3. Bấm 'Ghi Đè & Tính Lại Điểm' để xác thực điểm số chuẩn hóa cập nhật tự động.",
    ],
  },
  {
    id: "scenario_4_attested_decision",
    title: "Tình huống 4: Ký Xác Nhận Attestation & Ra Quyết Định",
    category: "attested_decision",
    learning_objective: "Quy trình bất biến: AI không bao giờ được tự động ra quyết định tuyển dụng. Chỉ Requisition Owner mới có quyền ký ReviewAttestation và phê duyệt 'advance'.",
    description: "Hồ sơ đạt ngưỡng 78.5/100, đủ điều kiện tiến vào vòng phỏng vấn kỹ thuật. Bạn sẽ thực hiện ký attestation với bằng chứng số và chốt quyết định.",
    candidate_profile: {
      public_label: "SANDBOX-CAND-04",
      experience_summary: "Senior Python Developer đạt chuẩn yêu cầu công việc.",
      skills: ["Python", "FastAPI", "PostgreSQL", "CI/CD"],
    },
    ai_preliminary_assessment: {
      overall_comparable_score: 78.5,
      core_floor_passed: true,
      coverage_pct: 100.0,
      recommendation: "advance",
    },
    instructions: [
      "1. Đọc biên bản cam kết thẩm định (ReviewAttestation) và snapshot hash.",
      "2. Chọn quyết định tuyển dụng: 'advance' (Chuyển sang phỏng vấn kỹ thuật).",
      "3. Ký số điện tử và lưu quyết định bất biến.",
    ],
  },
  {
    id: "scenario_5_audit_trail",
    title: "Tình huống 5: Kiểm Tra Dấu Vết Kiểm Toán (Audit Trail)",
    category: "audit_trace",
    learning_objective: "Đảm bảo tính giải trình và minh bạch: Mọi thao tác xem, sửa, phê duyệt đều được ghi nhận vào sổ cái kiểm toán bất biến với timestamp UTC và actor ID.",
    description: "Xem lại toàn bộ lịch sử chuỗi sự kiện kiểm toán từ lúc tiếp nhận hồ sơ, làm sạch PII, chạy AI, HR ghi đè đến khi ký quyết định cuối cùng.",
    candidate_profile: {
      public_label: "SANDBOX-CAND-05",
      experience_summary: "Hồ sơ đã hoàn tất toàn bộ chu trình đánh giá.",
      skills: ["Python", "Docker"],
    },
    ai_preliminary_assessment: {
      audit_events_count: 5,
      tamper_evident: true,
    },
    instructions: [
      "1. Xem dòng thời gian kiểm toán và xác nhận mã băm bảo toàn chuỗi.",
      "2. Kiểm tra cam kết bảo mật không rò rỉ PII trong log kiểm toán.",
      "3. Hoàn tất toàn bộ khóa huấn luyện Sandbox Onboarding.",
    ],
  },
];

export default function SandboxPage() {
  const [scenarios, setScenarios] = useState<Scenario[]>(FALLBACK_SCENARIOS);
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
        api.getSandboxScenarios().catch(() => FALLBACK_SCENARIOS),
        api.getOnboardingStatus().catch(() => ({
          completed_steps: {},
          is_completed: false,
          remaining_steps: stepKeys,
        })),
      ]);
      setScenarios(scenariosData?.length ? scenariosData : FALLBACK_SCENARIOS);
      setOnboardingStatus(statusData);

      // Set active step to first incomplete step
      const completed = statusData.completed_steps || {};
      const firstIncomplete = stepKeys.findIndex((k) => !completed[k]);
      if (firstIncomplete >= 0) {
        setActiveStepIndex(firstIncomplete);
      }
    } catch (err: any) {
      console.warn("Fallback to offline sandbox simulation:", err);
      setScenarios(FALLBACK_SCENARIOS);
      setOnboardingStatus({
        completed_steps: {},
        is_completed: false,
        remaining_steps: stepKeys,
      });
    } finally {
      setLoading(false);
    }
  }

  async function completeStep(stepId: string, resultData: any) {
    try {
      const updated = await api.completeOnboardingStep(stepId, resultData);
      setOnboardingStatus(updated);
    } catch {
      // Local fallback for offline/sandbox mode
      setOnboardingStatus((prev: any) => {
        const steps = { ...(prev?.completed_steps || {}) };
        steps[stepId] = { completed: true, completed_at: new Date().toISOString() };
        const remaining = stepKeys.filter((k) => !steps[k]);
        return {
          ...prev,
          completed_steps: steps,
          is_completed: remaining.length === 0,
          remaining_steps: remaining,
        };
      });
    }
    setActionMessage(`Đã hoàn thành bước: ${stepId}`);
    if (activeStepIndex < 4) {
      setActiveStepIndex(activeStepIndex + 1);
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
