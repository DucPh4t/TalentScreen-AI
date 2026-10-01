'use client';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { api } from '../lib/api';
import { toast } from './Toast';

type Item = { id: string; file: File; status: 'queued' | 'uploading' | 'success' | 'error'; applicationId?: string; error?: string };
export default function BatchDropzone({ requisitionId, onUploadComplete, onBusyChange }: {
  requisitionId: string; onUploadComplete: () => Promise<void> | void; onClose?: () => void; onBusyChange?: (busy: boolean) => void;
}) {
  const [items, setItems] = useState<Item[]>([]);
  const [busy, setBusy] = useState(false);
  const [attempted, setAttempted] = useState(0);
  const [batchTotal, setBatchTotal] = useState(0);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const running = useRef(false);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (running.current) { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, []);
  const add = useCallback((files: FileList | File[]) => {
    if (running.current) return;
    const accepted: Item[] = [];
    for (const file of Array.from(files)) {
      if (!/\.(pdf|docx)$/i.test(file.name)) { toast.warning('Chỉ nhận PDF hoặc DOCX.'); continue; }
      if (file.size > 10 * 1024 * 1024 || !file.size) { toast.warning('Mỗi CV phải có nội dung và không quá 10 MB.'); continue; }
      if ([...items, ...accepted].some(x => x.file.name === file.name && x.file.size === file.size && x.file.lastModified === file.lastModified)) continue;
      if (items.length + accepted.length >= 20) { toast.warning('Tối đa 20 tệp trong một lượt.'); break; }
      accepted.push({ id: crypto.randomUUID(), file, status: 'queued' });
    }
    setItems(previous => [...previous, ...accepted]);
  }, [items]);
  const patch = (id: string, changes: Partial<Item>) => setItems(previous => previous.map(item => item.id === id ? { ...item, ...changes } : item));
  async function upload() {
    if (running.current) return;
    const pending = items.filter(x => x.status === 'queued' || x.status === 'error');
    if (!pending.length) return;
    running.current = true; setBusy(true); onBusyChange?.(true); setAttempted(0); setBatchTotal(pending.length);
    let succeeded = 0;
    try {
      const user = await api.getMe();
      for (const [index, item] of pending.entries()) {
        patch(item.id, { status: 'uploading', error: undefined });
        try {
          const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', await item.file.arrayBuffer()))).map(n => n.toString(16).padStart(2, '0')).join('');
          // Only a hash and opaque IDs are kept for retry. No CV, filename or quote is cached.
          const key = `ts-upload:${user.id}:${requisitionId}:${digest}`;
          let record: { applicationId?: string; token: string };
          try { record = JSON.parse(sessionStorage.getItem(key) || 'null') || { token: crypto.randomUUID() }; }
          catch { record = { token: crypto.randomUUID() }; }
          sessionStorage.setItem(key, JSON.stringify(record));
          let applicationId = item.applicationId || record.applicationId;
          if (!applicationId) {
            const created = await api.createApplication(requisitionId, record.token);
            applicationId = created.id; record.applicationId = applicationId;
            sessionStorage.setItem(key, JSON.stringify(record));
          }
          patch(item.id, { applicationId });
          await api.uploadDocument(applicationId, item.file, record.token);
          patch(item.id, { status: 'success' }); succeeded++;
        } catch (reason) { patch(item.id, { status: 'error', error: reason instanceof Error ? reason.message : 'Không tải được tệp. Hãy thử lại.' }); }
        setAttempted(index + 1);
      }
      if (succeeded === pending.length) toast.success(`Đã tải lên ${succeeded} CV. Hệ thống sẽ đọc tệp; HR cần rà soát trước khi chạy AI.`);
      else toast.warning(`Đã tải lên ${succeeded}/${pending.length} CV. Thử lại các tệp lỗi sẽ dùng đúng hồ sơ cũ.`);
    } catch (reason) { toast.error(reason instanceof Error ? reason.message : 'Không xác thực được phiên làm việc.'); }
    finally { running.current = false; setBusy(false); onBusyChange?.(false); }
    await onUploadComplete();
  }
  const pending = items.filter(x => x.status !== 'success').length;
  return <section className="upload-panel">
    <div className={`upload-drop ${dragging ? 'is-dragging' : ''}`} onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); add(e.dataTransfer.files); }}>
      <h3>Tải lên CV · PDF hoặc DOCX</h3><p>Tối đa 20 tệp/lượt, 10 MB/tệp. Kéo thả hoặc chọn từ máy tính.</p>
      <input ref={input} type="file" aria-label="Chọn tệp CV" multiple accept=".pdf,.docx" disabled={busy} onChange={e => { if (e.target.files) add(e.target.files); e.target.value = ''; }} />
    </div>
    <p className="muted">Tải lên chưa phải kết quả đánh giá. Bạn có thể theo dõi việc đọc tệp trong danh sách hồ sơ. Nếu tải lại trang, chọn lại cùng tệp để tiếp tục an toàn trong phiên đăng nhập này.</p>
    {!!items.length && <>
      <div className="workflow-actions"><strong>{items.length} tệp · {items.filter(x => x.status === 'success').length} đã tải lên</strong>
        <button className="btn btn-primary" disabled={busy || !pending} onClick={() => void upload()}>{busy ? `Đang tải lên · đã thử ${attempted}/${batchTotal}` : items.some(x => x.status === 'error') ? 'Thử lại tệp lỗi / tải tệp chờ' : pending ? `Tải lên ${pending} CV` : 'Đã tải lên tất cả'}</button>
        <button className="btn btn-secondary" disabled={busy} onClick={() => setItems([])}>Dọn danh sách tệp</button>
      </div>
      <div role="status" aria-live="polite">{busy ? 'Đang tải lên. Vui lòng giữ trang mở.' : 'Bạn có thể theo dõi xử lý trong danh sách hồ sơ.'}</div>
      <ul className="upload-files">{items.map(item => <li key={item.id}>
        <div><strong>{item.file.name}</strong><small>{(item.file.size / 1024).toFixed(0)} KB</small></div>
        <span>{({ queued: 'Chờ tải', uploading: 'Đang tải lên', success: 'Đã tải lên · chờ đọc tệp', error: 'Tải lên thất bại' })[item.status]}</span>
        {item.error && <p role="alert">{item.error}</p>}
        {item.applicationId && <Link href={`/applications/${item.applicationId}`} onClick={e => { if (busy) e.preventDefault(); }}>Theo dõi hồ sơ</Link>}
        {!busy && item.status === 'queued' && <button className="btn btn-secondary btn-sm" onClick={() => setItems(previous => previous.filter(x => x.id !== item.id))}>Bỏ tệp</button>}
      </li>)}</ul>
    </>}
  </section>;
}
