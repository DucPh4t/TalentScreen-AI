"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
export default function QuestionBankSetup({ rubricId, canManage }: { rubricId: string; canManage: boolean }) {
  const [banks, setBanks] = useState<any[]>([]); const [error, setError] = useState(""); const [busy, setBusy] = useState(false); const [ack, setAck] = useState(false);
  useEffect(() => { let active = true; setBanks([]); setAck(false); api.getQuestionBank(rubricId).then(data => { if (active) setBanks(data); }).catch(e => { if (active) setError(e.message); }); return () => { active = false; }; }, [rubricId]);
  const draft = banks.find(b => b.status === "draft"); const approved = banks.find(b => b.status === "approved");
  async function act() { setBusy(true); setError(""); try { if (draft) await api.approveQuestionBank(draft.id, rubricId); else await api.createSeedQuestionBank(rubricId); setBanks(await api.getQuestionBank(rubricId)); setAck(false); } catch (e) { setError(e instanceof Error ? e.message : "Không cập nhật được câu hỏi."); } finally { setBusy(false); } }
  return <section className="card"><h2>Câu hỏi phỏng vấn chuẩn của đợt</h2><p className="muted">Chuẩn bị và duyệt một lần cho mỗi phiên bản tiêu chí; dùng cùng bộ câu hỏi khi phỏng vấn các ứng viên.</p>
    {error && <div role="alert" className="notice notice-error">{error}<button className="btn btn-secondary" onClick={() => { setError(""); api.getQuestionBank(rubricId).then(setBanks).catch(e => setError(e.message)); }}>Thử tải lại</button></div>}
    {(draft || approved)?.questions?.map((q: any) => <article className="criterion-edit" key={q.question_id}><strong>{q.criterion_id}</strong><p>{q.question_vi}</p><small>{q.purpose_vi}</small></article>)}
    {approved && <p role="status">Đã có bộ câu hỏi được duyệt.</p>}
    {canManage && !approved && <>{draft && <label className="rubric-ack"><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} />Tôi đã kiểm tra câu hỏi phù hợp với tiêu chí và JD.</label>}<button className="btn btn-primary" disabled={busy || !!error || (!!draft && !ack)} onClick={() => void act()}>{busy ? "Đang lưu…" : draft ? "Duyệt bộ câu hỏi" : "Tạo bộ câu hỏi mẫu"}</button></>}
  </section>;
}
