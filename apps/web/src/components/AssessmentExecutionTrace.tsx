"use client";

import React from "react";
import { AssessmentExecutionTraceData } from "@/lib/api";

interface Props {
  strategy: string;
  trace: AssessmentExecutionTraceData;
  criterionLabels?: Record<string, string>;
}

function providerLabel(value?: string): string {
  if (!value) return "Không ghi nhận";
  const normalized = value.toLowerCase();
  if (normalized.includes("deepseek")) return "DeepSeek";
  if (normalized.includes("jev")) return "Jev shadow";
  if (normalized.includes("mock")) return "Mock provider";
  return value.slice(0, 80);
}

function strategyLabel(value?: string): string {
  switch (value) {
    case "hybrid": return "Hybrid RAG · vector + lexical";
    case "full_text_baseline":
    case "fulltext": return "Đối chiếu toàn văn baseline";
    case "fulltext_fallback": return "Dự phòng toàn văn";
    default: return value ? value.slice(0, 80) : "Không ghi nhận";
  }
}

function outcomeLabel(value?: string): string {
  switch (value) {
    case "validated":
    case "succeeded": return "Đã kiểm tra đầu ra và bằng chứng";
    case "insufficient_evidence": return "Chưa đủ bằng chứng · giữ HR rà soát";
    case "failed":
    case "blocked": return "Không tạo kết quả hợp lệ · cần HR xử lý thủ công";
    case "running": return "Đang xử lý";
    default: return value ? value.slice(0, 80) : "Không có trạng thái trace";
  }
}

function toolLabel(value?: string): string {
  switch (value) {
    case "retrieve_more_evidence": return "Tìm thêm bằng chứng";
    case "get_source_spans": return "Đọc các đoạn nguồn đã tìm thấy";
    default: return "Tác vụ được ghi nhận";
  }
}

export default function AssessmentExecutionTrace({ strategy, trace, criterionLabels = {} }: Props) {
  const toolCalls = Array.isArray(trace?.tool_calls) ? trace.tool_calls : [];
  const outcome = trace?.outcome;
  const failed = outcome === "failed" || outcome === "blocked";
  const hasDetails = Boolean(
    trace && (
      trace.agent_prompt_version || trace.assessment_prompt_version || trace.provider || trace.model ||
      trace.model_round_trips !== undefined || trace.tool_execution_count !== undefined ||
      toolCalls.length || trace.error_code
    )
  );

  return (
    <section className={`assessment-trace ${failed ? "assessment-trace-failed" : ""}`} aria-labelledby="assessment-trace-title">
      <div className="assessment-trace-heading">
        <div>
          <h3 id="assessment-trace-title">Dấu vết xử lý AI</h3>
          <p>Trace chỉ lưu phiên bản, trạng thái, số lượt và ID bằng chứng; không hiển thị prompt, câu truy vấn hay nội dung CV.</p>
        </div>
        <span className={`assessment-trace-status ${failed ? "is-failed" : ""}`} role={failed ? "alert" : "status"}>
          {outcomeLabel(outcome)}
        </span>
      </div>

      <dl className="assessment-trace-facts">
        <div><dt>Chiến lược</dt><dd>{strategyLabel(trace?.retrieval_strategy || strategy)}</dd></div>
        <div><dt>Provider</dt><dd>{providerLabel(trace?.provider)}</dd></div>
        <div><dt>Model</dt><dd>{trace?.model ? trace.model.slice(0, 100) : "Không ghi nhận"}</dd></div>
        <div><dt>Lượt gọi model</dt><dd>{Number.isInteger(trace?.model_round_trips) ? trace.model_round_trips : "—"}</dd></div>
        <div><dt>Lượt dùng tool</dt><dd>{Number.isInteger(trace?.tool_execution_count) ? trace.tool_execution_count : "—"}</dd></div>
        <div><dt>Tiêu chí trong kết quả</dt><dd>{Number.isInteger(trace?.result_criterion_count) ? trace.result_criterion_count : "—"}</dd></div>
      </dl>

      {trace?.error_code && <p className="assessment-trace-error">Mã trạng thái: <code>{trace.error_code.slice(0, 80)}</code></p>}

      {hasDetails ? (
        <details className="assessment-trace-details">
          <summary>Xem phiên bản prompt và bước truy xuất</summary>
          <div className="assessment-trace-versions">
            <span>Agent prompt: <code>{trace.agent_prompt_version || "không ghi nhận"}</code></span>
            <span>Assessment prompt: <code>{trace.assessment_prompt_version || "không ghi nhận"}</code></span>
          </div>
          {toolCalls.length > 0 ? (
            <ol className="assessment-trace-tools">
              {toolCalls.map((call, index) => {
                const criterionIds = Array.isArray(call.criterion_ids) ? call.criterion_ids : [];
                const spanIds = Array.isArray(call.span_ids) ? call.span_ids : [];
                return (
                  <li key={`${call.tool_name || "tool"}-${index}`}>
                    <strong>{toolLabel(call.tool_name)}</strong>
                    <span>{call.outcome === "succeeded" ? "Hoàn tất" : call.outcome === "blocked" ? "Bị chặn" : "Đã ghi nhận"}</span>
                    {criterionIds.length > 0 && (
                      <div className="assessment-trace-ref-list">
                        Tiêu chí: {criterionIds.map((criterionId) => criterionLabels[criterionId] || criterionId).join(", ")}
                      </div>
                    )}
                    <div className="assessment-trace-ref-list">
                      {Number.isInteger(call.result_count) ? `${call.result_count} kết quả` : "Số kết quả không có"}
                      {spanIds.length > 0 && <> · span: {spanIds.slice(0, 4).map((spanId) => <code key={spanId}>{spanId}</code>)}{spanIds.length > 4 ? ` +${spanIds.length - 4}` : ""}</>}
                    </div>
                  </li>
                );
              })}
            </ol>
          ) : (
            <p className="assessment-trace-empty">Lượt chạy này không gọi thêm retrieval tool.</p>
          )}
        </details>
      ) : (
        <p className="assessment-trace-empty">Trace chi tiết chưa được lưu cho lượt chạy này.</p>
      )}
    </section>
  );
}
