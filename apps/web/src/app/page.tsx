'use client';

import { useEffect, useState } from 'react';
import { api, UserAccount, RequisitionItem } from '../lib/api';

export default function HomePage() {
  const [user, setUser] = useState<UserAccount | null>(null);
  const [loading, setLoading] = useState(true);
  const [loginName, setLoginName] = useState('admin_local');
  const [password, setPassword] = useState('AdminPass123!');
  const [loginError, setLoginError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [requisitions, setRequisitions] = useState<RequisitionItem[]>([]);

  useEffect(() => {
    checkAuth();
  }, []);

  async function checkAuth() {
    try {
      const u = await api.getMe();
      setUser(u);
      loadRequisitions();
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  async function loadRequisitions() {
    try {
      const list = await api.listRequisitions();
      setRequisitions(list);
    } catch (e) {
      console.error(e);
    }
  }

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoginError('');
    setSubmitting(true);
    try {
      await api.login(loginName, password);
      await checkAuth();
    } catch (err: any) {
      setLoginError(err.message || 'Thông tin đăng nhập không hợp lệ.');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleLogout() {
    await api.logout();
    setUser(null);
    setRequisitions([]);
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '4rem' }}>
        <p style={{ color: 'var(--text-secondary)' }}>Đang tải trạng thái hệ thống…</p>
      </div>
    );
  }

  if (!user) {
    return (
      <div style={{ maxWidth: '440px', margin: '3rem auto' }}>
        <div className="card">
          <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
            <span className="brand-badge" style={{ fontSize: '0.9rem', padding: '0.3rem 0.75rem' }}>
              TS-AI
            </span>
            <h1 className="page-title" style={{ fontSize: '1.4rem', marginTop: '0.75rem' }}>
              Đăng nhập hệ thống
            </h1>
            <p className="page-subtitle">
              Sàng lọc hồ sơ công bằng, minh bạch và bảo mật thông tin
            </p>
          </div>

          {loginError && (
            <div style={{
              backgroundColor: 'var(--status-danger-bg)',
              color: 'var(--status-danger-text)',
              border: '1px solid var(--status-danger-border)',
              padding: '0.75rem',
              borderRadius: 'var(--radius-sm)',
              marginBottom: '1rem',
              fontSize: '0.875rem'
            }}>
              {loginError}
            </div>
          )}

          <form onSubmit={handleLogin}>
            <div className="form-group">
              <label className="form-label" htmlFor="loginName">Tên đăng nhập</label>
              <input
                id="loginName"
                className="form-input"
                type="text"
                value={loginName}
                onChange={(e) => setLoginName(e.target.value)}
                required
                disabled={submitting}
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="password">Mật khẩu</label>
              <input
                id="password"
                className="form-input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={submitting}
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              style={{ width: '100%', marginTop: '0.5rem' }}
              disabled={submitting}
            >
              {submitting ? 'Đang xác thực…' : 'Đăng nhập'}
            </button>
          </form>

          <div style={{ marginTop: '1.5rem', borderTop: '1px solid var(--border-subtle)', paddingTop: '1rem', fontSize: '0.8rem', color: 'var(--text-muted)', textAlign: 'center' }}>
            Bảo mật Argon2id • Session HttpOnly • CSRF Token Guard
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Chào mừng trở lại, {user.display_name}</h1>
          <p className="page-subtitle">Tài khoản: {user.login_name} • Trạng thái: {user.status}</p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <a href="/requisitions" className="btn btn-primary">
            Quản lý đợt tuyển dụng
          </a>
          <button onClick={handleLogout} className="btn btn-secondary">
            Đăng xuất
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem', marginBottom: '2rem' }}>
        <div className="card">
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Đợt tuyển dụng hoạt động
          </div>
          <div style={{ fontSize: '2.25rem', fontWeight: 700, color: 'var(--accent-primary)', marginTop: '0.5rem' }}>
            {requisitions.length}
          </div>
          <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            Vị trí kỹ thuật đang được phân công
          </div>
        </div>

        <div className="card">
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Nguyên tắc bảo vệ dữ liệu
          </div>
          <div style={{ fontSize: '1.1rem', fontWeight: 600, color: '#34d399', marginTop: '0.5rem' }}>
            100% Redacted PII
          </div>
          <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            Không lộ thông tin nhân thân ra ngoài mô hình
          </div>
        </div>

        <div className="card">
          <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Quyết định nhân sự
          </div>
          <div style={{ fontSize: '1.1rem', fontWeight: 600, color: '#fbbf24', marginTop: '0.5rem' }}>
            Human-in-the-Loop
          </div>
          <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            AI chỉ gợi ý bằng chứng; con người quyết định cuối cùng
          </div>
        </div>
      </div>

      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
          <h2 style={{ fontSize: '1.15rem', fontWeight: 700 }}>Danh sách đợt tuyển dụng gần đây</h2>
          <a href="/requisitions" style={{ fontSize: '0.85rem', fontWeight: 600 }}>Xem tất cả →</a>
        </div>

        {requisitions.length === 0 ? (
          <p style={{ color: 'var(--text-secondary)', padding: '1rem 0' }}>
            Chưa có đợt tuyển dụng nào được tạo. Nhấn "Quản lý đợt tuyển dụng" để tạo đợt mới.
          </p>
        ) : (
          <div className="table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Vị trí tuyển dụng</th>
                  <th>Phòng ban</th>
                  <th>Trạng thái</th>
                  <th>Cập nhật lúc</th>
                  <th>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {requisitions.map((req) => (
                  <tr key={req.id}>
                    <td style={{ fontWeight: 600 }}>{req.title}</td>
                    <td>{req.department || 'Kỹ thuật'}</td>
                    <td>
                      <span className={`badge badge-${req.status}`}>
                        {req.status.toUpperCase()}
                      </span>
                    </td>
                    <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                      {new Date(req.updated_at).toLocaleString('vi-VN')}
                    </td>
                    <td>
                      <a href={`/requisitions/${req.id}`} className="btn btn-secondary" style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem' }}>
                        Mở workspace
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
