"use client";
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { api } from '@/lib/api';
import { interviewConsensus, outcomeLabels, preserveEditBase } from '@/lib/hr-workflow';

type Props = {
  applicationId:string; sourceKey:string; roundNo:number; setRoundNo:(value:number)=>void; dirty:boolean; canManage:boolean;
  rubric:any; draft:any; generating:boolean; onGenerate:()=>void; cards:any[]; cardsReady:boolean; userId?:string;
  onFocus:(ids:string[])=>void; onRefresh:()=>Promise<void>; children:ReactNode;
};
export default function InterviewWorkspace(p:Props) {
  const [view,setView] = useState<'prepare'|'record'|'summary'>('prepare');
  const [state,setState] = useState<any>(null);
  const [prep,setPrep] = useState<any>(null);
  const [dirty,setDirty] = useState(false);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const [notice,setNotice] = useState('');
  const [questions,setQuestions] = useState<any[]>([]);
  const [editingQuestions,setEditingQuestions] = useState(false);
  const [questionReason,setQuestionReason] = useState('');
  const questionEditBase = useRef<string|null>(null);
  const [spans,setSpans] = useState<any[]>([]);
  const [conclusion,setConclusion] = useState('request_information');
  const [reason,setReason] = useState('');
  const requestNo = useRef(0);
  const dirtyRef = useRef(dirty);dirtyRef.current=dirty;
  const planEditBase = useRef<any>(null);
  const cardsKey = p.cards.map(card=>`${card.id}:${card.row_version}:${card.status}`).join('|');
  const previousCardsKey = useRef(cardsKey);
  async function loadRound(preservePreparation=false) {
    const request = ++requestNo.current;
    try { const data = await api.getInterviewRound(p.applicationId,p.roundNo);
      if(request!==requestNo.current) return;
      setState(data);
      planEditBase.current=preserveEditBase(planEditBase.current,data,preservePreparation&&dirtyRef.current);
      if(!preservePreparation||!dirtyRef.current) {setPrep(data.preparation);p.onFocus(data.preparation.focus_criterion_ids);setDirty(false);}
      setError('');
    }
    catch(e:any) {if(request===requestNo.current) setError(e.message || 'Không tải được kế hoạch phỏng vấn.');}
  }
  useEffect(()=>{void loadRound();return()=>{requestNo.current++;};},[p.applicationId,p.roundNo,p.rubric?.id,p.sourceKey]);
  useEffect(()=>{if(previousCardsKey.current!==cardsKey) {previousCardsKey.current=cardsKey;void loadRound(true);}},[cardsKey]);
  useEffect(()=>{ if(!editingQuestions) setQuestions(p.draft?.latest_revision?.followups || p.draft?.ai_followups || []); },[p.draft?.id,p.draft?.status,p.draft?.latest_revision?.id,editingQuestions]);
  useEffect(()=>{ if(p.canManage) api.getApprovedSpans(p.applicationId).then(setSpans).catch(()=>setSpans([])); },[p.applicationId,p.canManage,p.draft?.id]);
  function update(field:string,value:any) {setPrep((previous:any)=>({...previous,[field]:value}));setDirty(true);setNotice('');}
  function toggle(field:string,id:string) {update(field,prep[field].includes(id)?prep[field].filter((value:string)=>value!==id):[...prep[field],id]);}
  async function savePlan() {
    if(!state||!prep) return;
    setBusy(true);setError('');
    try { const data = await api.saveInterviewRound(p.applicationId,p.roundNo,{...prep,expected_version:planEditBase.current.row_version,source_hash:planEditBase.current.source_hash});
      setState(data);planEditBase.current=data;setPrep(data.preparation);setDirty(false);p.onFocus(data.preparation.focus_criterion_ids);setNotice('Đã lưu kế hoạch phỏng vấn.');await p.onRefresh(); }
    catch(e:any){setError(e.message);} finally{setBusy(false);}
  }
  async function saveQuestions() {
    if(!p.draft) return;
    setBusy(true);setError('');
    try{await api.saveInterviewRevision(p.draft.id,{expected_previous_revision_id:questionEditBase.current,followups:questions,change_reason:questionReason});
      setEditingQuestions(false);setQuestionReason('');await p.onRefresh();setNotice('Đã lưu phiên bản câu hỏi mới.');}
    catch(e:any){setError(e.message);}finally{setBusy(false);}
  }
  async function recordConclusion(e:React.FormEvent) {
    e.preventDefault();setBusy(true);setError('');
    try{const data=await api.concludeInterviewRound(p.applicationId,p.roundNo,{expected_version:state.row_version,outcome:conclusion,reason:reason.trim()});
      setState(data);setReason('');setNotice('Đã ghi kết luận của người phụ trách.');await p.onRefresh();}
    catch(e:any){setError(e.message);}finally{setBusy(false);}
  }
  const cards = p.cards.filter(card=>card.round_no===p.roundNo && card.rubric_version_id===p.rubric?.id);
  const summaries=interviewConsensus(p.rubric?.criteria || [],cards);
  const latest=state?.conclusions?.at(-1);
  const questionBusy=p.generating || (!p.draft?.is_stale && ['queued','running'].includes(p.draft?.status));
  const localDate=prep?.starts_at ? (()=>{const date=new Date(prep.starts_at);return new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16);})() : '';
  return <div className="interview-layout">
    <section className="card">
      <div className="card-header interview-header"><div><h2 className="card-title">Phỏng vấn theo năng lực</h2><p className="muted">Chuẩn bị trọng tâm, ghi nhận độc lập rồi tổng hợp để HR chốt bước tiếp theo.</p></div>
        <label className="form-label interview-round-picker">Lượt phỏng vấn<select aria-label="Lượt phỏng vấn" value={p.roundNo} disabled={p.dirty||dirty||busy||editingQuestions} onChange={e=>{p.setRoundNo(Number(e.target.value));setNotice('');setReason('');}}>{Array.from({length:10},(_,i)=>i+1).map(round=><option key={round} value={round}>Lượt {round}</option>)}</select></label>
      </div>
      <div className="tabs-container" role="tablist" aria-label="Các bước phỏng vấn" style={{marginBottom:0}}>
        {([['prepare','Chuẩn bị'],['record','Ghi nhận'],['summary','Tổng hợp']] as const).map(([key,label])=><button key={key} type="button" role="tab" aria-selected={view===key} className={`tab-btn ${view===key?'active':''}`} onClick={()=>setView(key)}>{label}</button>)}
      </div>
    </section>
    {error && <p role="alert" className="notice notice-error">{error} <button className="btn btn-secondary btn-sm" disabled={busy} onClick={()=>void loadRound()}>{dirty?'Bỏ thay đổi và tải lại':'Tải lại kế hoạch'}</button></p>}
    {notice && <p role="status" className="notice">{notice}</p>}
    {state?.is_stale && <p role="alert" className="notice notice-error">CV, JD hoặc tiêu chí đã đổi. Lượt cũ được giữ để kiểm toán; hãy mở lượt mới theo căn cứ hiện hành.</p>}
    {view==='prepare' && <>
      <section className="card"><h3>Kế hoạch buổi phỏng vấn</h3><p className="muted">Có thể chuẩn bị trước khi chốt mời. Điền lịch và địa điểm thực tế trước khi duyệt thư mời.</p>
        {prep ? <div className="workflow-form">
          <div className="interview-fields">
            <label>Tên buổi trao đổi<input className="form-input" value={prep.label} maxLength={120} onChange={e=>update('label',e.target.value)} disabled={!p.canManage||busy||state?.is_stale}/></label>
            <label>Thời gian · giờ trên thiết bị<input className="form-input" type="datetime-local" value={localDate} onChange={e=>update('starts_at',e.target.value?new Date(e.target.value).toISOString():null)} disabled={!p.canManage||busy||state?.is_stale}/></label>
            <label>Thời lượng (phút)<input type="number" min={15} max={180} value={prep.duration_minutes} onChange={e=>update('duration_minutes',Number(e.target.value))} disabled={!p.canManage||busy||state?.is_stale}/></label>
            <label>Hình thức<select value={prep.channel} onChange={e=>update('channel',e.target.value)} disabled={!p.canManage||busy||state?.is_stale}><option value="online">Trực tuyến</option><option value="onsite">Trực tiếp</option><option value="phone">Điện thoại</option></select></label>
            <label>Link / địa điểm / số liên hệ<input className="form-input" value={prep.meeting_location} maxLength={500} onChange={e=>update('meeting_location',e.target.value)} disabled={!p.canManage||busy||state?.is_stale} placeholder="Thông tin tham gia buổi trao đổi"/></label>
          </div>
          <strong>Năng lực trọng tâm của lượt này</strong><div className="interview-focus">{(p.rubric?.criteria||[]).map((criterion:any)=><label key={criterion.id}><input type="checkbox" checked={prep.focus_criterion_ids.includes(criterion.id)} onChange={()=>toggle('focus_criterion_ids',criterion.id)} disabled={!p.canManage||busy||state?.is_stale}/>{criterion.label || criterion.id}</label>)}</div>
          <strong>Người phỏng vấn</strong><div className="interview-focus">{(state?.members||[]).map((member:any)=><label key={member.id}><input type="checkbox" checked={prep.interviewer_ids.includes(member.id)} onChange={()=>toggle('interviewer_ids',member.id)} disabled={!p.canManage||busy||state?.is_stale}/>{member.display_name}</label>)}</div>
          <div className="interview-actions">{p.canManage && <button className="btn btn-primary" disabled={busy||!dirty||state?.is_stale||!prep.focus_criterion_ids.length||!prep.interviewer_ids.length} onClick={()=>void savePlan()}>{busy?'Đang lưu…':'Lưu kế hoạch'}</button>}{dirty&&<span className="muted">Có thay đổi chưa lưu.</span>}</div>
        </div> : <p className="muted">Đang tải kế hoạch…</p>}
      </section>
      <section className="card"><div className="card-header interview-header"><div><h3>Câu hỏi theo hồ sơ</h3><p className="muted">Câu hỏi chuẩn giữ nhất quán giữa ứng viên; AI gợi ý tối đa 3 câu làm rõ dựa trên CV và tiêu chí. Ngân hàng câu hỏi là tùy chọn.</p></div>
        {p.canManage && <button className="btn btn-secondary" disabled={questionBusy||state?.is_stale||!p.rubric||(p.draft?.status==='succeeded'&&!p.draft?.is_stale)} onClick={p.onGenerate}>{questionBusy?'Đang tạo câu hỏi…':p.draft?.status==='succeeded'&&!p.draft?.is_stale?'Đã có câu hỏi hiện hành':'Tạo câu hỏi gợi ý'}</button>}</div>
        {questionBusy&&<p role="status" className="notice">Hệ thống đang xử lý; câu hỏi sẽ tự cập nhật khi hoàn tất.</p>}
        {p.draft?.status==='failed'&&<p className="notice notice-error">Không tạo được câu hỏi. Có thể thử lại hoặc dùng câu hỏi chuẩn.</p>}
        {p.draft?.is_stale&&<p role="alert" className="notice notice-error">Bộ câu hỏi dùng căn cứ cũ. Hãy tạo lại trước khi sử dụng.</p>}
        {(p.draft?.core_questions||[]).map((q:any)=><article className="surface interview-question" key={q.question_id}><strong>Câu hỏi chung · {p.rubric?.criteria?.find((c:any)=>c.id===q.criterion_id)?.label||q.criterion_id}</strong><p>{q.question_vi}</p><small>{q.purpose_vi}</small></article>)}
        {questions.map((q:any,index:number)=><article className="surface interview-question" key={index}>
          <strong>{p.rubric?.criteria?.find((c:any)=>c.id===q.criterion_id)?.label||q.criterion_id}</strong>
          {editingQuestions?<><label className="form-label">Câu hỏi {index+1}<textarea value={q.question_vi} maxLength={600} onChange={e=>setQuestions(previous=>previous.map((item,i)=>i===index?{...item,question_vi:e.target.value}:item))}/></label><button className="btn btn-quiet btn-sm" onClick={()=>setQuestions(previous=>previous.filter((_,i)=>i!==index))}>Bỏ câu hỏi này</button></>:<p>{q.question_vi}</p>}
          <p className="muted">Mục đích: {q.purpose_vi}</p><small>Dấu hiệu cần tìm: {(q.answer_indicators||[]).join('; ')}</small>
          {!(q.source_span_ids||[]).length?<small className="muted">CV chưa cung cấp bằng chứng cho câu hỏi làm rõ này.</small>:<details><summary>Bằng chứng liên quan trong CV ({q.source_span_ids.length})</summary>{q.source_span_ids.map((id:string)=><blockquote key={id}>{spans.find(span=>span.span_id===id)?.quote || 'Mở CV đã che để đối chiếu nguồn được tham chiếu.'}</blockquote>)}</details>}
        </article>)}
        {!questions.length&&!questionBusy&&<p className="muted">Chưa có câu hỏi riêng. Bạn có thể tạo gợi ý từ đánh giá hiện hành.</p>}
        {p.canManage&&p.draft?.status==='succeeded'&&!p.draft?.is_stale&&<div className="workflow-form">
          {editingQuestions?<><label>Lý do chỉnh câu hỏi<textarea value={questionReason} maxLength={1000} onChange={e=>setQuestionReason(e.target.value)} placeholder="Giải thích vì sao sửa hoặc bỏ câu hỏi."/></label><div className="interview-actions"><button className="btn btn-primary" disabled={busy||questionReason.trim().length<10} onClick={()=>void saveQuestions()}>Lưu phiên bản câu hỏi</button><button className="btn btn-secondary" onClick={()=>setEditingQuestions(false)} disabled={busy}>Hủy sửa</button></div></>:<button className="btn btn-secondary" onClick={()=>{questionEditBase.current=p.draft.latest_revision?.id || null;setEditingQuestions(true);}}>Chọn và sửa câu hỏi</button>}
        </div>}
      </section>
    </>}
    <div hidden={view!=='record'}>{state?.id ? p.children : <section className="card"><p className="notice">Lưu kế hoạch với trọng tâm và người phỏng vấn trước khi ghi phiếu.</p><button className="btn btn-secondary" onClick={()=>setView('prepare')}>Chuẩn bị kế hoạch</button></section>}</div>
    {view==='summary'&&<section className="card"><h3>Tổng hợp sau phỏng vấn · Lượt {p.roundNo}</h3>
      {!p.cardsReady?<p className="notice">Chưa tải đủ phiếu hội đồng. <button className="btn btn-secondary btn-sm" onClick={()=>void p.onRefresh()}>Làm mới phiếu</button></p>:!state?.can_view_summary?<p className="notice">Người phỏng vấn chấm độc lập. Người phụ trách đang tham gia phỏng vấn cần nộp phiếu của mình trước khi xem phiếu người khác.</p>:<>
        <p className="muted">Điểm dưới đây do con người ghi nhận. Chênh lệch cần đối chiếu; không tự cộng với điểm AI để ra quyết định.</p>
        <div className="table-container"><table className="interview-summary"><thead><tr><th>Năng lực</th><th>Điểm ghi nhận</th><th>Cần rà soát</th></tr></thead><tbody>{summaries.map(row=><tr key={row.criterion_id}><td>{row.label}</td><td>{row.scores.length?row.scores.map(score=>`${score}/4`).join(' · '):'Chưa có điểm'}</td><td>{row.disagreement?'Chênh lệch lớn giữa người chấm':row.conflicting?'Có câu trả lời cần đối chiếu':row.unobserved?`${row.unobserved} phiếu chưa quan sát`:'—'}</td></tr>)}</tbody></table></div>
        {cards.filter(card=>card.status==='finalized').map(card=><details className="workflow-history" key={card.id}><summary>{card.interviewer_name||'Người phỏng vấn'} · Phiên bản {card.row_version}{card.is_stale?' · Căn cứ cũ':''}</summary>{card.criteria.map((entry:any)=><article key={entry.criterion_id}><strong>{p.rubric?.criteria?.find((c:any)=>c.id===entry.criterion_id)?.label||entry.criterion_id}</strong><p>{entry.answer_summary||'Chưa ghi nhận câu trả lời.'}</p>{entry.interviewer_note&&<p className="muted">{entry.interviewer_note}</p>}</article>)}</details>)}
        {latest&&<div className="surface workflow-result"><strong>Kết luận của người phụ trách: {latest.outcome==='advance'?'Tiếp tục vòng sau':outcomeLabels[latest.outcome]}</strong><p>{latest.reason}</p><small>{new Date(latest.created_at).toLocaleString('vi-VN')}</small></div>}
        {state?.conclusion_stale&&<p role="alert" className="notice">Phiếu hoặc nguồn đã thay đổi sau kết luận. Cần rà soát và ghi phiên bản kết luận mới.</p>}
        {p.canManage&&<form onSubmit={recordConclusion} className="workflow-form"><label>Bước tiếp theo sau phỏng vấn<select value={conclusion} onChange={e=>setConclusion(e.target.value)}><option value="advance">Tiếp tục vòng sau</option><option value="request_information">Cần thêm bằng chứng / trao đổi bổ sung</option><option value="not_advance">Không tiếp tục</option><option value="propose_hire">Đề xuất tuyển · chưa tạo offer</option></select></label>
          <label>Căn cứ kết luận<textarea rows={3} required minLength={20} maxLength={2000} value={reason} onChange={e=>setReason(e.target.value)}/></label>
          <p className="muted">Cần phiếu hiện hành của tất cả người được phân công. Mỗi kết luận lưu các phiên bản phiếu làm căn cứ.</p>
          <button className="btn btn-primary" disabled={busy||state?.is_stale||!state?.id||dirty||reason.trim().length<20}>Ghi kết luận sau phỏng vấn</button></form>}
        {(state?.conclusions||[]).length>1&&<details className="workflow-history"><summary>Lịch sử kết luận ({state.conclusions.length})</summary>{state.conclusions.map((item:any)=><article key={item.id}><strong>{item.outcome==='advance'?'Tiếp tục vòng sau':outcomeLabels[item.outcome]}</strong><p>{item.reason}</p><small>{new Date(item.created_at).toLocaleString('vi-VN')}</small></article>)}</details>}
      </>}
    </section>}
  </div>;
}
