'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api, RequisitionItem, UserAccount } from '../lib/api';
import { IconAlertTriangle, IconArrowRight, IconCheckCircle, IconFileText, IconPlus, IconRefresh, IconUserCheck } from './Icons';
import { stageLabels } from '../lib/workflow';
import { Skeleton } from './Skeleton';

type ReviewItem = { id: string; public_label: string; received_at: string; requisitionTitle: string; stage: string; independent?: boolean };

const statusLabel: Record<RequisitionItem['status'], string> = {
  draft: 'Bản nháp', open: 'Đang mở', paused: 'Tạm dừng', closed: 'Đã đóng',
};

export default function DashboardHome({ user, requisitions, error, onReload }: {
  user: UserAccount;
  requisitions: RequisitionItem[];
  error: string;
  onReload: () => Promise<void>;
}) {
  const reviewerOnly = requisitions.length > 0 && requisitions.every(item => item.my_role === "reviewer");
  const [queueFilter, setQueueFilter] = useState("");
  const [refreshTick, setRefreshTick] = useState(0);
  const [reviewItems, setReviewItems] = useState<ReviewItem[]>([]);
  const [reviewLoading, setReviewLoading] = useState(true);
  const [reviewLoadError, setReviewLoadError] = useState(false);

  useEffect(() => {
    let active = true;
    async function loadReviewQueue() {
      const recentOpen = requisitions.filter((item) => ['open', 'paused'].includes(item.status));
      if (!recentOpen.length) {
        if (active) { setReviewItems([]); setReviewLoadError(false); setReviewLoading(false); }
        return;
      }
      if (refreshTick === 0) setReviewLoading(true);
      const results = await Promise.allSettled(recentOpen.map(async (item): Promise<ReviewItem[]> => item.my_role === "reviewer"
        ? (await api.getIndependentReviewWorklist(item.id)).filter(app => !app.submitted).map(app => ({ id: app.application_id, public_label: app.public_label, received_at: app.received_at, requisitionTitle: item.title, stage: app.ready ? "independent_ready" : "independent_waiting", independent: true }))
        : (await api.getReviewQueue(item.id)).filter(app => app.workflow_stage !== "completed").map(app => ({ id: app.application_id, public_label: app.public_label, received_at: app.received_at, requisitionTitle: item.title, stage: app.workflow_stage || "unknown" }))));
      if (!active) return;
      setReviewLoadError(results.some((result) => result.status === 'rejected'));
      const items = results.flatMap(result => result.status === 'fulfilled' ? result.value : []);
      setReviewItems(items.sort((a, b) => new Date(a.received_at).getTime() - new Date(b.received_at).getTime()));
      setReviewLoading(false);
    }
    void loadReviewQueue();
    return () => { active = false; };
  }, [requisitions, refreshTick]);

  useEffect(() => { const timer = window.setInterval(() => { if (document.visibilityState === "visible") setRefreshTick(previous => previous + 1); }, 15000); return () => window.clearInterval(timer); }, []);

  const openCount = requisitions.filter((item) => item.status === 'open').length;
  const draftCount = requisitions.filter((item) => item.status === 'draft').length;

  const visibleItems = reviewItems.filter(item => !queueFilter || item.stage === queueFilter);
  const queueStages = reviewerOnly ? ["independent_ready", "independent_waiting"]
    : Array.from(new Set(reviewItems.map(item => item.stage)));
  const labelForStage = (stage: string) => stage === "independent_ready" ? "Chờ chấm độc lập"
    : stage === "independent_waiting" ? "Chờ rà soát CV" : stageLabels[stage] || "Chưa xác định";

  return (
    <div className="dashboard-page">
      <div className="page-header dashboard-heading">
        <div><p className="eyebrow">Không gian nhân sự</p><h1 className="page-title">Tổng quan tuyển dụng</h1><p className="page-subtitle">Chào {user.display_name}. Đây là những công việc cần bạn chú ý.</p></div>
        <Link className="btn btn-primary" href="/requisitions"><IconPlus size={17} />Mở đợt tuyển dụng</Link>
      </div>
      {error && <div className="notice notice-error" role="alert"><IconAlertTriangle size={17} /><span>{error}</span><button className="btn btn-sm btn-outline" onClick={() => void onReload()}>Thử lại</button></div>}
      <section className="overview-metrics" aria-label="Tổng quan dữ liệu tuyển dụng">
        <div className="overview-metric metric-priority"><div><span>{reviewerOnly ? "Chờ bạn chấm độc lập" : "Hồ sơ cần xử lý"}</span><IconUserCheck size={19} /></div><strong>{reviewLoading || reviewLoadError ? "—" : reviewItems.length}</strong><p>{reviewLoadError ? "Một số đợt chưa tải được" : "Trong các đợt đang mở và tạm dừng"}</p></div>
        <div className="overview-metric"><div><span>Đợt đang mở</span><IconFileText size={19} /></div><strong>{openCount}</strong><p>Tiếp nhận và rà soát hồ sơ</p></div>
        <div className="overview-metric"><div><span>Đợt ở bản nháp</span><IconFileText size={19} /></div><strong>{draftCount}</strong><p>Chờ hoàn tất JD và tiêu chí</p></div>
      </section>
      <div className="overview-grid">
        <section className="surface queue-panel" aria-labelledby="review-queue-title">
          <div className="panel-heading"><div><h2 id="review-queue-title">{reviewerOnly ? "Hồ sơ được phân công" : "Hàng đợi công việc"}</h2><p>Ưu tiên theo thời gian tiếp nhận.</p></div><button type="button" className="btn btn-quiet btn-sm" aria-label="Làm mới hàng đợi" onClick={() => setRefreshTick(previous => previous + 1)}><IconRefresh size={16} /><span>Làm mới</span></button></div>
          <div className="queue-toolbar"><label htmlFor="queue-filter">Trạng thái</label><select id="queue-filter" className="form-select" value={queueFilter} onChange={event => setQueueFilter(event.target.value)}><option value="">Tất cả trạng thái</option>{Array.from(new Set([...queueStages, ...(queueFilter ? [queueFilter] : [])])).map(stage => <option key={stage} value={stage}>{labelForStage(stage)} ({reviewItems.filter(item => item.stage === stage).length})</option>)}</select><span>{reviewLoading ? "Đang tải…" : `${visibleItems.length} hồ sơ`}</span></div>
          {reviewLoadError && <div className="notice notice-warning" role="status"><IconAlertTriangle size={16} /><span>Chưa tải được một số đợt. Mở từng đợt để kiểm tra đầy đủ.</span></div>}
          {reviewLoading ? <div className="queue-loading" role="status" aria-label="Đang tải hàng đợi"><Skeleton height="72px" /><Skeleton height="72px" /><Skeleton height="72px" /></div>
            : visibleItems.length === 0 ? <div className="empty-work"><span className="empty-icon"><IconCheckCircle size={25} /></span><h3>{queueFilter ? "Không có hồ sơ ở trạng thái này" : "Chưa có hồ sơ cần xử lý"}</h3><p>{queueFilter ? "Chọn trạng thái khác để tiếp tục rà soát." : "Mở một đợt tuyển dụng để tiếp nhận và xem hồ sơ."}</p>{queueFilter ? <button className="btn btn-secondary" onClick={() => setQueueFilter("")}>Xem tất cả trạng thái</button> : <Link href="/requisitions" className="btn btn-secondary">Xem đợt tuyển dụng<IconArrowRight size={15} /></Link>}</div>
            : <div className="review-list">{visibleItems.slice(0, 8).map(item => <Link key={item.id} href={`/applications/${item.id}${item.independent ? "/independent-review" : ""}`} className="review-row"><span className="candidate-avatar">{item.public_label.slice(-2)}</span><span className="review-copy"><strong>{item.public_label}</strong><small>{item.requisitionTitle}</small><time dateTime={item.received_at}>{new Date(item.received_at).toLocaleDateString("vi-VN")}</time></span><span className={`review-state review-state-${item.stage}`}>{labelForStage(item.stage)}</span><IconArrowRight size={16} /></Link>)}</div>}
          {visibleItems.length > 8 && <p className="queue-footnote">Đang hiển thị 8 hồ sơ đầu. Mở từng đợt tuyển dụng để xem đầy đủ.</p>}
        </section>
        <aside className="surface recent-panel" aria-labelledby="recent-requisitions-title"><div className="panel-heading"><div><h2 id="recent-requisitions-title">Đợt tuyển dụng gần đây</h2><p>{requisitions.length} đợt bạn được truy cập</p></div></div>
          {requisitions.length === 0 ? <div className="recent-empty"><IconFileText size={25} /><p>Chưa có đợt tuyển dụng.</p></div> : requisitions.slice(0, 5).map(req => <Link href={`/requisitions/${req.id}`} className="recent-requisition" key={req.id}><span className="recent-requisition-icon"><IconFileText size={19} /></span><div className="recent-req-info"><strong>{req.title}</strong><small><span className={`status-marker status-${req.status}`} />{statusLabel[req.status]}</small></div><IconArrowRight size={15} /></Link>)}
          <Link className="recent-panel-all" href="/requisitions">Xem tất cả đợt<IconArrowRight size={15} /></Link>
        </aside>
      </div>
    </div>
  );
}
