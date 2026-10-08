"use client";

import Link from 'next/link';
import type { ApplicationItem, ReviewQueueItem } from '@/lib/api';
import { applicationNextTask } from '@/lib/application-list';
import { IconArrowRight, IconFileText, IconAlertTriangle, IconSearch } from '@/components/Icons';

type Props = {
  applications: ApplicationItem[];
  queue: ReviewQueueItem[];
  queueUnavailable: boolean;
  independent: boolean;
  onResetFilters: () => void;
};

function PrivacyState({ item, unavailable }: { item?: ReviewQueueItem; unavailable: boolean }) {
  if (unavailable || !item) return <span className="candidate-secondary">Chưa tải được trạng thái CV</span>;
  return <div className="candidate-privacy">
    <span className="candidate-secondary">{item.sanitized_status === 'approved' ? 'CV đã che được duyệt' : item.sanitized_status === 'draft' ? 'CV đã che chờ rà soát' : 'CV chưa sẵn sàng'}</span>
    {item.is_duplicate && <span className="candidate-flag" title="Tệp hoặc liên hệ trùng với hồ sơ bạn có quyền xem. Cần kiểm tra; không tự gộp hay thay đổi điểm."><IconAlertTriangle size={13} />Nghi trùng · {item.application_history_count || 2} hồ sơ</span>}
    {item.risk_flags.includes('contact_data') && <span className="candidate-flag candidate-flag--danger">Cần kiểm tra thông tin liên hệ</span>}
    {item.risk_flags.includes('parse_quality') && <span className="candidate-flag">Cần kiểm tra trích xuất</span>}
  </div>;
}

function NextTask({ application, item, independent }: { application: ApplicationItem; item?: ReviewQueueItem; independent: boolean }) {
  const task = applicationNextTask(application, item, independent);
  return <div className="candidate-task">
    <span className={`candidate-task-label candidate-task-label--${task.tone}`}><span aria-hidden="true" />{task.label}</span>
    <span className="candidate-secondary">{task.hint}</span>
    {!independent && item?.workflow_stage === 'awaiting_decision' && item.sla_breached && <span className="candidate-flag"><IconAlertTriangle size={13} />Chờ HR {Math.floor(item.hours_in_stage || 0)} giờ · quá 72 giờ</span>}
  </div>;
}

function OpenApplication({ application, independent }: { application: ApplicationItem; independent: boolean }) {
  if (application.status !== 'active') return <span className="candidate-secondary">Không khả dụng</span>;
  return <Link className="btn btn-outline btn-sm candidate-open" href={`/applications/${application.id}${independent ? '/independent-review' : ''}`} aria-label={`${independent ? 'Chấm độc lập' : 'Xem hồ sơ'} ${application.public_label}`}>
    {independent ? 'Chấm độc lập' : 'Xem hồ sơ'}<IconArrowRight size={14} />
  </Link>;
}

function ReceivedAt({ date }: { date: string }) {
  const value = new Date(date);
  return <time className="candidate-date" dateTime={date}>
    {value.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' })}
    <span className="candidate-secondary">{value.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}</span>
  </time>;
}

export default function ApplicationList({ applications, queue, queueUnavailable, independent, onResetFilters }: Props) {
  const byId = new Map(queue.map(item => [item.application_id, item]));
  if (!applications.length) return <div className="candidate-empty" role="status">
    <IconSearch size={25} /><h3>Không tìm thấy hồ sơ phù hợp bộ lọc</h3>
    <p>Thử mã hồ sơ khác hoặc bỏ bộ lọc để xem toàn bộ danh sách.</p>
    <button type="button" className="btn btn-secondary" onClick={onResetFilters}>Xóa bộ lọc</button>
  </div>;
  return <>
    <div className="candidate-desktop table-wrapper">
      <table className="data-table candidate-table">
        <caption className="candidate-sr-only">Danh sách hồ sơ theo thời gian tiếp nhận; gợi ý AI không phải quyết định tuyển dụng.</caption>
        <thead><tr><th scope="col">Hồ sơ</th><th scope="col">{independent ? 'Công việc' : 'Bước tiếp theo'}</th><th scope="col">CV & cảnh báo</th><th scope="col">Ngày nhận</th><th scope="col"><span className="candidate-sr-only">Thao tác</span></th></tr></thead>
        <tbody>{applications.map(application => {
          const item = queueUnavailable ? undefined : byId.get(application.id);
          return <tr key={application.id}>
            <th scope="row"><div className="candidate-identity"><span className="candidate-document-icon" aria-hidden="true"><IconFileText size={19} /></span><div><strong>{application.public_label}</strong><span className="candidate-secondary">Hồ sơ ẩn danh</span></div></div></th>
            <td><NextTask application={application} item={item} independent={independent} /></td>
            <td><PrivacyState item={item} unavailable={queueUnavailable} /></td>
            <td><ReceivedAt date={application.received_at} /></td>
            <td><OpenApplication application={application} independent={independent} /></td>
          </tr>;
        })}</tbody>
      </table>
    </div>
    <ul className="candidate-mobile" aria-label="Danh sách hồ sơ">{applications.map(application => {
      const item = queueUnavailable ? undefined : byId.get(application.id);
      return <li key={application.id} className="candidate-mobile-card">
        <div className="candidate-mobile-heading"><div className="candidate-identity"><span className="candidate-document-icon" aria-hidden="true"><IconFileText size={19} /></span><div><strong>{application.public_label}</strong><span className="candidate-secondary">Hồ sơ ẩn danh</span></div></div><ReceivedAt date={application.received_at} /></div>
        <NextTask application={application} item={item} independent={independent} />
        <PrivacyState item={item} unavailable={queueUnavailable} />
        <OpenApplication application={application} independent={independent} />
      </li>;
    })}</ul>
  </>;
}
