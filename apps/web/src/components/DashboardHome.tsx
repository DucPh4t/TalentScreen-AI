'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api, ApplicationItem, RequisitionItem, UserAccount } from '../lib/api';
import { IconAlertTriangle, IconArrowRight, IconCheckCircle, IconFileText, IconPlus, IconShield, IconSparkles, IconUserCheck } from './Icons';
import { Skeleton } from './Skeleton';

type ReviewItem = ApplicationItem & { requisitionTitle: string };

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
  const [reviewItems, setReviewItems] = useState<ReviewItem[]>([]);
  const [reviewLoading, setReviewLoading] = useState(true);
  const [reviewLoadError, setReviewLoadError] = useState(false);

  useEffect(() => {
    let active = true;
    async function loadReviewQueue() {
      const recentOpen = requisitions.filter((item) => item.status === 'open').slice(0, 6);
      if (!recentOpen.length) {
        if (active) { setReviewItems([]); setReviewLoading(false); }
        return;
      }
      setReviewLoading(true);
      const results = await Promise.allSettled(recentOpen.map((item) => api.listApplications(item.id)));
      if (!active) return;
      setReviewLoadError(results.some((result) => result.status === 'rejected'));
      const items = results.flatMap((result, index) => result.status === 'fulfilled'
        ? result.value.filter((app) => app.status === 'active' && !app.current_decision_id)
          .map((app) => ({ ...app, requisitionTitle: recentOpen[index].title }))
        : []);
      setReviewItems(items.sort((a, b) => new Date(a.received_at).getTime() - new Date(b.received_at).getTime()).slice(0, 5));
      setReviewLoading(false);
    }
    void loadReviewQueue();
    return () => { active = false; };
  }, [requisitions]);

  const openCount = requisitions.filter((item) => item.status === 'open').length;
  const draftCount = requisitions.filter((item) => item.status === 'draft').length;

  return (
    <div className="dashboard-page">
      <section className="dashboard-intro surface">
        <div>
          <div className="eyebrow"><span className="intro-dot" /> Không gian tuyển dụng</div>
          <h1>Chào {user.display_name}</h1>
          <p>Chọn một đợt tuyển dụng để kiểm tra JD, rubric và hồ sơ. Mọi kết quả AI đều cần HR rà soát.</p>
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
                <small>JD, rubric và hồ sơ</small>
              </div>
              <IconArrowRight size={15} className="sidebar-link-arrow" />
            </Link>
            <Link className="sidebar-link" href="/sandbox">
              <IconSparkles size={18} className="sidebar-link-icon" />
              <div className="sidebar-link-text">
                <strong>Tập huấn HR</strong>
                <small>Thực hành trên dữ liệu mẫu</small>
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
            <div className="surface metric-tile"><span>Bản nháp</span><strong>{draftCount}</strong><small>Cần hoàn tất JD và rubric</small></div>
            <div className="surface metric-tile"><span>Hồ sơ hiển thị</span><strong>{reviewLoading || reviewLoadError ? '—' : reviewItems.length}</strong><small>{reviewLoadError ? 'Một số đợt chưa tải được' : 'Tối đa 5 hồ sơ từ 6 đợt gần đây'}</small></div>
          </section>

          <section className="surface work-panel">
            <div className="panel-heading"><div><p className="eyebrow">Ưu tiên xử lý</p><h2>Hồ sơ cần HR rà soát</h2><p className="muted">Sắp theo thời gian tiếp nhận. Số liệu chỉ gồm các đợt tải được.</p></div><span className="panel-icon"><IconUserCheck size={20} /></span></div>
            {reviewLoadError && <div className="notice notice-warning" role="status"><IconAlertTriangle size={16} />Một số danh sách hồ sơ chưa tải được. Mở từng đợt để kiểm tra đầy đủ.</div>}
            {reviewLoading ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', padding: '0.5rem 0' }} role="status">
                <Skeleton height="54px" borderRadius="12px" />
                <Skeleton height="54px" borderRadius="12px" />
                <Skeleton height="54px" borderRadius="12px" />
              </div>
            ) : reviewItems.length === 0 ? (
              <div className="empty-work"><span className="empty-icon"><IconCheckCircle size={24} /></span><h3>Chưa có hồ sơ trong danh sách ưu tiên</h3><p>Mở một đợt tuyển dụng để xem toàn bộ hồ sơ và tiến độ đánh giá.</p><Link href="/requisitions" className="btn btn-secondary">Xem đợt tuyển dụng <IconArrowRight size={15} /></Link></div>
            ) : <div className="review-list">{reviewItems.map((item) => <Link key={item.id} href={`/applications/${item.id}`} className="review-row"><span className="candidate-avatar">{item.public_label.slice(-2)}</span><span className="review-copy"><strong>{item.public_label}</strong><small>{item.requisitionTitle} · Tiếp nhận {new Date(item.received_at).toLocaleDateString('vi-VN')}</small></span><span className="review-state">{item.current_assessment_run_id ? 'Xem đánh giá' : 'Chưa có đánh giá'}</span><IconArrowRight size={16} /></Link>)}</div>}
          </section>

          <section className="human-note"><IconShield size={18} /><span><strong>Nguyên tắc quyết định</strong> — Điểm AI là quan sát theo bằng chứng hiện có, không phải điểm năng lực tuyệt đối. HR có thể yêu cầu làm rõ hoặc ghi đè kèm lý do.</span></section>
        </div>

        <aside className="dashboard-rail" aria-label="Các bước tiếp theo">
          <section className="surface action-panel"><div className="panel-heading"><div><p className="eyebrow">Thao tác nhanh</p><h2>Bắt đầu từ đợt tuyển dụng</h2></div><span className="panel-icon"><IconPlus size={19} /></span></div><p className="muted">Tạo JD, chuẩn bị rubric, rồi tiếp nhận CV trong cùng một không gian.</p><Link className="btn btn-primary action-main" href="/requisitions"><IconPlus size={16} />Tạo hoặc mở đợt</Link><div className="action-steps"><div><span>01</span><p><strong>Kiểm tra JD và rubric</strong><small>HR và chuyên môn IT duyệt trước khi dùng.</small></p></div><div><span>02</span><p><strong>Tiếp nhận và khử định danh</strong><small>Kiểm tra bản đã che trước khi đánh giá.</small></p></div><div><span>03</span><p><strong>Rà soát bằng chứng</strong><small>HR ký quyết định cuối cùng.</small></p></div></div></section>
          <section className="surface help-panel"><span className="help-icon"><IconSparkles size={19} /></span><div><h2>Mới sử dụng TalentScreen?</h2><p>Thử quy trình trên hồ sơ mẫu trước khi làm việc với dữ liệu thật.</p><Link href="/sandbox">Vào phần tập huấn <IconArrowRight size={15} /></Link></div></section>
        </aside>
      </div>
    </div>
  );
}
