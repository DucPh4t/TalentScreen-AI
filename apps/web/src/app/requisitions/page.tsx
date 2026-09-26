'use client';

import { useEffect, useState } from 'react';
import { api, RequisitionItem } from '../../lib/api';

export default function RequisitionsPage() {
  const [requisitions, setRequisitions] = useState<RequisitionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [title, setTitle] = useState('');
  const [department, setDepartment] = useState('Phát triển phần mềm');
  const [jdText, setJdText] = useState(
    'Yêu cầu tuyển dụng: Senior Python Backend Developer.\n' +
    '1. Có kinh nghiệm tối thiểu 3 năm làm việc với Python, FastAPI, Django.\n' +
    '2. Thành thạo thiết kế RESTful API, kiến trúc microservices và message broker (RabbitMQ/Kafka).\n' +
    '3. Thành thạo cơ sở dữ liệu PostgreSQL, tối ưu truy vấn SQL và indexing.\n' +
    '4. Có kiến thức về bảo mật: xác thực JWT, phân quyền RBAC, phòng chống SQL Injection, CSRF.\n' +
    '5. Kinh nghiệm làm việc với Docker, Kubernetes và CI/CD pipelines.\n' +
    '6. Kỹ năng giao tiếp và làm việc nhóm tốt.'
  );
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      const data = await api.listRequisitions();
      setRequisitions(data);
    } catch (err: any) {
      setErrorMsg(err.message || 'Lỗi khi tải danh sách đợt tuyển dụng.');
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setErrorMsg('');
    try {
      const created = await api.createRequisition(title, jdText, department);
      setShowModal(false);
      setTitle('');
      await loadData();
    } catch (err: any) {
      setErrorMsg(err.message || 'Không thể tạo đợt tuyển dụng.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Đợt tuyển dụng</h1>
          <p className="page-subtitle">
            Quản lý các vị trí kỹ thuật, bản mô tả công việc (JD), và tiêu chí Rubric đánh giá
          </p>
        </div>
        <button onClick={() => setShowModal(true)} className="btn btn-primary">
          + Tạo đợt tuyển dụng mới
        </button>
      </div>

      {errorMsg && (
        <div style={{
          backgroundColor: 'var(--status-danger-bg)',
          color: 'var(--status-danger-text)',
          border: '1px solid var(--status-danger-border)',
          padding: '0.75rem 1rem',
          borderRadius: 'var(--radius-sm)',
          marginBottom: '1.5rem',
          fontSize: '0.875rem'
        }}>
          {errorMsg}
        </div>
      )}

      <div className="card">
        {loading ? (
          <p style={{ color: 'var(--text-secondary)', padding: '2rem', textAlign: 'center' }}>
            Đang tải dữ liệu…
          </p>
        ) : requisitions.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '3rem 1rem' }}>
            <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem' }}>
              Chưa có đợt tuyển dụng nào được tạo.
            </p>
            <button onClick={() => setShowModal(true)} className="btn btn-primary">
              Tạo đợt đầu tiên
            </button>
          </div>
        ) : (
          <div className="table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Vị trí</th>
                  <th>Phòng ban</th>
                  <th>Trạng thái</th>
                  <th>Phiên bản Rubric</th>
                  <th>Thời gian cập nhật</th>
                  <th>Hành động</th>
                </tr>
              </thead>
              <tbody>
                {requisitions.map((req) => (
                  <tr key={req.id}>
                    <td style={{ fontWeight: 600 }}>{req.title}</td>
                    <td>{req.department || 'Chung'}</td>
                    <td>
                      <span className={`badge badge-${req.status}`}>
                        {req.status.toUpperCase()}
                      </span>
                    </td>
                    <td style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                      {req.current_rubric_version_id ? 'Đã duyệt v1' : 'Bản nháp (Draft)'}
                    </td>
                    <td style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                      {new Date(req.updated_at).toLocaleString('vi-VN')}
                    </td>
                    <td>
                      <a href={`/requisitions/${req.id}`} className="btn btn-secondary" style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}>
                        Xem chi tiết & Hồ sơ →
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showModal && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-header">
              <h2 className="modal-title">Tạo đợt tuyển dụng mới</h2>
              <button
                onClick={() => setShowModal(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: '1.25rem', cursor: 'pointer' }}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreate}>
              <div className="form-group">
                <label className="form-label" htmlFor="title">Tên vị trí tuyển dụng</label>
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
                <label className="form-label" htmlFor="department">Phòng ban</label>
                <input
                  id="department"
                  className="form-input"
                  type="text"
                  placeholder="Ví dụ: Kỹ thuật phần mềm"
                  value={department}
                  onChange={(e) => setDepartment(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="jdText">
                  Nội dung bản mô tả công việc (JD)
                </label>
                <textarea
                  id="jdText"
                  className="form-textarea"
                  rows={8}
                  value={jdText}
                  onChange={(e) => setJdText(e.target.value)}
                  required
                />
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginTop: '0.3rem' }}>
                  Nội dung JD sẽ được trích xuất để làm căn cứ bằng chứng cho 6 tiêu chí Rubric.
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
                  {submitting ? 'Đang tạo…' : 'Xác nhận tạo đợt'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
