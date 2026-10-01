"use client";
import { useEffect, useState } from "react";
import { api, AssessmentRunData } from "@/lib/api";
type Criterion = { criterion_id: string; status: string; score: number | null; evidence: { span_id: string; quote: string }[]; rationale: string; missing_information: string[] };
const normalize = (items: any[]): Criterion[] => items.map(c => ({ criterion_id: c.criterion_id, status: c.status, score: c.score, evidence: (c.evidence || []).map((e: any) => ({ span_id: e.span_id, quote: e.quote })), rationale: c.rationale, missing_information: c.missing_information || [] }));
export default function HRRevisionEditor({ application, rubric, run, revisions, selectedCriterion, onSaved }: { application: any; rubric: any; run: AssessmentRunData; revisions: any[]; selectedCriterion: string | null; onSaved: () => Promise<void> }) {
  const draft = revisions.find(r => r.status === "draft" && !r.is_stale && r.rubric_version_id === rubric.id && r.application_generation === application.generation);
  const [criteria, setCriteria] = useState<Criterion[]>(normalize(draft?.criteria_payload?.criteria || run.criteria));
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [summary, setSummary] = useState(draft?.summary_reason || "");
  const [spans, setSpans] = useState<{ span_id: string; quote: string }[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { let active = true; api.getApprovedSpans(application.id).then(data => { if (active) setSpans(data); }).catch(e => { if (active) setError(e.message); }); return () => { active = false; }; }, [application.id, application.current_sanitized_version_id]);
  useEffect(() => {
    setCriteria(normalize(draft?.criteria_payload?.criteria || run.criteria));
    setSummary(draft?.summary_reason || "");
    setReasons(Object.fromEntries(Object.entries(draft?.change_reasons || {}).map(([key, value]: [string, any]) => [key, value.note])));
  }, [draft?.id, run.id]);
  useEffect(() => { if (!selectedCriterion) return; setExpanded(true); const frame = requestAnimationFrame(() => document.getElementById(`hr-edit-${selectedCriterion}`)?.scrollIntoView({ block: "start" })); return () => cancelAnimationFrame(frame); }, [selectedCriterion]);
  const update = (id: string, patch: Partial<Criterion>) => setCriteria(previous => previous.map(c => c.criterion_id === id ? { ...c, ...patch } : c));
  const original = normalize(run.criteria);
  const changed = criteria.filter(c => JSON.stringify(c) !== JSON.stringify(original.find(o => o.criterion_id === c.criterion_id)));
  const valid = summary.trim().length >= 10 && changed.every(c => (reasons[c.criterion_id] || "").trim().length >= 20) && criteria.every(c => c.rationale.trim().length > 0 &&
    (c.status === "assessed" ? c.score !== null && c.evidence.length > 0 : c.missing_information.some(x => x.trim()) && (c.status !== "conflicting_evidence" || c.evidence.length >= 2)));
  async function save() {
    setBusy(true); setError("");
    const payload = { criteria, summary_reason: summary.trim(), change_reasons: Object.fromEntries(changed.map(c => [c.criterion_id, { reason_code: "other", note: reasons[c.criterion_id].trim() }])) };
    try {
      if (draft) await api.updateHRRevision(draft.id, { ...payload, expected_revision_version: 1 });
      else await api.createHRRevision(application.id, { ...payload, expected_application_version: application.row_version, base_run_id: run.id,
        source_snapshot_ref: { document_id: application.current_document_id, sanitized_version_id: application.current_sanitized_version_id, rubric_version_id: rubric.id, application_generation: application.generation } });
      await onSaved();
    } catch (e) { setError(e instanceof Error ? e.message : "Không lưu được bản nháp."); }
    finally { setBusy(false); }
  }
  async function finalize() {
    if (!draft) return; setBusy(true); setError("");
    try { await api.finalizeHRRevision(draft.id, application.row_version, rubric.id); await onSaved(); }
    catch (e) { setError(e instanceof Error ? e.message : "Không hoàn tất được bản đánh giá."); } finally { setBusy(false); }
  }
  const savedMatches = draft && JSON.stringify(criteria) === JSON.stringify(normalize(draft.criteria_payload.criteria)) && summary === draft.summary_reason && changed.every(c => reasons[c.criterion_id] === draft.change_reasons?.[c.criterion_id]?.note);
  return <section id="hr-revision-editor" className="card revision-editor">
    <h2>Điều chỉnh đánh giá của HR</h2><p className="muted">Lưu bản nháp, kiểm tra khác biệt rồi hoàn tất để dùng làm căn cứ quyết định. Điểm AI gốc được giữ nguyên. Chưa đủ bằng chứng giữ điểm trống.</p>
    {error && <p className="notice notice-error" role="alert">{error}</p>}
    <details open={expanded} onToggle={event => setExpanded(event.currentTarget.open)}><summary>Chỉnh từng tiêu chí · {changed.length} tiêu chí khác AI</summary>
      {criteria.map(c => <section id={`hr-edit-${c.criterion_id}`} className="criterion-edit" key={c.criterion_id}>
        <h3>{rubric.criteria?.find((definition: any) => definition.id === c.criterion_id)?.label || c.criterion_id}</h3>
        <p>AI: {original.find(o => o.criterion_id === c.criterion_id)?.score ?? "Chưa đủ bằng chứng"} → HR: {c.score ?? "Chưa đủ bằng chứng"}</p>
        <label>Trạng thái bằng chứng<select className="form-input" value={c.status} onChange={e => update(c.criterion_id, { status: e.target.value, score: e.target.value === "assessed" ? c.score : null, missing_information: e.target.value === "assessed" ? [] : c.missing_information })}>
          <option value="assessed">Có bằng chứng để chấm</option><option value="insufficient_evidence">Chưa đủ bằng chứng</option><option value="conflicting_evidence">Bằng chứng mâu thuẫn</option></select></label>
        {c.status === "assessed" && <label>Điểm theo tiêu chí<select className="form-input" value={c.score ?? ""} onChange={e => update(c.criterion_id, { score: e.target.value === "" ? null : Number(e.target.value) })}><option value="">Chọn mức điểm</option>{[0,1,2,3,4].map(n => <option key={n} value={n}>{n}/4</option>)}</select></label>}
        <details><summary>Thang điểm 0–4</summary>{rubric.criteria?.find((d: any) => d.id === c.criterion_id)?.scoring_anchors?.map((anchor: any) => <p key={anchor.score}><strong>{anchor.score}/4:</strong> {anchor.description}</p>)}</details>
        <label>Giải thích đánh giá<textarea className="form-textarea" maxLength={1200} value={c.rationale} onChange={e => update(c.criterion_id, { rationale: e.target.value })} /></label>
        {c.status !== "assessed" && <label>Thông tin cần làm rõ · mỗi dòng một mục<textarea className="form-textarea" value={c.missing_information.join("\n")} onChange={e => update(c.criterion_id, { missing_information: e.target.value.split("\n").filter(Boolean) })} /></label>}
        <details><summary>Chọn bằng chứng nguyên văn · {c.evidence.length} đoạn</summary><div className="span-picker">{spans.map(span => <label key={span.span_id}><input type="checkbox" checked={c.evidence.some(e => e.span_id === span.span_id)} disabled={!c.evidence.some(e => e.span_id === span.span_id) && c.evidence.length >= 6} onChange={e => update(c.criterion_id, { evidence: e.target.checked ? [...c.evidence, span] : c.evidence.filter(x => x.span_id !== span.span_id) })} /><span>{span.quote}</span></label>)}</div></details>
        {changed.some(x => x.criterion_id === c.criterion_id) && <label>Lý do điều chỉnh · tối thiểu 20 ký tự<textarea className="form-textarea" value={reasons[c.criterion_id] || ""} onChange={e => setReasons({ ...reasons, [c.criterion_id]: e.target.value })} /></label>}
      </section>)}
      <label>Lý do tổng hợp · tối thiểu 10 ký tự<textarea className="form-textarea" maxLength={2000} value={summary} onChange={e => setSummary(e.target.value)} /></label>
      <button className="btn btn-primary" disabled={busy || !valid} onClick={() => void save()}>{busy ? "Đang lưu…" : "Lưu bản nháp HR"}</button>
    </details>
    {draft && <div className="notice"><p>Bản nháp HR #{draft.revision_no}. Hoàn tất sẽ khóa bản đã lưu; đây chưa phải quyết định tuyển dụng.</p><button className="btn btn-secondary" disabled={busy || !savedMatches} onClick={() => void finalize()}>Hoàn tất bản đánh giá đã lưu</button></div>}
    {revisions.filter(r => r.status === "finalized").map(r => <details key={r.id}><summary>Bản HR #{r.revision_no} đã hoàn tất {r.is_stale ? "· nguồn đã thay đổi" : ""}</summary><p>{r.summary_reason}</p>{r.criteria_payload.criteria.map((c: any) => <p key={c.criterion_id}>{rubric.criteria?.find((d: any) => d.id === c.criterion_id)?.label || c.criterion_id}: AI {original.find(o => o.criterion_id === c.criterion_id)?.score ?? "—"} → HR {c.score ?? "—"}. {r.change_reasons[c.criterion_id]?.note}</p>)}</details>)}
  </section>;
}
