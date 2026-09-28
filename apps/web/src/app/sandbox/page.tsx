"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import {
  IconSparkles,
  IconShield,
  IconCheckCircle,
  IconAlertTriangle,
  IconQuote,
  IconLock,
  IconRefresh,
  IconArrowRight,
  IconUserCheck,
  IconSliders,
  IconFileText,
  IconMessageSquare,
  IconX
} from "@/components/Icons";
import { useToast } from "@/components/Toast";
import { SkeletonDossier } from "@/components/Skeleton";

interface Scenario {
  id: string;
  title: string;
  category: string;
  learning_objective: string;
  description: string;
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
      recommendation: "consider_next_round",
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
  const { success, error: toastError, warning } = useToast();
  const [scenarios, setScenarios] = useState<Scenario[]>(FALLBACK_SCENARIOS);
  const [onboardingStatus, setOnboardingStatus] = useState<any>(null);
  const [activeStepIndex, setActiveStepIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [serverAvailable, setServerAvailable] = useState(false);

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
      const statusData = await api.getOnboardingStatus();
      const scenariosData = await api.getSandboxScenarios().catch(() => FALLBACK_SCENARIOS);
      setServerAvailable(true);
      setScenarios(scenariosData?.length ? scenariosData : FALLBACK_SCENARIOS);
      setOnboardingStatus(statusData);

      const completed = statusData?.completed_steps || {};
      const firstIncomplete = stepKeys.findIndex((k) => !completed[k]);
      if (firstIncomplete >= 0) {
        setActiveStepIndex(firstIncomplete);
      }
    } catch (err: any) {
      console.warn("Sandbox server unavailable; showing read-only examples:", err);
      setServerAvailable(false);
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
    if (!serverAvailable) {
      setActionMessage("Chưa kết nối backend. Bạn có thể xem ví dụ, nhưng tiến độ huấn luyện chưa được ghi nhận.");
      return;
    }
    try {
      const updated = await api.completeOnboardingStep(stepId, resultData);
      setOnboardingStatus(updated);
    } catch (err: any) {
      setActionMessage(`Không lưu được tiến độ: ${err.message || String(err)}. Vui lòng thử lại.`);
      return;
    }
    setActionMessage(`Đã hoàn thành xuất sắc bước: ${stepId}`);
    if (activeStepIndex < 4) {
      setActiveStepIndex(activeStepIndex + 1);
    }
  }

  async function handleReset() {
    try {
      const resetData = await api.resetOnboarding();
      setOnboardingStatus(resetData);
      setActiveStepIndex(0);
      setActionMessage("Đã đặt lại tiến độ huấn luyện Sandbox.");
      success("Đã đặt lại tiến độ huấn luyện Sandbox.");
    } catch (err: any) {
      toastError(err.message || "Lỗi đặt lại tiến độ");
    }
  }

  if (loading) {
    return <SkeletonDossier />;
  }

  const currentScenario = scenarios[activeStepIndex];
  const completedSteps = onboardingStatus?.completed_steps || {};
  const isAllCompleted = onboardingStatus?.is_completed || false;
  const actionMessageIsError = Boolean(actionMessage && (actionMessage.startsWith("Chưa") || actionMessage.startsWith("Không lưu")));

