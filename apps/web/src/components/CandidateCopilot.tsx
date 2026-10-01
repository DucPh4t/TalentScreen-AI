"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
export default function CandidateCopilot({ applicationId, snapshotKey, onEvidence }: { applicationId: string; snapshotKey: string; onEvidence: (e: any) => void }) {
  const [message, setMessage] = useState(""); const [answer, setAnswer] = useState<any>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  useEffect(() => { setAnswer(null); setMessage(""); setError(""); }, [snapshotKey]);
  async function ask(event: React.FormEvent) { event.preventDefault(); if (busy || message.trim().length < 3) return; setBusy(true); setError(""); setAnswer(null);
    try { setAnswer(await api.askCopilot(applicationId, message.trim())); } catch(e) { setError(e instanceof Error ? e.message : "Không trả lời được."); } finally { setBusy(false); } }
  return <details className="card copilot-panel"><summary>Copilot · hỏi về hồ sơ này</summary><p className="muted">Giải thích từ đánh giá AI đã lưu và CV đã duyệt. Không thực hiện quyết định hoặc gửi thư. Không nhập thông tin định danh.</p>
    <div className="workflow-actions">{["Vì sao SQL được đánh giá như vậy?", "CV còn thiếu bằng chứng nào?", "Gợi ý 3 câu hỏi làm rõ kinh nghiệm"].map(q => <button type="button" className="btn btn-secondary btn-sm" disabled={busy} key={q} onClick={() => setMessage(q)}>{q}</button>)}</div>
    <form onSubmit={ask}><label htmlFor="copilot-question">Câu hỏi</label><textarea id="copilot-question" className="form-textarea" rows={2} maxLength={600} value={message} onChange={e => setMessage(e.target.value)} disabled={busy} /><button className="btn btn-primary" disabled={busy || message.trim().length < 3}>{busy ? "Đang tìm thông tin…" : "Hỏi Copilot"}</button></form>
    {error && <p role="alert" className="notice notice-error">{error}</p>}
    <div role="status" aria-live="polite">{busy && "Đang đối chiếu nguồn đã duyệt…"}</div>
    {answer && <div className="copilot-answer"><p>{answer.message}</p><small>Nguồn: đánh giá {answer.run_id.slice(0,8)} · {answer.provider === "mock" ? "Mô phỏng, chưa dùng DeepSeek" : "DeepSeek chọn thông tin; server kiểm tra nguồn"}</small>
      {answer.facts.map((fact: any) => <article key={fact.criterion_id}><h3>{fact.label} · {fact.score === null ? "Chưa có điểm" : `${fact.score}/4`}</h3><p>{fact.rationale}</p>{fact.missing_information.length > 0 && <p>Cần làm rõ: {fact.missing_information.join("; ")}</p>}{fact.evidence.map((e: any) => <button type="button" className="evidence-quote-box" key={e.span_id} onClick={() => onEvidence(e)}>“{e.quote}” · Xem bằng chứng</button>)}</article>)}
      {!!answer.questions.length && <ul>{answer.questions.map((q: string) => <li key={q}>{q}</li>)}</ul>}
    </div>}
  </details>;
}
