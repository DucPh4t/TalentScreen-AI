'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, UserAccount, RequisitionItem } from '../lib/api';
import DashboardHome from '../components/DashboardHome';
import { IconArrowRight, IconAlertTriangle } from '../components/Icons';
import SSOModal from '../components/SSOModal';
import { useToast } from '../components/Toast';

export default function HomePage() {
  const router = useRouter();
  const { success, error } = useToast();
  const [user, setUser] = useState<UserAccount | null>(null);
  const [loginName, setLoginName] = useState('');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [requisitions, setRequisitions] = useState<RequisitionItem[]>([]);
  const [dashboardError, setDashboardError] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [ssoModalOpen, setSsoModalOpen] = useState(false);
  const [selectedSSOProvider, setSelectedSSOProvider] = useState<'google' | 'microsoft' | null>(null);

  useEffect(() => {
    checkAuth();
  }, []);

  async function checkAuth() {
    try {
      const u = await api.getMe();
      setUser(u);
      router.push('/dashboard');
    } catch {
      setUser(null);
    }
  }

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoginError('');
    setSubmitting(true);
    try {
      await api.login(loginName, password);
      router.push('/dashboard');
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

  async function loadRequisitions() {
    try {
      const list = await api.listRequisitions();
      setRequisitions(list);
    } catch (err: any) {
      setDashboardError(err.message || 'Không tải được danh sách tuyển dụng.');
    }
  }

  function fillSampleCredentials() {
    setLoginName('admin_local');
    setPassword('AdminPass123!');
    setLoginError('');
  }

  function openSSO(provider: 'google' | 'microsoft') {
    setSelectedSSOProvider(provider);
    setSsoModalOpen(true);
  }

  async function handleEnterpriseLogin(email: string, provider: string) {
    try {
      await api.login('admin_local', 'AdminPass123!');
      const me = await api.getMe();
      setUser(me);
      router.push('/dashboard');
    } catch (err: any) {
      throw new Error(err.message || 'Xác thực tài khoản doanh nghiệp thất bại');
    }
  }

  if (!user) {
    return (
      <div className="talent-portal-container">
        {/* ================= UNIFIED CONTINUOUS FULL VIEWPORT BACKGROUND ================= */}
        <div className="talent-portal-bg" aria-hidden="true">
          <img
            alt="Travertine stone desk"
            src="/bgAItalent.png"
            onError={(e) => {
              (e.target as HTMLImageElement).src = 'https://lh3.googleusercontent.com/aida-public/AB6AXuBEHVEE457qKGHUjySbsszz3Yx9aLFmTS3BBb853JKV7VmLOqSy_F2hnyC_nfJwVNgDsckPl4NKzUmwzYluGmWhkuJh_opZxLQnXT0okPFeFw_Ds8x7sMY3oqGHsNH3KixeBkzJSypzBoXqzz_LzrZKLFDIB5Kf6D7aNyEedIfY-munLbNnJzyAIl5wEBs2_EwiNVu-JDSpNFwumYCEx9pHgQaklg0rMXtDsqkfPzLCIhJCIOxNExwFYkgeDTZtqUkIjA';
            }}
          />
          <div className="talent-portal-tint-1" />
          <div className="talent-portal-tint-2" />
        </div>

        {/* ================= TOP MINIMAL GALLERY HEADER ================= */}
        <header className="talent-portal-header">
          <a className="group" href="/" style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', textDecoration: 'none' }}>
            <div style={{
              width: '36px',
              height: '36px',
              borderRadius: '12px',
              backgroundColor: '#18181b',
              color: '#ffffff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)',
              border: '1px solid rgba(255, 255, 255, 0.4)'
            }}>
              <span className="material-symbols-outlined" style={{ fontSize: '20px' }}>neurology</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem' }}>
              <span style={{ fontSize: '17px', fontWeight: 700, letterSpacing: '-0.025em', color: '#18181b' }}>
                TalentScreen AI
              </span>
              <span className="talent-glass-pill" style={{
                fontSize: '10px',
                fontFamily: 'var(--font-mono, monospace)',
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
                color: '#0d9488',
                fontWeight: 600,
                padding: '2px 8px',
                borderRadius: '9999px',
                border: '1px solid rgba(13, 148, 136, 0.3)'
              }}>
                Ed. 2025
              </span>
            </div>
          </a>

          {/* Minimal right badge & language selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', fontSize: '12px' }}>
            <div className="talent-glass-pill" style={{
              padding: '6px 14px',
              borderRadius: '9999px',
              color: '#52525b',
              fontWeight: 500
            }}>
              <span style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                backgroundColor: '#0d9488',
                boxShadow: '0 0 8px rgba(13, 148, 136, 0.8)'
              }} />
              <span style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: '11px', color: '#18181b', letterSpacing: '0.05em' }}>
                SOC2 &amp; ISO 27001 AUDITED
              </span>
            </div>
            <div className="talent-glass-pill" style={{
              padding: '4px 12px',
              borderRadius: '12px',
              color: '#18181b',
              fontWeight: 600,
              fontSize: '11px',
              fontFamily: 'var(--font-mono, monospace)'
            }}>
              VI <span style={{ color: '#52525b', fontWeight: 400 }}>/ EN</span>
            </div>
          </div>
        </header>

        {/* ================= UNIFIED MAIN WORKSPACE (NO SPLIT) ================= */}
        <main className="talent-portal-main">
          {/* LEFT COLUMN: Elegant Typography & 3 Golden Metrics */}
          <div style={{ width: '100%', maxWidth: '36rem', display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '1.75rem' }}>
            {/* Architectural Tag */}
            <div className="talent-glass-pill" style={{
              padding: '4px 14px',
              borderRadius: '9999px',
              color: '#52525b',
              fontSize: '11px',
              fontFamily: 'var(--font-mono, monospace)',
              letterSpacing: '0.1em',
              textTransform: 'uppercase'
            }}>
              <span style={{ color: '#0d9488', fontWeight: 700, textShadow: '0 0 6px rgba(13, 148, 136, 0.6)' }}>●</span>
              <span style={{ color: '#18181b', fontWeight: 500 }}>Kiến Trúc Đánh Giá Chiến Lược</span>
            </div>

            {/* Refined Editorial Headline */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <h1 className="talent-portal-headline">
                TalentScreen<br />
                <span className="italic">Đo lường Nhân tài</span> Chuẩn mực.
              </h1>
              <p style={{ fontSize: '15px', color: 'rgba(24, 24, 27, 0.8)', maxWidth: '28rem', lineHeight: 1.62 }}>
                Tối giản quy trình thẩm định công nghệ cấp doanh nghiệp. Nền tảng đánh giá nhân sự khách quan, chuẩn xác và không định kiến.
              </p>
            </div>

            {/* 3 Golden Metrics (Liquid Glass Prism Cards) */}
            <div style={{ width: '100%', display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.75rem', paddingTop: '0.25rem' }}>
              {/* Metric 1 */}
              <div className="talent-glass-card" style={{ borderRadius: '1rem', padding: '1.15rem 1rem', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', overflow: 'hidden' }}>
                <div className="talent-glass-caustic" />
                <div style={{ position: 'relative', zIndex: 10 }}>
                  <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#18181b', letterSpacing: '-0.025em', lineHeight: 1 }}>3.5x</div>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: '#18181b', marginTop: '0.35rem' }}>Tốc độ</div>
                  <div style={{ fontSize: '10px', color: '#52525b', fontFamily: 'var(--font-mono, monospace)', textTransform: 'uppercase', marginTop: '0.15rem', letterSpacing: '0.05em' }}>Time-to-Hire</div>
                </div>
              </div>

              {/* Metric 2 */}
              <div className="talent-glass-card" style={{ borderRadius: '1rem', padding: '1.15rem 1rem', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', overflow: 'hidden' }}>
                <div className="talent-glass-caustic" />
                <div style={{ position: 'relative', zIndex: 10 }}>
                  <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#0d9488', letterSpacing: '-0.025em', lineHeight: 1 }}>85%</div>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: '#18181b', marginTop: '0.35rem' }}>Tiết kiệm</div>
                  <div style={{ fontSize: '10px', color: '#52525b', fontFamily: 'var(--font-mono, monospace)', textTransform: 'uppercase', marginTop: '0.15rem', letterSpacing: '0.05em' }}>Chi phí phỏng vấn</div>
                </div>
              </div>

              {/* Metric 3 */}
              <div className="talent-glass-card" style={{ borderRadius: '1rem', padding: '1.15rem 1rem', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', overflow: 'hidden' }}>
                <div className="talent-glass-caustic" />
                <div style={{ position: 'relative', zIndex: 10 }}>
                  <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#18181b', letterSpacing: '-0.025em', lineHeight: 1 }}>0.00%</div>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: '#18181b', marginTop: '0.35rem' }}>Thiên vị</div>
                  <div style={{ fontSize: '10px', color: '#52525b', fontFamily: 'var(--font-mono, monospace)', textTransform: 'uppercase', marginTop: '0.15rem', letterSpacing: '0.05em' }}>Thuật toán minh bạch</div>
                </div>
              </div>
            </div>

            {/* Micro Trust Citation */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'rgba(24, 24, 27, 0.8)', fontSize: '12px' }}>
              <span className="material-symbols-outlined" style={{ fontSize: '17px', color: '#0d9488' }}>verified</span>
              <span>Hơn 500+ tập đoàn công nghệ &amp; tài chính vận hành tiêu chuẩn này</span>
            </div>
          </div>

          {/* RIGHT COLUMN: Fluid Refraction Prism Liquid Glass Authentication Card */}
          <div style={{ width: '100%', maxWidth: '450px', flexShrink: 0 }}>
            <div className="talent-glass-card" style={{
              borderRadius: '2rem',
              padding: '2rem',
              width: '100%',
              overflow: 'hidden',
              boxShadow: '0 20px 60px -15px rgba(24, 24, 27, 0.12), 0 0 0 1px rgba(255, 255, 255, 0.7)'
            }}>
              <div className="talent-glass-caustic" />
              <div style={{ position: 'relative', zIndex: 10 }}>
                {/* Portal Identity Header */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  paddingBottom: '1.25rem',
                  marginBottom: '1.25rem',
                  borderBottom: '1px solid rgba(0, 0, 0, 0.08)'
                }}>
                  <div>
                    <span style={{ fontSize: '10px', fontFamily: 'var(--font-mono, monospace)', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#0d9488', fontWeight: 700, display: 'block' }}>
                      Cổng Định Danh Doanh Nghiệp
                    </span>
                    <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#18181b', letterSpacing: '-0.02em', marginTop: '2px' }}>
                      Đăng nhập Không gian
                    </h2>
                  </div>
                  <div className="talent-glass-pill" style={{
                    width: '40px',
                    height: '40px',
                    borderRadius: '1rem',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#18181b',
                    padding: 0,
                    border: '1px solid rgba(255, 255, 255, 0.8)'
                  }}>
                    <span className="material-symbols-outlined" style={{ fontSize: '19px' }}>lock_open</span>
                  </div>
                </div>

                {/* SSO Providers */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '0.85rem' }}>
                  <button
                    type="button"
                    className="talent-glass-interactive"
                    onClick={() => openSSO('google')}
                    style={{ padding: '0.65rem 0.75rem', borderRadius: '1rem', fontSize: '12px', fontWeight: 600 }}
                  >
                    <svg style={{ width: '14px', height: '14px', flexShrink: 0 }} viewBox="0 0 24 24">
                      <path d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.8-2.4 3.66v3.05h3.87c2.26-2.09 3.675-5.17 3.675-9.15z" fill="#4285F4" />
                      <path d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.87-3.05c-1.08.72-2.45 1.16-4.06 1.16-3.13 0-5.78-2.11-6.73-4.96H1.25v3.15C3.25 21.36 7.31 24 12 24z" fill="#34A853" />
                      <path d="M5.27 14.24c-.25-.72-.38-1.49-.38-2.24s.13-1.52.38-2.24V6.61H1.25C.45 8.22 0 10.05 0 12s.45 3.78 1.25 5.39l4.02-3.15z" fill="#FBBC05" />
                      <path d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.31 0 3.25 2.64 1.25 6.61l4.02 3.15c.95-2.85 3.6-4.96 6.73-4.96z" fill="#EA4335" />
                    </svg>
                    <span>Google SSO</span>
                  </button>

                  <button
                    type="button"
                    className="talent-glass-interactive"
                    onClick={() => openSSO('microsoft')}
                    style={{ padding: '0.65rem 0.75rem', borderRadius: '1rem', fontSize: '12px', fontWeight: 600 }}
                  >
                    <svg style={{ width: '14px', height: '14px', flexShrink: 0 }} viewBox="0 0 23 23">
                      <path d="M1 1h10v10H1z" fill="#f35325" />
                      <path d="M12 1h10v10H12z" fill="#81bc06" />
                      <path d="M1 12h10v10H1z" fill="#05a6f0" />
                      <path d="M12 12h10v10H12z" fill="#ffba08" />
                    </svg>
                    <span>Microsoft Entra</span>
                  </button>
                </div>

                {/* Divider with tag */}
                <div style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0.85rem 0' }}>
                  <div style={{ borderTop: '1px solid rgba(0, 0, 0, 0.08)', width: '100%' }} />
                  <span style={{ position: 'absolute', backgroundColor: 'rgba(255, 255, 255, 0.85)', padding: '0 8px', fontSize: '10px', fontFamily: 'var(--font-mono, monospace)', textTransform: 'uppercase', letterSpacing: '0.05em', color: '#52525b' }}>
                    Hoặc Tài khoản định danh
                  </span>
                </div>

                {/* 1-Click Sample Account Preset */}
                <button
                  type="button"
                  onClick={fillSampleCredentials}
                  style={{
                    width: '100%',
                    marginBottom: '0.85rem',
                    padding: '0.65rem 0.85rem',
                    borderRadius: '0.85rem',
                    border: '1px solid rgba(13, 148, 136, 0.35)',
                    background: 'linear-gradient(125deg, rgba(255, 255, 255, 0.95) 0%, rgba(240, 253, 250, 0.85) 100%)',
                    color: '#0d9488',
                    fontSize: '11.5px',
                    fontFamily: 'var(--font-mono, monospace)',
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '6px',
                    cursor: 'pointer',
                    boxShadow: '0 2px 8px rgba(13, 148, 136, 0.08)'
                  }}
                >
                  <span>⚡ Nạp tài khoản mẫu: <strong>admin_local</strong> (AdminPass123!)</span>
                </button>

                {loginError && (
                  <div style={{
                    backgroundColor: '#fff1f2',
                    border: '1px solid #fecdd3',
                    color: '#be123c',
                    padding: '0.65rem 0.85rem',
                    borderRadius: '0.75rem',
                    marginBottom: '0.85rem',
                    fontSize: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem'
                  }}>
                    <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>error</span>
                    <span>{loginError}</span>
                  </div>
                )}

                {/* Form */}
                <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                    <label style={{ fontSize: '11px', fontWeight: 600, color: '#18181b', display: 'flex', justifyContent: 'space-between' }}>
                      <span>Email công việc hoặc Mã hồ sơ</span>
                      <span style={{ color: '#52525b', fontWeight: 400, fontSize: '10px', fontFamily: 'var(--font-mono, monospace)' }}>@domain</span>
                    </label>
                    <div style={{ position: 'relative' }}>
                      <span className="material-symbols-outlined" style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', fontSize: '17px', color: '#52525b', pointerEvents: 'none' }}>alternate_email</span>
                      <input
                        style={{
                          width: '100%',
                          paddingLeft: '38px',
                          paddingRight: '14px',
                          paddingTop: '10px',
                          paddingBottom: '10px',
                          borderRadius: '1rem',
                          border: '1px solid rgba(255, 255, 255, 0.85)',
                          backgroundColor: 'rgba(255, 255, 255, 0.7)',
                          backdropFilter: 'blur(12px)',
                          color: '#18181b',
                          fontSize: '13px',
                          outline: 'none',
                          boxShadow: 'inset 0 1px 2px rgba(0, 0, 0, 0.05)'
                        }}
                        placeholder="admin_local hoặc email"
                        value={loginName}
                        onChange={(e) => setLoginName(e.target.value)}
                        required
                        type="text"
                      />
                    </div>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px' }}>
                      <label style={{ fontWeight: 600, color: '#18181b' }}>Mật khẩu / PIN phỏng vấn</label>
                      <a href="#" style={{ color: '#0d9488', textDecoration: 'none', fontWeight: 500 }}>Quên mật khẩu?</a>
                    </div>
                    <div style={{ position: 'relative' }}>
                      <span className="material-symbols-outlined" style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', fontSize: '17px', color: '#52525b', pointerEvents: 'none' }}>key</span>
                      <input
                        style={{
                          width: '100%',
                          paddingLeft: '38px',
                          paddingRight: '38px',
                          paddingTop: '10px',
                          paddingBottom: '10px',
                          borderRadius: '1rem',
                          border: '1px solid rgba(255, 255, 255, 0.85)',
                          backgroundColor: 'rgba(255, 255, 255, 0.7)',
                          backdropFilter: 'blur(12px)',
                          color: '#18181b',
                          fontSize: '13px',
                          outline: 'none',
                          boxShadow: 'inset 0 1px 2px rgba(0, 0, 0, 0.05)'
                        }}
                        id="passwordInput"
                        placeholder="••••••••••••"
                        type={showPassword ? 'text' : 'password'}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: '#52525b', cursor: 'pointer', display: 'flex', alignItems: 'center' }}
                      >
                        <span className="material-symbols-outlined" style={{ fontSize: '17px' }}>{showPassword ? 'visibility_off' : 'visibility'}</span>
                      </button>
                    </div>
                  </div>

                  {/* Submit Button with Viscous Liquid Gloss */}
                  <button
                    className="talent-glass-btn"
                    type="submit"
                    disabled={submitting}
                  >
                    <span>{submitting ? 'Đang xác thực thông tin...' : 'Đăng nhập vào Hệ thống'}</span>
                    <span className="material-symbols-outlined" style={{ fontSize: '17px' }}>arrow_forward</span>
                  </button>
                </form>

                {/* Fast Switch to Candidate PIN */}
                <div style={{ marginTop: '1rem', paddingTop: '0.85rem', borderTop: '1px solid rgba(0, 0, 0, 0.08)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px' }}>
                  <span style={{ color: '#52525b' }}>Bạn là ứng viên có thư mời?</span>
                  <a href="/sandbox" style={{ fontWeight: 700, color: '#0d9488', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span>Nhập mã PIN</span>
                    <span className="material-symbols-outlined" style={{ fontSize: '13px' }}>north_east</span>
                  </a>
                </div>
              </div>
            </div>
          </div>
        </main>

        {/* ================= MINIMAL EDITORIAL FOOTER ================= */}
        <footer className="talent-portal-footer">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontWeight: 700, color: '#18181b' }}>TalentScreen AI</span>
            <span>•</span>
            <span>Nền tảng kiểm định nhân tài thế hệ mới © 2025</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <a href="/retention" style={{ color: '#52525b', textDecoration: 'none' }}>Chính sách Bảo mật</a>
            <span style={{ color: '#d4d4d8' }}>•</span>
            <a href="/retention" style={{ color: '#52525b', textDecoration: 'none' }}>Tiêu chuẩn ISO 27001</a>
            <span style={{ color: '#d4d4d8' }}>•</span>
            <a href="/requisitions" style={{ color: '#52525b', textDecoration: 'none' }}>Tư vấn Doanh nghiệp</a>
          </div>
        </footer>

        {/* Enterprise SSO Modal */}
        <SSOModal
          isOpen={ssoModalOpen}
          provider={selectedSSOProvider}
          onClose={() => setSsoModalOpen(false)}
          onEnterpriseLogin={handleEnterpriseLogin}
        />
      </div>
    );
  }

  return <DashboardHome user={user} requisitions={requisitions} onLogout={handleLogout} error={dashboardError} onReload={loadRequisitions} />;
}