  return (
    <div>
      {/* Top Header & Isolation Banner */}
      <div className="page-header">
        <div>
          <div className="breadcrumbs">
            <Link href="/">Trang chủ</Link>
            <span>/</span>
            <span style={{ color: "var(--text-primary)" }}>Sandbox Huấn Luyện HR</span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
            <h1 className="page-title">Sandbox Huấn Luyện &amp; Mô Phỏng HR</h1>
            <span className="badge badge-open">
              <IconLock size={12} color="#34d399" />
              <span>ISOLATED SANDBOX</span>
            </span>
          </div>

          <p className="page-subtitle">
            Tình huống mẫu để HR luyện đối chiếu bằng chứng, ghi nhận thông tin còn thiếu, ghi đè có lý do và xác nhận quyết định. Không dùng hồ sơ thật trong phần tập huấn này.
          </p>
        </div>

        <button onClick={handleReset} className="btn btn-secondary btn-sm">
          <IconRefresh size={14} />
          <span>Làm Lại Từ Đầu</span>
        </button>
      </div>

      {!serverAvailable && (
        <div role="status" style={{ background: "#78350f", color: "#fef3c7", padding: "0.75rem 1rem", borderRadius: "0.375rem", marginBottom: "1rem" }}>
          Chế độ xem ví dụ offline: chưa ghi nhận hoàn thành onboarding. Kết nối backend và đăng nhập để lưu tiến độ.
        </div>
      )}

      {actionMessage && (
        <div style={{
          backgroundColor: actionMessageIsError ? "#78350f" : "var(--emerald-bg)",
          color: actionMessageIsError ? "#fef3c7" : "var(--emerald-text)",
          border: actionMessageIsError ? "1px solid #f59e0b" : "1px solid var(--emerald-border)",
          padding: "0.85rem 1.25rem",
          borderRadius: "var(--radius-sm)",
          marginBottom: "1.5rem",
          fontSize: "0.875rem",
          display: "flex",
          alignItems: "center",
          gap: "0.5rem"
        }}>
          {actionMessageIsError ? <IconAlertTriangle size={16} color="#fef3c7" /> : <IconCheckCircle size={16} color="var(--emerald-text)" />}
          <span>{actionMessage}</span>
        </div>
      )}

      {/* Stepper Navigation Bar */}
      <div className="stepper-nav">
        {scenarios.map((sc, idx) => {
          const stepKey = stepKeys[idx];
          const isDone = !!completedSteps[stepKey];
          const isActive = idx === activeStepIndex;

          return (
            <div
              key={sc.id}
              onClick={() => setActiveStepIndex(idx)}
              className={`stepper-step ${isActive ? "active" : ""} ${isDone ? "completed" : ""}`}
            >
              <div className="stepper-num">
                {isDone ? "✓" : idx + 1}
              </div>
              <div>
                <div style={{ fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.05em", color: isActive ? "var(--accent-cyan)" : "var(--text-muted)" }}>
                  Bước {idx + 1}
                </div>
                <div style={{ fontSize: "0.85rem", fontWeight: 700, color: isActive ? "var(--accent-blue)" : isDone ? "var(--emerald-text)" : "var(--text-secondary)" }}>
                  {sc.title.split(": ")[1] || sc.title}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Main Practice Workspace (2 Columns) */}
      {currentScenario && (
        <div className="sandbox-workspace-grid">
          {/* Left Column: Learning Objective & Candidate Mock */}
          <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            <div className="card">
              <div style={{ display: "flex", alignItems: "center", gap: "0.45rem", marginBottom: "0.75rem" }}>
                <span className="badge badge-subtle" style={{ color: "var(--accent-cyan)" }}>
                  MỤC TIÊU HUẤN LUYỆN #{activeStepIndex + 1}
                </span>
              </div>
              <p style={{ color: "var(--text-primary)", fontSize: "0.95rem", lineHeight: 1.6, fontWeight: 500 }}>
                {currentScenario.learning_objective}
              </p>

              <div style={{ marginTop: "1.25rem", borderTop: "1px solid var(--border-subtle)", paddingTop: "1rem" }}>
                <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 700 }}>
                  Bối Cảnh Tình Huống Giả Lập
                </div>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginTop: "0.35rem", lineHeight: 1.6 }}>
                  {currentScenario.description}
                </p>
              </div>
            </div>

            {/* Candidate Mock Data */}
            <div className="card">
              <div className="card-header">
                <h3 className="card-title" style={{ fontSize: "1rem" }}>
                  Hồ Sơ Giả Lập:{" "}
                  <span style={{ color: "var(--accent-cyan)", fontFamily: "var(--font-mono)" }}>
                    {currentScenario.candidate_profile.public_label}
                  </span>
                </h3>
                <span className="badge badge-open" style={{ fontSize: "0.7rem" }}>
                  MẪU THỬ
                </span>
              </div>
              <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", marginBottom: "1rem", lineHeight: 1.5 }}>
                {currentScenario.candidate_profile.experience_summary}
              </p>
              <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}>
                {currentScenario.candidate_profile.skills.map((s) => (
                  <span key={s} className="badge badge-subtle" style={{ fontSize: "0.75rem" }}>
                    {s}
                  </span>
                ))}
              </div>
            </div>

            {/* Instructions checklist */}
            <div className="card">
              <h4 style={{ fontSize: "0.9rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <IconCheckCircle size={15} color="#38bdf8" />
                <span>Các Thao Tác Cần Thực Hiện:</span>
              </h4>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {currentScenario.instructions.map((inst, i) => (
                  <div key={i} style={{ fontSize: "0.825rem", color: "var(--text-secondary)", display: "flex", alignItems: "flex-start", gap: "0.4rem", lineHeight: 1.5 }}>
                    <span style={{ color: "var(--accent-cyan)", fontWeight: 700 }}>•</span>
                    <span>{inst}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right Column: Interactive Practice Station */}
          <div className="card" style={{ border: "1px solid var(--border-medium)" }}>
            <div className="card-header">
              <div>
                <h3 className="card-title">Khu Vực Thao Tác Thực Hành</h3>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.8rem", marginTop: "0.2rem" }}>
                  Tình huống {activeStepIndex + 1} / 5: {currentScenario.title.split(": ")[1]}
                </p>
              </div>
              <span className="badge badge-subtle" style={{ fontFamily: "var(--font-mono)" }}>
                Step {activeStepIndex + 1}/5
              </span>
            </div>

            {/* SCENARIO 1: Inspect Source Quote */}
            {activeStepIndex === 0 && (
              <div>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginBottom: "1rem", lineHeight: 1.6 }}>
                  AI ghi nhận bằng chứng sơ bộ cho tiêu chí: <strong style={{ color: "var(--text-primary)" }}>{currentScenario.ai_preliminary_assessment.criterion_label}</strong>. Mở trích dẫn để đối chiếu với văn bản mẫu:
                </p>

                <div className="evidence-quote-box" style={{ marginBottom: "1.25rem" }}>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.3rem" }}>
                    Đoạn trích bằng chứng do AI phát hiện:
                  </div>
                  <div style={{ fontStyle: "italic", color: "var(--text-primary)", fontSize: "0.875rem" }}>
                    &ldquo;{currentScenario.ai_preliminary_assessment.evidence_quote}&rdquo;
                  </div>
                  <div style={{ marginTop: "0.5rem", fontSize: "0.72rem", color: "var(--accent-cyan)", fontFamily: "var(--font-mono)" }}>
                    Span ID: {currentScenario.ai_preliminary_assessment.span_id}
                  </div>
                </div>

                <button
                  onClick={() => setIsQuoteDrawerOpen(true)}
                  className="btn btn-primary"
                  style={{ width: "100%", marginBottom: "1rem" }}
                >
                  <IconQuote size={16} />
                  <span>Mở Quote Drawer Đối Chiếu Bằng Chứng Gốc</span>
                </button>

                {isQuoteDrawerOpen && (
                  <div style={{
                    background: "rgba(11, 15, 25, 0.95)",
                    border: "1px solid var(--accent-cyan)",
                    borderRadius: "var(--radius-md)",
                    padding: "1.25rem",
                    marginTop: "1rem",
                    animation: "fade-in 0.2s ease"
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                      <h4 style={{ color: "var(--accent-cyan)", fontSize: "0.95rem", fontWeight: 700 }}>
                        Quote Drawer: Bằng Chứng Nguồn Xác Thực
                      </h4>
                      <button onClick={() => setIsQuoteDrawerOpen(false)} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer" }}>
                        <IconX size={16} />
                      </button>
                    </div>

                    <div style={{ fontSize: "0.875rem", color: "#cbd5e1", lineHeight: 1.6, marginBottom: "0.75rem", fontFamily: "var(--font-mono)" }}>
                      <strong>Văn bản CV gốc:</strong> {currentScenario.ai_preliminary_assessment.evidence_quote}
                    </div>

                    <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)", marginBottom: "1.25rem", wordBreak: "break-all" }}>
                      Mã băm bảo toàn chuỗi: {currentScenario.ai_preliminary_assessment.provenance_hash}
                    </div>

                    <button
                      onClick={() => {
                        setIsQuoteDrawerOpen(false);
                        completeStep("step_1_inspect_source", { verified: true });
                      }}
                      className="btn btn-primary"
                      style={{ background: "#10b981", borderColor: "#10b981", width: "100%" }}
                    >
                      <IconCheckCircle size={16} />
                      <span>Xác Nhận Bằng Chứng Đúng &amp; Hoàn Thành Bước 1</span>
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* SCENARIO 2: Missing Evidence */}
            {activeStepIndex === 1 && (
              <div>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginBottom: "1.25rem", lineHeight: 1.6 }}>
                  Ứng viên ghi kỹ năng Bảo Mật nhưng AI phát hiện hồ sơ thiếu bằng chứng định lượng trong môi trường thực tế:
                </p>

                <div style={{
                  background: "var(--amber-bg)",
                  border: "1px solid var(--amber-border)",
                  padding: "1.15rem",
                  borderRadius: "var(--radius-md)",
                  marginBottom: "1.5rem"
                }}>
                  <div style={{ color: "var(--amber-text)", fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                    <IconAlertTriangle size={16} color="var(--amber-text)" />
                    <span>Cờ Cảnh Báo: Thiếu Thông Tin Chứng Minh</span>
                  </div>
                  <ul style={{ margin: 0, paddingLeft: "1.25rem", color: "var(--amber-text)", fontSize: "0.825rem", lineHeight: 1.6 }}>
                    {currentScenario.ai_preliminary_assessment.missing_info.map((m: string, i: number) => (
                      <li key={i}>{m}</li>
                    ))}
                  </ul>
                </div>

                <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginBottom: "1.25rem", lineHeight: 1.6 }}>
                  <strong style={{ color: "var(--text-primary)" }}>Nguyên tắc:</strong> Không tự suy diễn. Chuyển phần thiếu bằng chứng thành câu hỏi phỏng vấn để ứng viên làm rõ.
                </p>

                <button
                  onClick={() =>
                    completeStep("step_2_missing_evidence", {
                      action: "flagged_for_interview",
                      missing_count: currentScenario.ai_preliminary_assessment.missing_info.length,
                    })
                  }
                  className="btn btn-primary"
                  style={{ width: "100%", background: "#d97706", borderColor: "#d97706" }}
                >
                  <IconMessageSquare size={16} />
                  <span>Gắn Cờ &amp; Chuyển Thành Câu Hỏi Phỏng Vấn (Hoàn Thành Bước 2)</span>
                </button>
              </div>
            )}

            {/* SCENARIO 3: HR Override */}
            {activeStepIndex === 2 && (
              <div>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginBottom: "1.25rem", lineHeight: 1.6 }}>
                  Điểm AI sơ bộ: <strong style={{ color: "var(--amber-text)" }}>1/4</strong>. Qua phỏng vấn sơ bộ, bạn biết ứng viên là maintainer của thư viện gRPC mã nguồn mở và muốn điều chỉnh lên mức thành thạo:
                </p>

                <div className="form-group">
                  <label className="form-label">Chọn Điểm Số Mới (0 - 4)</label>
                  <select
                    className="form-select"
                    value={overrideScore}
                    onChange={(e) => setOverrideScore(Number(e.target.value))}
                  >
                    <option value={0}>0 - Chưa có bằng chứng</option>
                    <option value={1}>1 - Nhận biết cơ bản</option>
                    <option value={2}>2 - Áp dụng được dưới hướng dẫn</option>
                    <option value={3}>3 - Thành thạo độc lập (Đề xuất)</option>
                    <option value={4}>4 - Chuyên gia / Tối ưu hiệu năng cao</option>
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Lý do ghi đè bắt buộc (Tối thiểu 10 ký tự, nghiêm cấm yếu tố nhân khẩu học)</label>
                  <textarea
                    className="form-textarea"
                    rows={3}
                    value={overrideReason}
                    onChange={(e) => setOverrideReason(e.target.value)}
                    placeholder="Ví dụ: Ứng viên có kinh nghiệm thực tế thiết kế hạ tầng RPC phân tán với Protobuf đạt chuẩn hiệu năng cao..."
                  />
                </div>

                <button
                  onClick={() => {
                    if (overrideReason.trim().length < 10) {
                      warning("Vui lòng nhập lý do ghi đè chi tiết tối thiểu 10 ký tự.");
                      return;
                    }
                    completeStep("step_3_hr_override", {
                      new_score: overrideScore,
                      reason: overrideReason,
                    });
                  }}
                  className="btn btn-primary"
                  style={{ width: "100%" }}
                >
                  <IconSliders size={16} />
                  <span>Ghi Đè &amp; Tính Lại Điểm Chuẩn Hóa (Hoàn Thành Bước 3)</span>
                </button>
              </div>
            )}

            {/* SCENARIO 4: Attested Decision */}
            {activeStepIndex === 3 && (
              <div>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginBottom: "1.25rem", lineHeight: 1.6 }}>
                  Trong tình huống mẫu, hồ sơ đạt <strong style={{ color: "var(--emerald-text)" }}>78.5/100</strong> (vượt ngưỡng 70, đạt sàn cốt lõi). Hãy xem lại bằng chứng và xác nhận quyết định của người duyệt:
                </p>

                <div style={{
                  background: "var(--bg-surface-elevated)",
                  border: "1px solid var(--border-medium)",
                  padding: "1.15rem",
                  borderRadius: "var(--radius-md)",
                  marginBottom: "1.25rem"
                }}>
                  <label style={{ display: "flex", alignItems: "flex-start", gap: "0.65rem", cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={attestationAccepted}
                      onChange={(e) => setAttestationAccepted(e.target.checked)}
                      style={{ marginTop: "0.25rem" }}
                    />
                    <span style={{ fontSize: "0.825rem", color: "var(--text-primary)", lineHeight: 1.5 }}>
                      Tôi xác nhận (ReviewAttestation) đã trực tiếp xem xét toàn bộ các đoạn trích bằng chứng, không đưa ra quyết định dựa trên bất kỳ thuộc tính phân biệt đối xử nào, và chịu trách nhiệm với tư cách Requisition Owner.
                    </span>
                  </label>
                </div>

                <div className="form-group">
                  <label className="form-label">Quyết định tuyển dụng</label>
                  <select
                    className="form-select"
                    value={selectedOutcome}
                    onChange={(e) => setSelectedOutcome(e.target.value)}
                  >
                    <option value="advance">Chuyển tiếp phỏng vấn kỹ thuật (Advance)</option>
                    <option value="request_information">Yêu cầu bổ sung thông tin (Clarification)</option>
                    <option value="not_advance">Chưa phù hợp (Not Advance)</option>
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
                  className="btn btn-primary"
                  style={{ width: "100%", background: attestationAccepted ? "#10b981" : undefined }}
                >
                  <IconCheckCircle size={16} />
                  <span>Xác nhận quyết định mẫu (Hoàn thành bước 4)</span>
                </button>
              </div>
            )}

            {/* SCENARIO 5: Audit Trail */}
            {activeStepIndex === 4 && (
              <div>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginBottom: "1.25rem", lineHeight: 1.6 }}>
                  Ví dụ minh họa về chuỗi sự kiện kiểm toán; đây không phải log của hồ sơ thật:
                </p>

                <div style={{
                  background: "var(--bg-surface-elevated)",
                  border: "1px solid var(--border-medium)",
                  borderRadius: "var(--radius-md)",
                  padding: "1rem",
                  marginBottom: "1.25rem",
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.775rem",
                  color: "var(--text-primary)",
                  lineHeight: 1.7
                }}>
                  <div>[2026-09-26T08:00:00Z] INTAKE_RECEIVED: CAND-SANDBOX-05 (Hash: a8f9...31c)</div>
                  <div>[2026-09-26T08:00:05Z] SANITIZATION_APPROVED: PII Stripped, 0 contact leaked</div>
                  <div>[2026-09-26T08:01:20Z] AI_ASSESSMENT_RUN: 6 criteria evaluated</div>
                  <div>[2026-09-26T08:05:42Z] HR_REVISION_LOGGED: Criteria sql_data modified by Owner</div>
                  <div>[2026-09-26T08:07:15Z] ATTESTATION_SIGNED: Signed by Owner (Signature valid)</div>
                </div>

                <div style={{
                  background: "rgba(56, 189, 248, 0.08)",
                  border: "1px solid rgba(56, 189, 248, 0.25)",
                  padding: "0.85rem 1rem",
                  borderRadius: "var(--radius-sm)",
                  color: "var(--accent-cyan)",
                  fontSize: "0.825rem",
                  marginBottom: "1.5rem",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.45rem"
                }}>
                  <IconShield size={16} color="var(--accent-cyan)" />
                  <span>Cam kết bảo mật: Zero Demographics, Không lưu PII trong Audit Log, Chuỗi sự kiện bất biến.</span>
                </div>

                <button
                  onClick={() => {
                    completeStep("step_5_audit_trail", {
                      audit_verified: true,
                      tamper_evident_checked: true,
                    });
                  }}
                  className="btn btn-primary"
                  style={{ width: "100%", background: "var(--accent-gradient)" }}
                >
                  <IconCheckCircle size={16} />
                  <span>Xác Nhận Toàn Vẹn &amp; Hoàn Tất Huấn Luyện (Bước 5)</span>
                </button>
              </div>
            )}

            {/* Bottom Completion Banner */}
            {isAllCompleted && (
              <div style={{
                marginTop: "1.5rem",
                background: "rgba(16, 185, 129, 0.15)",
                border: "1px solid var(--emerald-border)",
                borderRadius: "var(--radius-lg)",
                padding: "1.5rem",
                textAlign: "center"
              }}>
                <div style={{ color: "var(--emerald-text)", fontWeight: 800, fontSize: "1.15rem", marginBottom: "0.35rem", display: "flex", alignItems: "center", justifyContent: "center", gap: "0.5rem" }}>
                  <IconCheckCircle size={22} color="var(--emerald-text)" />
                  <span>CHÚC MỪNG: BẠN ĐÃ HOÀN THÀNH HUẤN LUYỆN HR ONBOARDING!</span>
                </div>
                <p style={{ color: "#cbd5e1", fontSize: "0.875rem", maxWidth: "560px", margin: "0 auto 1.25rem auto", lineHeight: 1.6 }}>
                  Bạn đã nắm vững toàn bộ 5 nguyên tắc bất biến của hệ thống TalentScreen AI. Bây giờ bạn hoàn toàn sẵn sàng thẩm định các đợt tuyển dụng thực tế.
                </p>
                <Link href="/requisitions" className="btn btn-primary">
                  <span>Mở Workspace Đợt Tuyển Dụng Thật</span>
                  <IconArrowRight size={16} />
                </Link>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
