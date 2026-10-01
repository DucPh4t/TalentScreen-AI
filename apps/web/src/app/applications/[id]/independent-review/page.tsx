"use client";

import { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, IndependentReviewContext } from "@/lib/api";

interface PageProps { params: Promise<{ id: string }> }
type ReviewKind = "hr" | "it";
type Recommendation = "consider_next_round" | "needs_clarification" | "review_required";
type CriterionStatus = "assessed" | "insufficient_evidence" | "conflicting_evidence";

// JSONB does not preserve object key order; compare the draft by values.
function canonicalPayload(value: any): string {
  const sorted = (item: any): any => Array.isArray(item) ? item.map(sorted) : item && typeof item === "object"
    ? Object.fromEntries(Object.keys(item).sort().map(key => [key, sorted(item[key])])) : item;
  return JSON.stringify(sorted(value));
}

export default function IndependentReviewPage({ params }: PageProps) {
  const { id } = use(params);
  const [context, setContext] = useState<IndependentReviewContext | null>(null);
  const [scores, setScores] = useState<Record<string, number | null>>({});
  const [statuses, setStatuses] = useState<Record<string, CriterionStatus>>({});
  const [quotes, setQuotes] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [kind, setKind] = useState<ReviewKind>("hr");
  const [recommendation, setRecommendation] = useState<Recommendation>("review_required");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ack, setAck] = useState(false);
  const [draftStatus, setDraftStatus] = useState("Chưa có thay đổi");
  const [hydrated, setHydrated] = useState(false);
  const [saveTick, setSaveTick] = useState(0);
  const draftVersion = useRef(0);
  const savedPayload = useRef("");
  const saving = useRef(false);
  const cvPane = useRef<HTMLDivElement>(null);
  const [selectedQuote, setSelectedQuote] = useState("");
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    let alive = true;
    api.getIndependentReviewContext(id).then(async (data) => {
      if (!alive) return;
      setContext(data);
      setSubmitted(data.already_submitted);
      setScores(Object.fromEntries(data.criteria.map((criterion) => [criterion.id, null])));
      setStatuses(Object.fromEntries(data.criteria.map((criterion) => [criterion.id, "insufficient_evidence"])));
      setQuotes(Object.fromEntries(data.criteria.map((criterion) => [criterion.id, ""])));
      setNotes(Object.fromEntries(data.criteria.map((criterion) => [criterion.id, ""])));
      if (!data.already_submitted) {
        try {
          const draft = await api.getIndependentReviewDraft(id);
          if (!alive) return;
          if (draft) {
            setScores(draft.payload.criterion_scores); setStatuses(draft.payload.criterion_statuses);
            setQuotes(Object.fromEntries(Object.entries(draft.payload.criterion_quotes).map(([key,value]) => [key, value || ""])) as Record<string,string>);
            setNotes(draft.payload.criterion_notes); setKind(draft.payload.review_kind); setRecommendation(draft.payload.recommendation);
            draftVersion.current = draft.version; savedPayload.current = canonicalPayload({ ...draft.payload, criterion_quotes: Object.fromEntries(Object.entries(draft.payload.criterion_quotes).map(([key, value]) => [key, value || ""])) }); setDraftStatus("Đã khôi phục bản nháp riêng của bạn");
          }
        } catch (e) { setError(e instanceof Error ? e.message : "Không khôi phục được bản nháp."); return; }
      }
      setHydrated(true);
    }).catch((reason) => { if (alive) setError(reason.message || "Không tải được hồ sơ chấm độc lập."); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [id]);

  const labelPayload = context ? {
    review_kind: kind, expected_generation: context.application_generation, expected_document_id: context.document_id,
    expected_sanitized_version_id: context.sanitized_version_id, expected_rubric_version_id: context.rubric_version_id,
    criterion_scores: scores, criterion_statuses: statuses, criterion_quotes: quotes, criterion_notes: notes, recommendation,
  } : null;
  const encodedPayload = canonicalPayload(labelPayload);
  useEffect(() => {
    if (!hydrated || !context || submitted || submitting || !labelPayload || encodedPayload === savedPayload.current) return;
    setDraftStatus("Có thay đổi chưa lưu…");
    const timer = window.setTimeout(async () => {
      if (saving.current) return;
      saving.current = true; setDraftStatus("Đang lưu bản nháp…");
      try {
        const result = await api.saveIndependentReviewDraft(id, { ...JSON.parse(encodedPayload), expected_draft_version: draftVersion.current });
        draftVersion.current = result.version; savedPayload.current = encodedPayload;
        setDraftStatus("Đã lưu bản nháp riêng ở server · hiệu lực 24 giờ");
        setSaveTick(previous => previous + 1);
      } catch (e) { setDraftStatus(e instanceof Error ? `Chưa lưu: ${e.message}` : "Chưa lưu được. Giữ trang mở và thử lại."); }
      finally { saving.current = false; }
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [encodedPayload, hydrated, submitted, submitting, saveTick]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (hydrated && !submitted && encodedPayload !== savedPayload.current) { event.preventDefault(); event.returnValue = ""; }
    };
    window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn);
  }, [encodedPayload, hydrated, submitted]);

  const valid = Boolean(context && context.criteria.length > 0 && context.criteria.every(
    (criterion) => {
      const status = statuses[criterion.id];
      const quote = quotes[criterion.id]?.trim() || "";
      return notes[criterion.id]?.trim().length >= 10 &&
        (status === "insufficient_evidence" || (quote.length >= 10 && context.sanitized_text.includes(quote))) &&
        (status !== "assessed" || scores[criterion.id] !== null);
    }
  ));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!context || !valid || !ack || saving.current || submitting || submitted) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.submitIndependentReview(id, {
        review_kind: kind,
        expected_generation: context.application_generation,
        expected_document_id: context.document_id,
        expected_sanitized_version_id: context.sanitized_version_id,
        expected_rubric_version_id: context.rubric_version_id,
        criterion_scores: scores,
        criterion_statuses: statuses,
        criterion_quotes: Object.fromEntries(context.criteria.map((criterion) => [criterion.id, statuses[criterion.id] === "insufficient_evidence" ? null : quotes[criterion.id].trim()])),
        criterion_notes: notes,
        recommendation,
      });
      setSubmitted(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không nộp được nhãn độc lập. Hãy tải lại hồ sơ.");
    } finally {
      setSubmitting(false);
    }
  }

  return <main className="page-content" style={{ maxWidth: 1160, margin: "0 auto", padding: "1.5rem" }}>
    <Link href={context ? `/requisitions/${context.requisition_id || ""}` : "/requisitions"} className="btn btn-secondary btn-sm">← Quay về đợt tuyển dụng</Link>
    <div style={{ margin: "1.25rem 0" }}>
      <h1>Chấm độc lập hồ sơ</h1>
      <p className="muted">Chỉ dùng CV đã che và rubric đã duyệt. Điểm AI không xuất hiện trước khi bạn khóa nhãn.</p>
    </div>
    {loading && <p>Đang tải CV và tiêu chí…</p>}
    {error && <p role="alert" className="notice notice-error">{error}</p>}
    {context && <div className="blind-review-grid">
      <div className="card blind-cv-pane" style={{ padding: "1.25rem", marginBottom: "1rem" }}>
        <strong>{context.public_label}</strong>
        <p className="muted">Phiên bản hồ sơ gen-{context.application_generation}. Mọi đánh giá dưới đây sẽ gắn với đúng CV và rubric này.</p>
        {!context.enforced_blind && <p className="notice notice-warning">Môi trường hiện tại chưa khóa API kết quả AI cho reviewer. Nhãn nộp ở đây chỉ dùng diễn tập; không tính là nhãn mù cho nghiệm thu shadow.</p>}
        {submitted && <div className="notice notice-success" role="status">Nhãn đã được khóa. Bạn có thể mở hồ sơ để đối chiếu với AI; không thể sửa nhãn đã nộp.</div>}
        <h2 style={{ marginTop: "1rem" }}>CV đã che</h2>
        <p className="muted">Bôi đen một đoạn CV rồi dùng nút “Dùng đoạn đã chọn” ở tiêu chí tương ứng.</p>
        <div ref={cvPane} className="blind-cv-text" onMouseUp={() => {
          const selection = window.getSelection();
          if (selection?.anchorNode && selection.focusNode && cvPane.current?.contains(selection.anchorNode) && cvPane.current?.contains(selection.focusNode)) setSelectedQuote(selection.toString().trim());
        }}>
          {context.sanitized_text}
        </div>
      </div>
      {!submitted && <form onSubmit={submit}>
        <p role="status" aria-live="polite">{draftStatus}</p><button type="button" className="btn btn-secondary btn-sm" onClick={() => setSaveTick(previous => previous + 1)}>Lưu lại bản nháp</button>
        <div className="card" style={{ padding: "1.25rem", marginBottom: "1rem" }}>
          <label className="form-label" htmlFor="review-kind">Vai trò đánh giá</label>
          <select id="review-kind" className="form-input" value={kind} onChange={(event) => setKind(event.target.value as ReviewKind)}>
            <option value="hr">HR</option><option value="it">Chuyên môn IT</option>
          </select>
          <p className="muted">Vai trò này do người đánh giá khai báo; Owner cần kiểm tra người tham gia trước khi dùng làm tập nhãn nghiệm thu.</p>
        </div>
        {context.criteria.map((criterion) => <section className="card" key={criterion.id} style={{ padding: "1.25rem", marginBottom: "1rem" }}>
          <h2>{criterion.label}</h2>
          <p className="muted">{criterion.description}</p>
          <details><summary>Thang điểm 0–4</summary>{Object.entries(criterion.anchors).map(([score, anchor]: [string, any]) => <p key={score}><strong>{score}/4:</strong> {typeof anchor === "string" ? anchor : anchor.description || anchor.description_vi || "Xem tiêu chí được duyệt"}</p>)}</details>
          <label className="form-label" htmlFor={`status-${criterion.id}`}>Trạng thái bằng chứng</label>
          <select id={`status-${criterion.id}`} className="form-input" value={statuses[criterion.id] || "insufficient_evidence"}
            onChange={(event) => {
              const next = event.target.value as CriterionStatus;
              setStatuses({ ...statuses, [criterion.id]: next });
              if (next !== "assessed") setScores({ ...scores, [criterion.id]: null });
            }}>
            <option value="insufficient_evidence">Chưa đủ bằng chứng</option>
            <option value="assessed">Có bằng chứng để chấm</option>
            <option value="conflicting_evidence">Bằng chứng mâu thuẫn</option>
          </select>
          {statuses[criterion.id] !== "insufficient_evidence" && <>
            <button type="button" className="btn btn-secondary btn-sm" disabled={selectedQuote.length < 10 || !context.sanitized_text.includes(selectedQuote)} onClick={() => setQuotes({ ...quotes, [criterion.id]: selectedQuote })}>Dùng đoạn đã chọn từ CV</button>
            <label className="form-label" htmlFor={`quote-${criterion.id}`}>Trích dẫn nguyên văn từ CV đã che</label>
            <textarea id={`quote-${criterion.id}`} className="form-textarea" rows={2} minLength={10} required
              value={quotes[criterion.id] || ""} onChange={(event) => setQuotes({ ...quotes, [criterion.id]: event.target.value })}
              placeholder="Dán một đoạn có thật từ CV đã che ở trên." />
          </>}
          {statuses[criterion.id] === "assessed" && <>
          <label className="form-label" htmlFor={`score-${criterion.id}`}>Điểm quan sát</label>
          <select id={`score-${criterion.id}`} className="form-input" value={scores[criterion.id] ?? "unknown"} required
            onChange={(event) => setScores({ ...scores, [criterion.id]: event.target.value === "unknown" ? null : Number(event.target.value) })}>
            <option value="unknown">Chọn mức điểm</option>
            {[0, 1, 2, 3, 4].map((score) => <option key={score} value={score}>{score}/4</option>)}
          </select>
          </>}
          <label className="form-label" htmlFor={`note-${criterion.id}`}>Căn cứ trong CV hoặc thông tin cần hỏi thêm</label>
          <textarea id={`note-${criterion.id}`} className="form-textarea" rows={3} minLength={10} required
            value={notes[criterion.id] || ""} onChange={(event) => setNotes({ ...notes, [criterion.id]: event.target.value })}
            placeholder="Nêu bằng chứng cụ thể; nếu chưa đủ thông tin, ghi rõ điều cần xác minh." />
        </section>)}
        <div className="card" style={{ padding: "1.25rem" }}>
          <label className="form-label" htmlFor="review-recommendation">Đề xuất của bạn</label>
          <select id="review-recommendation" className="form-input" value={recommendation}
            onChange={(event) => setRecommendation(event.target.value as Recommendation)}>
            <option value="review_required">Cần HR xem xét</option>
            <option value="needs_clarification">Cần làm rõ thông tin</option>
            <option value="consider_next_round">Cân nhắc vòng tiếp theo</option>
          </select>
          <p className="muted">Đây là nhãn đánh giá độc lập để đo mức tương đồng với AI, không phải quyết định tuyển dụng.</p>
          <label className="rubric-ack"><input type="checkbox" checked={ack} onChange={event => setAck(event.target.checked)} />Tôi đã rà soát từng tiêu chí và xác nhận khóa nhãn; nhãn đã nộp không thể sửa.</label>
          <button className="btn btn-primary" type="submit" disabled={!valid || !ack || submitting || !hydrated}>{submitting ? "Đang khóa nhãn…" : "Nộp và khóa nhãn độc lập"}</button>
        </div>
      </form>}
    </div>}
  </main>;
}
