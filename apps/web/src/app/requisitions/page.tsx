'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api, RequisitionItem } from '../../lib/api';
import {
  IconPlus,
  IconSearch,
  IconFileText,
  IconArrowRight,
  IconX,
  IconCheckCircle,
  IconAlertTriangle,
  IconSparkles
} from '../../components/Icons';
import { useToast } from '../../components/Toast';
import { SkeletonTable } from '../../components/Skeleton';

export default function RequisitionsPage() {
  const { success, error: toastError } = useToast();
  const [requisitions, setRequisitions] = useState<RequisitionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'open' | 'draft' | 'paused'>('all');

  const [title, setTitle] = useState('');
  const [jdText, setJdText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [loadError, setLoadError] = useState('');
  const [createdDraftId, setCreatedDraftId] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoadError('');
    try {
      const data = await api.listRequisitions();
      setRequisitions(data);
    } catch (err: any) {
      setLoadError(err.message || 'Lỗi khi tải danh sách đợt tuyển dụng.');
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setErrorMsg('');
    try {
      const created = await api.createRequisition(title);
      try {
        await api.createJDVersion(created.id, jdText, created.row_version);
      } catch (jdError) {
        setCreatedDraftId(created.id);
        setShowModal(false);
        await loadData();
        setErrorMsg(`Đợt đã tạo, nhưng JD chưa lưu: ${jdError instanceof Error ? jdError.message : 'Lỗi không xác định'}. Mở đợt vừa tạo để bổ sung JD.`);
        return;
      }
      setShowModal(false);
      setTitle('');
      setJdText('');
      setCreatedDraftId(null);
      success("Đã tạo đợt tuyển dụng mới thành công!");
      await loadData();
    } catch (err: any) {
      setErrorMsg(err.message || 'Không thể tạo đợt tuyển dụng.');
      toastError(err.message || 'Không thể tạo đợt tuyển dụng.');
    } finally {
      setSubmitting(false);
    }
  }

  const filteredRequisitions = requisitions.filter((req) => {
    const matchesSearch = req.title.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === 'all' || req.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <div>
      {/* Page Header */}
      <div className="page-header">
        <div>
          <div className="breadcrumbs">
            <Link href="/">Trang chủ</Link>
            <span>/</span>
            <span style={{ color: 'var(--text-primary)' }}>Đợt tuyển dụng</span>
          </div>
          <h1 className="page-title">Quản Lý Đợt Tuyển Dụng</h1>
          <p className="page-subtitle">
            Cấu hình vị trí kỹ thuật, bản mô tả công việc (JD), và bộ tiêu chí Rubric 6 chuẩn mực độc lập
          </p>
        </div>

        <button onClick={() => setShowModal(true)} className="btn btn-primary">
          <IconPlus size={16} />
          <span>Tạo Đợt Tuyển Dụng Mới</span>
        </button>
      </div>

      {errorMsg && (
        <div style={{
          backgroundColor: 'var(--rose-bg)',
          color: 'var(--rose-text)',
          border: '1px solid var(--rose-border)',
          padding: '0.85rem 1.25rem',
          borderRadius: 'var(--radius-sm)',
          marginBottom: '1.5rem',
          fontSize: '0.875rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem'
        }}>
          <IconAlertTriangle size={16} color="var(--rose-text)" />
          <span>{errorMsg}</span>
          {createdDraftId && <Link href={`/requisitions/${createdDraftId}`} className="btn btn-sm btn-outline">Mở bản nháp</Link>}
        </div>
      )}

      {/* Filter and Search Bar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '1rem',
        marginBottom: '1.5rem',
        flexWrap: 'wrap'
      }}>
        <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
          <button
            onClick={() => setStatusFilter('all')}
            className={`btn btn-sm ${statusFilter === 'all' ? 'btn-primary' : 'btn-outline'}`}
          >
            Tất cả ({requisitions.length})
          </button>
          <button
            onClick={() => setStatusFilter('open')}
            className={`btn btn-sm ${statusFilter === 'open' ? 'btn-primary' : 'btn-outline'}`}
          >
            Đang mở ({requisitions.filter(r => r.status === 'open').length})
          </button>
          <button
            onClick={() => setStatusFilter('draft')}
            className={`btn btn-sm ${statusFilter === 'draft' ? 'btn-primary' : 'btn-outline'}`}
          >
            Bản nháp ({requisitions.filter(r => r.status === 'draft').length})
          </button>
          <button
            onClick={() => setStatusFilter('paused')}
            className={`btn btn-sm ${statusFilter === 'paused' ? 'btn-primary' : 'btn-outline'}`}
          >
            Tạm dừng ({requisitions.filter(r => r.status === 'paused').length})
          </button>
        </div>

        <div style={{ position: 'relative', width: '320px', maxWidth: '100%' }}>
          <div style={{ position: 'absolute', left: '0.85rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }}>
            <IconSearch size={15} />
          </div>
          <input
            type="text"
            className="form-input"
            style={{ paddingLeft: '2.4rem' }}
            placeholder="Tìm theo vị trí tuyển dụng…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      {/* Requisitions Content */}
      <div className="card" style={{ padding: '0.5rem' }}>
        {loading ? (
          <SkeletonTable rows={5} cols={5} />
        ) : loadError ? (
          <div className="empty-work" role="alert"><IconAlertTriangle size={22} /><h3>Không tải được đợt tuyển dụng</h3><p>{loadError}</p><button className="btn btn-secondary" onClick={() => void loadData()}>Thử lại</button></div>
        ) : filteredRequisitions.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '4rem 1.5rem' }}>
            <div style={{ width: '48px', height: '48px', borderRadius: '50%', background: 'rgba(56, 189, 248, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 1rem auto' }}>
              <IconFileText size={24} color="#38bdf8" />
            </div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700, marginBottom: '0.4rem' }}>Không tìm thấy đợt tuyển dụng nào</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginBottom: '1.5rem' }}>
              {searchQuery ? 'Thử thay đổi từ khóa tìm kiếm hoặc bộ lọc trạng thái.' : 'Hãy khởi tạo đợt tuyển dụng đầu tiên để nhận hồ sơ.'}
            </p>
            <button onClick={() => setShowModal(true)} className="btn btn-primary">
              <IconPlus size={16} />
              <span>Tạo Đợt Mới</span>
            </button>
          </div>
        ) : (
          <div className="table-wrapper" style={{ border: 'none' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Vị Trí Tuyển Dụng</th>
                  <th>Trạng Thái</th>
                  <th>Tiêu Chuẩn Rubric</th>
                  <th>Cập Nhật Lúc</th>
                  <th style={{ textAlign: 'right' }}>Thao Tác</th>
                </tr>
              </thead>
              <tbody>
                {filteredRequisitions.map((req) => (
                  <tr key={req.id}>
                    <td>
                      <div style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: '0.95rem' }}>{req.title}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        UUID: {req.id}
                      </div>
                    </td>
                    <td>
                      <span className={`badge badge-${req.status}`}>
                        {req.status === 'open' && 'ĐANG MỞ'}
                        {req.status === 'draft' && 'BẢN NHÁP'}
                        {req.status === 'paused' && 'TẠM DỪNG'}
                        {req.status === 'closed' && 'ĐÃ ĐÓNG'}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.825rem' }}>
                        <IconSparkles size={14} color="#38bdf8" />
                        <span style={{ color: req.current_rubric_version_id ? 'var(--emerald-text)' : 'var(--text-muted)' }}>
                          {req.current_rubric_version_id ? 'Rubric đã gắn' : 'Chưa có rubric được duyệt'}
                        </span>
                      </div>
                    </td>
                    <td style={{ fontSize: '0.825rem', color: 'var(--text-secondary)' }}>
                      {new Date(req.updated_at).toLocaleString('vi-VN')}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <Link href={`/requisitions/${req.id}`} className="btn btn-secondary btn-sm">
                        <span>Workspace Hồ Sơ</span>
                        <IconArrowRight size={14} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modal: Tạo Đợt Tuyển Dụng Mới */}
      {showModal && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <div style={{ width: '32px', height: '32px', borderRadius: 'var(--radius-sm)', background: 'var(--accent-gradient)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <IconPlus size={18} color="#fff" />
                </div>
                <div>
                  <h2 className="modal-title">Tạo Đợt Tuyển Dụng Mới</h2>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Khởi tạo bản mô tả công việc (JD) và bộ tiêu chí Rubric</p>
                </div>
              </div>
              <button
                onClick={() => setShowModal(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
              >
                <IconX size={20} />
              </button>
            </div>

            <form onSubmit={handleCreate}>
              <div className="form-group">
                <label className="form-label" htmlFor="title">Vị trí tuyển dụng</label>
                <input
                  id="title"
                  className="form-input"
                  type="text"
                  placeholder="Ví dụ: Senior Backend Python Engineer"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.45rem' }}>
                  <label className="form-label" htmlFor="jdText" style={{ marginBottom: 0 }}>
                    Nội dung bản mô tả công việc (Job Description)
                  </label>
                  <button
                    type="button"
                    onClick={() => {
                      setTitle('Chuyên viên Backend Python cho hệ thống nội bộ');
                      setJdText(
                        '# JD tham khảo — Backend Python cho hệ thống nội bộ\n' +
                        'HR và người phụ trách IT cần xác nhận nhu cầu, phạm vi công việc và ngưỡng chấm trước khi dùng cho tuyển dụng thật.\n\n' +
                        '| Requirement ID | Criterion ID / trọng số | Nội dung yêu cầu chuẩn để trích dẫn |\n' +
                        '|---|---|---|\n' +
                        '| `JD-PY-01` | `python_backend` /20 | Triển khai chức năng backend bằng Python từ một yêu cầu nghiệp vụ; tổ chức mã thành các phần có trách nhiệm rõ, xử lý lỗi và duy trì hành vi của chức năng khi sửa đổi. |\n' +
                        '| `JD-API-01` | `api_design` /25 | Thiết kế và triển khai HTTP API có hợp đồng đầu vào, đầu ra và mã trạng thái phù hợp; kiểm tra dữ liệu đầu vào và xử lý lỗi để bên sử dụng API nhận được hành vi nhất quán. |\n' +
                        '| `JD-SQL-01` | `sql_data` /20 | Làm việc với cơ sở dữ liệu quan hệ để lưu và truy vấn dữ liệu nghiệp vụ; thiết kế hoặc sửa cấu trúc dữ liệu, dùng ràng buộc và giao dịch khi cần để giữ tính đúng đắn của dữ liệu. |\n' +
                        '| `JD-TEST-01` | `testing_debugging` /15 | Kiểm thử hành vi backend và tái hiện lỗi từ tình huống cụ thể; xác định nguyên nhân, sửa lỗi và bổ sung kiểm tra phù hợp để hạn chế lỗi tái diễn. |\n' +
                        '| `JD-SEC-01` | `security_privacy` /10 | Áp dụng xác thực, phân quyền và bảo vệ dữ liệu trong phạm vi tính năng phụ trách; kiểm soát dữ liệu nhạy cảm trong truy cập, cấu hình và log, đồng thời xử lý các trường hợp truy cập không hợp lệ. |\n' +
                        '| `JD-OPS-01` | `delivery_ops` /10 | Đưa thay đổi backend qua quy trình Git, kiểm tra và triển khai có kiểm soát; cấu hình môi trường, quan sát tình trạng dịch vụ và có cách xử lý khi bản triển khai gặp lỗi. |\n\n' +
                        'Kinh nghiệm làm việc, dự án cá nhân, đồ án và dự án cộng đồng đều được xem xét theo cùng tiêu chí. Không dùng tuổi, giới tính, tên trường, danh tiếng tổ chức hoặc ngôn ngữ CV làm căn cứ chấm điểm.'
                      );
                    }}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: 'var(--accent-cyan)',
                      fontSize: '0.75rem',
                      cursor: 'pointer',
                      textDecoration: 'underline'
                    }}
                  >
                    Nạp JD tham khảo khớp rubric seed
                  </button>
                </div>
                <textarea
                  id="jdText"
                  className="form-textarea"
                  rows={8}
                  value={jdText}
                  onChange={(e) => setJdText(e.target.value)}
                  minLength={50}
                  required
                />
                <span className="form-helper">
                  Nội dung JD sẽ được trích xuất làm căn cứ đối chiếu cho 6 tiêu chí Rubric đánh giá năng lực lập trình viên.
                </span>
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="btn btn-secondary"
                  disabled={submitting}
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={submitting}
                >
                  {submitting ? 'Đang tạo…' : 'Xác Nhận Tạo Đợt Tuyển Dụng'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
