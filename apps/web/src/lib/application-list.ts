import type { ApplicationItem, ReviewQueueItem, ShortlistCandidate } from './api';

export interface ApplicationListFilters {
  search?: string;
  stage?: string;
  pendingOnly?: boolean;
  queueUnavailable?: boolean;
}

export function filterApplicationList(applications: ApplicationItem[], queue: ReviewQueueItem[], filters: ApplicationListFilters = {}) {
  const byId = new Map(queue.map(item => [item.application_id, item]));
  const query = (filters.search || '').trim().toLocaleLowerCase('vi-VN');
  return applications.filter(application => {
    if (!application.public_label.toLocaleLowerCase('vi-VN').includes(query)) return false;
    if (filters.queueUnavailable) return true;
    const item = byId.get(application.id);
    if (filters.stage && item?.workflow_stage !== filters.stage) return false;
    return !filters.pendingOnly || Boolean(item && (item.sanitized_status !== 'approved' || item.risk_flags.length > 0));
  });
}

interface NextTask { label: string; hint: string; tone: 'neutral' | 'accent' | 'warning' | 'danger' }

export function applicationNextTask(application: ApplicationItem, queue: ReviewQueueItem | undefined, independent = false): NextTask {
  if (application.status !== 'active') return { label: 'Hồ sơ không còn hoạt động', hint: 'Không thực hiện đánh giá mới.', tone: 'neutral' };
  if (independent) return { label: 'Chấm độc lập', hint: 'Rà soát bằng chứng trước khi xem gợi ý AI.', tone: 'neutral' };
  const tasks: Record<string, NextTask> = {
    awaiting_upload: { label: 'Bổ sung CV', hint: 'Hồ sơ chưa có tệp CV.', tone: 'warning' },
    reading: { label: 'Đang đọc CV', hint: 'Hệ thống đang trích xuất nội dung.', tone: 'neutral' },
    needs_review: { label: 'Rà soát CV đã che', hint: 'Kiểm tra thông tin trước khi phân tích.', tone: 'warning' },
    ready_for_ai: { label: 'Chuẩn bị phân tích', hint: 'Đối chiếu CV với rubric hiện hành.', tone: 'neutral' },
    analyzing: { label: 'Đang phân tích', hint: 'Kết quả sẽ cập nhật khi xử lý xong.', tone: 'neutral' },
    awaiting_decision: { label: 'HR cần quyết định', hint: 'Đọc bằng chứng và thông tin cần làm rõ.', tone: 'accent' },
    needs_rubric:{label:'Cập nhật tiêu chí theo JD',hint:'JD đã đổi; cần duyệt lại rubric trước khi đánh giá.',tone:'warning'},
    interview_review:{label:'Rà soát lại phỏng vấn',hint:'Phiếu đã được điều chỉnh sau kết luận.',tone:'warning'},
    interview_completed:{label:'Đã có kết luận phỏng vấn',hint:'Xem đề xuất của người phụ trách; chưa phải offer.',tone:'neutral'},
    waiting_information: {label:'Chờ ứng viên bổ sung',hint:'Theo dõi phản hồi và rà soát lại khi có thông tin mới.',tone:'warning'},
    awaiting_interview: {label:'Chuẩn bị phỏng vấn',hint:'Chọn trọng tâm, người phỏng vấn và lịch trao đổi.',tone:'accent'},
    not_advanced: {label:'Không tiếp tục',hint:'Xem kết luận của HR và phản hồi ứng viên.',tone:'neutral'},
    completed: { label: 'Đã ghi nhận quyết định', hint: 'Mở hồ sơ để xem quyết định của HR.', tone: 'neutral' },
    error: { label: 'Kiểm tra lỗi xử lý', hint: 'Mở hồ sơ để xem lỗi và bước khắc phục.', tone: 'danger' },
  };
  return tasks[queue?.workflow_stage || ''] || { label: 'Chưa tải được trạng thái', hint: 'Bạn vẫn có thể mở hồ sơ để kiểm tra.', tone: 'neutral' };
}

/** Used only when no explicit missing/core criterion is listed. */
export function shortlistEvidenceFallback(candidate: Pick<ShortlistCandidate, 'tier' | 'coverage'>): string {
  if (candidate.tier === 'not_assessed' || candidate.coverage === null) return 'Chưa có đánh giá hiện hành';
  if (candidate.coverage < 1) return 'Bằng chứng còn thiếu';
  return 'Không có mục cần làm rõ được ghi nhận';
}
