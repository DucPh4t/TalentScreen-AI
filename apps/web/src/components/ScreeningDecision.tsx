"use client";
import { useEffect, useState } from 'react';
import { outcomeLabels, type ClarificationResolution, type ScreeningOutcome } from '@/lib/hr-workflow';

type Props = {
  decisions:any[]; canManage:boolean; busy:boolean; blocked:boolean; reviewed:number; total:number;
  outcome:ScreeningOutcome; setOutcome:(value:ScreeningOutcome)=>void;
  clarificationResolution:ClarificationResolution|null; setClarificationResolution:(value:ClarificationResolution|null)=>void;
  resolutionOptions:ClarificationResolution[];
  reason:string; setReason:(value:string)=>void; acknowledged:boolean; setAcknowledged:(value:boolean)=>void;
  onSubmit:(event:React.FormEvent)=>void; onEvidence:()=>void; basis:string; recommendation?:string|null; stale:boolean;
};
export default function ScreeningDecision(p:Props) {
  const [editing,setEditing] = useState(false);
  const latest = p.decisions[0];
  const dispositionLabel = (value?:string|null) => {
    if (!value) return null;
    const match = value.match(/^clarification_resolution=([^;]+);?\s*(.*)$/);
    if (!match) return value;
    const labels:Record<string,string> = {
      candidate_confirmed_no_experience:'Ứng viên xác nhận chưa có kinh nghiệm ở tiêu chí bắt buộc',
      no_response_after_contact:'HR ghi nhận ứng viên không phản hồi sau khi được liên hệ',
      independent_evidence_based_reason:'HR ghi nhận căn cứ độc lập từ evidence khác',
    };
    return `${labels[match[1]] || match[1]}${match[2] ? ` · ${match[2]}` : ''}`;
  };
  useEffect(()=>{setEditing(false);},[latest?.id]);
  return <section className="card" aria-labelledby="screening-title">
    <div className="card-header"><div><h2 id="screening-title" className="card-title">Kết luận sàng lọc của HR</h2>
      <p className="muted">Chọn bước tiếp theo cho hồ sơ. Kết luận này chưa phải quyết định nhận việc.</p></div>
      {latest && p.canManage && <button className="btn btn-secondary" onClick={()=>{setEditing(!editing);p.setAcknowledged(false);p.setOutcome(latest.outcome);p.setClarificationResolution(null);p.setReason('');}}>{editing?'Hủy cập nhật':'Cập nhật kết luận'}</button>}
    </div>
    {latest && <div className="surface workflow-result"><strong>{outcomeLabels[latest.outcome]}</strong><p>{latest.reason}</p>
      {latest.override_reason && <p><strong>Giải trình / xác nhận xử lý:</strong> {dispositionLabel(latest.override_reason)}</p>}
      <small className="muted">Phiên bản {latest.sequence_no} · {new Date(latest.created_at).toLocaleString('vi-VN')}</small>
      {p.stale && <p role="alert" className="notice">Căn cứ hồ sơ đã đổi. Cần rà soát và cập nhật kết luận trước khi dùng tiếp.</p>}
    </div>}
    {(!latest || editing) && <form onSubmit={e=>{p.onSubmit(e);}} className="workflow-form">
      <div className="notice"><strong>Căn cứ: {p.basis}</strong><p>Đã đối chiếu {p.reviewed}/{p.total} tiêu chí.</p>
        <button type="button" className="btn btn-secondary btn-sm" onClick={p.onEvidence}>Xem bằng chứng và điều chỉnh</button></div>
      <fieldset className="workflow-options"><legend>Bước tiếp theo</legend>
        {(['advance','request_information','not_advance'] as const).map(outcome=><label key={outcome} className={p.outcome===outcome?'workflow-option selected':'workflow-option'}>
          <input type="radio" name="screening-outcome" value={outcome} checked={p.outcome===outcome} onChange={()=>{p.setOutcome(outcome);p.setClarificationResolution(null);}} disabled={!p.canManage||p.busy}/>
          <span><strong>{outcomeLabels[outcome]}</strong><small>{outcome==='advance'?'Trao đổi để kiểm chứng năng lực':outcome==='request_information'?'Giữ hồ sơ mở, chờ ứng viên phản hồi':'Kết thúc sàng lọc cho vị trí này'}</small></span>
        </label>)}
      </fieldset>
      {p.outcome==='not_advance' && p.recommendation==='needs_clarification' && p.resolutionOptions.length>0 && <>
        <label className="form-label" htmlFor="clarification-resolution">Cách xử lý evidence còn thiếu</label>
        <select id="clarification-resolution" className="form-input" required value={p.clarificationResolution||''}
          onChange={e=>p.setClarificationResolution((e.target.value||null) as ClarificationResolution|null)} disabled={!p.canManage||p.busy}>
          <option value="">Chọn kết quả xác minh</option>
          {p.resolutionOptions.map(value=><option key={value} value={value}>{value==='candidate_confirmed_no_experience'?'Ứng viên xác nhận chưa có năng lực':value==='no_response_after_contact'?'Đã liên hệ và ứng viên không phản hồi sau hạn đã thông báo':'Có căn cứ độc lập khác từ evidence đã rà soát'}</option>)}
        </select>
        <p className="muted">Lựa chọn này được lưu cùng giải trình kiểm toán. Thiếu nice-to-have tự nó không phải lý do từ chối; thiếu must-have cần ghi nhận đã liên hệ và kết quả làm rõ.</p>
      </>}
      <label className="form-label" htmlFor="screening-reason">Lý do và căn cứ của HR</label>
      <textarea id="screening-reason" rows={3} maxLength={2000} minLength={20} required value={p.reason} onChange={e=>p.setReason(e.target.value)} placeholder="Nêu năng lực, bằng chứng đã đối chiếu và nội dung còn cần làm rõ." disabled={!p.canManage||p.busy}/>
      <p className="muted">Ít nhất 20 ký tự. Khi chọn khác khuyến nghị AI, lý do này được lưu làm giải trình.</p>
      <label className="rubric-ack"><input type="checkbox" checked={p.acknowledged} onChange={e=>p.setAcknowledged(e.target.checked)} disabled={!p.canManage||p.busy}/>
        Tôi đã đối chiếu bằng chứng với CV, xem các điểm cần làm rõ và chịu trách nhiệm về kết luận dựa trên năng lực.</label>
      {p.reviewed!==p.total && <p className="notice">Cần hoàn tất đối chiếu tiêu chí ở tab bằng chứng trước khi ghi kết luận.</p>}
      <button className="btn btn-primary" type="submit" disabled={!p.canManage||p.busy||p.blocked||!p.total||p.reviewed!==p.total||!p.acknowledged||p.reason.trim().length<20||(p.outcome==='not_advance'&&p.recommendation==='needs_clarification'&&p.resolutionOptions.length>0&&!p.clarificationResolution)}>
        {p.busy?'Đang ghi nhận…':latest?'Ghi phiên bản kết luận mới':'Ghi kết luận sàng lọc'}</button>
    </form>}
    {p.decisions.length>1 && <details className="workflow-history"><summary>Lịch sử kết luận ({p.decisions.length})</summary>
      {p.decisions.map(d=><article key={d.id}><strong>#{d.sequence_no} · {outcomeLabels[d.outcome]}</strong><p>{d.reason}</p>{d.override_reason&&<p><strong>Giải trình / xác nhận xử lý:</strong> {dispositionLabel(d.override_reason)}</p>}<small>{new Date(d.created_at).toLocaleString('vi-VN')}</small></article>)}
    </details>}
  </section>;
}
