'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api, ApplicationItem, RequisitionItem, UserAccount } from '../lib/api';
import { IconAlertTriangle, IconArrowRight, IconCheckCircle, IconFileText, IconPlus, IconShield, IconSparkles, IconUserCheck } from './Icons';
import { stageLabels } from '../lib/workflow';
import { Skeleton } from './Skeleton';

type ReviewItem = { id: string; public_label: string; received_at: string; requisitionTitle: string; stage: string; independent?: boolean };

const statusLabel: Record<RequisitionItem['status'], string> = {
  draft: 'Bản nháp', open: 'Đang mở', paused: 'Tạm dừng', closed: 'Đã đóng',
};

export default function DashboardHome({ user, requisitions, onLogout, error, onReload }: {
  user: UserAccount;
  requisitions: RequisitionItem[];
  onLogout: () => Promise<void>;
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
        if (active) { setReviewItems([]); setReviewLoading(false); }
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

  return (
    <div className="dashboard-page">
      <section className="dashboard-intro surface">
        <div>
          <div className="eyebrow"><span className="intro-dot" /> Không gian tuyển dụng</div>
          <h1>Chào {user.display_name}</h1>
          <p>Chọn một đợt tuyển dụng để kiểm tra JD, tiêu chí và hồ sơ. Mọi kết quả AI đều cần HR rà soát.</p>
        </div>
        <div className="intro-actions">
          <span className="account-chip"><span className="account-avatar">{user.display_name?.slice(0, 1).toUpperCase() || 'H'}</span>{user.login_name}</span>
          <button type="button" className="btn btn-outline btn-sm" onClick={() => void onLogout()}>Đăng xuất</button>
        </div>
      </section>

      {error && <div className="notice notice-error" role="alert"><IconAlertTriangle size={17} />{error}<button className="btn btn-sm btn-outline" onClick={() => void onReload()}>Thử lại</button></div>}

      <div className="dashboard-grid">
        <aside className="surface dashboard-sidebar" aria-label="Điều hướng công việc">
          <div className="panel-heading"><div><p className="eyebrow">Điều hướng</p><h2>Trung tâm công việc</h2></div><span className="tiny-count">{requisitions.length} đợt</span></div>
          <div className="sidebar-menu">
            <Link className="sidebar-link active" href="/requisitions">
              <IconFileText size={18} className="sidebar-link-icon" />
              <div className="sidebar-link-text">
                <strong>Đợt tuyển dụng</strong>
                <small>JD, tiêu chí và hồ sơ</small>
              </div>
              <IconArrowRight size={15} className="sidebar-link-arrow" />
            </Link>
            <Link className="sidebar-link" href="/retention">
              <IconShield size={18} className="sidebar-link-icon" />
              <div className="sidebar-link-text">
                <strong>Lưu giữ dữ liệu</strong>
                <small>Thời hạn và yêu cầu xóa</small>
              </div>
              <IconArrowRight size={15} className="sidebar-link-arrow" />
            </Link>
          </div>
          <div className="sidebar-divider" />
          <p className="eyebrow sidebar-section-title">Thực hành &amp; Tập huấn</p>
          <div className="sidebar-menu" style={{ marginBottom: "0.5rem" }}>
            <Link className="sidebar-link" href="/sandbox">
              <IconSparkles size={18} className="sidebar-link-icon" />
              <div className="sidebar-link-text">
                <strong>Tập huấn HR (Sandbox)</strong>
                <small>Thực hành trên dữ liệu mẫu</small>
              </div>
              <IconArrowRight size={15} className="sidebar-link-arrow" />
            </Link>
          </div>
          <div className="sidebar-divider" />
          <p className="eyebrow sidebar-section-title">Đợt gần đây</p>
          {requisitions.length === 0 ? <p className="muted sidebar-empty">Chưa có đợt tuyển dụng.</p> : requisitions.slice(0, 4).map((req) => (
            <Link href={`/requisitions/${req.id}`} className="recent-requisition" key={req.id}>
              <span className={`status-marker status-${req.status}`} />
              <div className="recent-req-info">
                <strong className="recent-req-title">{req.title}</strong>
                <small className="recent-req-status">{statusLabel[req.status]}</small>
              </div>
              <IconArrowRight size={14} className="recent-req-arrow" />
            </Link>
          ))}
          <Link className="sidebar-all" href="/requisitions">Xem tất cả đợt <IconArrowRight size={15} /></Link>
        </aside>

        <div className="dashboard-main">
          <section className="metrics-row" aria-label="Tổng quan dữ liệu tuyển dụng">
            <div className="surface metric-tile"><span>Đợt đang mở</span><strong>{openCount}</strong><small>Đang tiếp nhận hoặc rà soát hồ sơ</small></div>
            <div className="surface metric-tile"><span>Bản nháp</span><strong>{draftCount}</strong><small>Cần hoàn tất JD và tiêu chí</small></div>
            <div className="surface metric-tile"><span>{reviewerOnly ? "Hồ sơ chưa khóa nhãn của bạn" : "Hồ sơ cần xử lý"}</span><strong>{reviewLoading || reviewLoadError ? '—' : reviewItems.length}</strong><small>{reviewLoadError ? 'Một số đợt chưa tải được' : 'Tất cả đợt đang mở hoặc tạm dừng bạn được truy cập'}</small></div>
          </section>

          <section className="surface work-panel">
            <div className="workflow-actions" aria-label="Lọc công việc"><button className="btn btn-secondary btn-sm" onClick={() => setQueueFilter("")}>Tất cả ({reviewItems.length})</button>{(reviewerOnly ? ["independent_ready", "independent_waiting"] : ["needs_review", "reading", "ready_for_ai", "analyzing", "awaiting_decision", "error", "independent_ready"]).map(stage => <button key={stage} aria-pressed={queueFilter === stage} className="btn btn-secondary btn-sm" onClick={() => setQueueFilter(stage)}>{(stage === "independent_ready" ? "Sẵn sàng chấm độc lập" : stage === "independent_waiting" ? "Chờ CV được rà soát" : stageLabels[stage])} ({reviewItems.filter(item => item.stage === stage).length})</button>)}<button className="btn btn-secondary btn-sm" onClick={() => setRefreshTick(previous => previous + 1)}>Làm mới</button></div>
            <div className="panel-heading"><div><p className="eyebrow">Ưu tiên xử lý</p><h2>{reviewerOnly ? "Hồ sơ cần bạn chấm độc lập" : "Hồ sơ cần HR rà soát"}</h2><p className="muted">Sắp theo thời gian tiếp nhận. Số liệu gồm các đợt đang mở/tạm dừng tải được; hiển thị tối đa 5 hồ sơ theo bộ lọc.</p></div><span className="panel-icon"><IconUserCheck size={20} /></span></div>
            {reviewLoadError && <div className="notice notice-warning" role="status"><IconAlertTriangle size={16} />Một số danh sách hồ sơ chưa tải được. Mở từng đợt để kiểm tra đầy đủ.</div>}
            {reviewLoading ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', padding: '0.5rem 0' }} role="status">
                <Skeleton height="54px" borderRadius="12px" />
                <Skeleton height="54px" borderRadius="12px" />
                <Skeleton height="54px" borderRadius="12px" />
              </div>
            ) : reviewItems.length === 0 ? (
              <div className="empty-work"><span className="empty-icon"><IconCheckCircle size={24} /></span><h3>Chưa có hồ sơ trong danh sách ưu tiên</h3><p>Mở một đợt tuyển dụng để xem toàn bộ hồ sơ và tiến độ đánh giá.</p><Link href="/requisitions" className="btn btn-secondary">Xem đợt tuyển dụng <IconArrowRight size={15} /></Link></div>
            ) : queueFilter && !reviewItems.some(item => item.stage === queueFilter) ? <p className="notice">Không có hồ sơ ở trạng thái đã chọn. Chọn “Tất cả” để xem công việc khác.</p> : <div className="review-list">{reviewItems.filter(item => !queueFilter || item.stage === queueFilter).slice(0, 5).map((item) => <Link key={item.id} href={`/applications/${item.id}${item.independent ? "/independent-review" : ""}`} className="review-row"><span className="candidate-avatar">{item.public_label.slice(-2)}</span><span className="review-copy"><strong>{item.public_label}</strong><small>{item.requisitionTitle} · Tiếp nhận {new Date(item.received_at).toLocaleDateString('vi-VN')}</small></span><span className="review-state">{(item.stage === "independent_ready" ? "Sẵn sàng chấm độc lập" : item.stage === "independent_waiting" ? "Chờ CV được rà soát" : stageLabels[item.stage]) || 'Chưa xác định'}</span><IconArrowRight size={16} /></Link>)}</div>}
          </section>

          <section className="human-note"><IconShield size={18} /><span><strong>Nguyên tắc quyết định</strong> — Điểm AI là quan sát theo bằng chứng hiện có, không phải điểm năng lực tuyệt đối. HR có thể yêu cầu làm rõ hoặc ghi đè kèm lý do.</span></section>
        </div>

        <aside className="dashboard-rail" aria-label="Các bước tiếp theo">
          <section className="surface action-panel"><div className="panel-heading"><div><p className="eyebrow">Thao tác nhanh</p><h2>Bắt đầu từ đợt tuyển dụng</h2></div><span className="panel-icon"><IconPlus size={19} /></span></div><p className="muted">Tạo JD, chuẩn bị tiêu chí, rồi tiếp nhận CV trong cùng một không gian.</p><Link className="btn btn-primary action-main" href="/requisitions"><IconPlus size={16} />Tạo hoặc mở đợt</Link><div className="action-steps"><div><span>01</span><p><strong>Kiểm tra JD và tiêu chí</strong><small>HR và chuyên môn IT duyệt trước khi dùng.</small></p></div><div><span>02</span><p><strong>Tiếp nhận và khử định danh</strong><small>Kiểm tra bản đã che trước khi đánh giá.</small></p></div><div><span>03</span><p><strong>Rà soát bằng chứng</strong><small>HR ký quyết định cuối cùng.</small></p></div></div></section>
          <section className="surface help-panel"><span className="help-icon"><IconSparkles size={19} /></span><div><h2>Mới sử dụng TalentScreen?</h2><p>Thử quy trình trên hồ sơ mẫu trước khi làm việc với dữ liệu thật.</p><Link href="/sandbox">Vào phần tập huấn <IconArrowRight size={15} /></Link></div></section>
        </aside>
      </div>
    </div>
  );
}
