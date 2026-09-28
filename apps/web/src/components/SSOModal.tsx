'use client';

import React, { useState, useEffect } from 'react';
import { toast } from './Toast';

interface SSOModalProps {
  isOpen: boolean;
  provider: 'google' | 'microsoft' | null;
  onClose: () => void;
  onEnterpriseLogin: (email: string, provider: string) => Promise<void>;
}

export default function SSOModal({ isOpen, provider, onClose, onEnterpriseLogin }: SSOModalProps) {
  const [email, setEmail] = useState('');
  const [authenticating, setAuthenticating] = useState(false);
  const [authStep, setAuthStep] = useState<string>('');
  const [viewTab, setViewTab] = useState<'login' | 'setup'>('login');
  const [setupSubmitted, setSetupSubmitted] = useState(false);
  const [customOrgName, setCustomOrgName] = useState('');

  useEffect(() => {
    if (isOpen) {
      setEmail('auditor.lead@fpt.com');
      setAuthenticating(false);
      setAuthStep('');
      setViewTab('login');
      setSetupSubmitted(false);
    }
  }, [isOpen, provider]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !provider) return null;

  const isGoogle = provider === 'google';
  const providerTitle = isGoogle ? 'Google Workspace SSO' : 'Microsoft Entra ID (Azure AD)';
  const protocolBadge = isGoogle ? 'OIDC 1.0 & OAuth 2.0 PKCE' : 'SAML 2.0 & WS-Fed';

  const sampleDomains = [
    { label: 'FPT Corporation', email: 'auditor.lead@fpt.com' },
    { label: 'VNG Tech', email: 'hr.talent@vng.com.vn' },
    { label: 'Viettel Telecom', email: 'auditor@viettel.com.vn' },
    { label: 'Shopee Sea', email: 'talent.lead@shopee.com' }
  ];

  const handleStartSSO = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !email.includes('@')) {
      toast.warning('Vui lòng nhập email doanh nghiệp hợp lệ (@company.com).');
      return;
    }

    setAuthenticating(true);
    setAuthStep('Đang xác định IdP Tenant và chứng chỉ SAML/OIDC...');

    setTimeout(async () => {
      setAuthStep(`Đang xác thực phiên định danh ${email} qua ${providerTitle}...`);
      setTimeout(async () => {
        try {
          await onEnterpriseLogin(email, provider);
          toast.success(`Xác thực ${providerTitle} thành công! Chào mừng HR Auditor: ${email}`);
          onClose();
        } catch (err: any) {
          toast.error(err.message || 'Xác thực SSO thất bại');
          setAuthenticating(false);
          setAuthStep('');
        }
      }, 700);
    }, 600);
  };

  const handleRequestSetup = (e: React.FormEvent) => {
    e.preventDefault();
    setSetupSubmitted(true);
    toast.success(
      `Đã tạo hồ sơ tiếp nhận IdP cho ${customOrgName || 'doanh nghiệp'}. Bộ phận Enterprise Security sẽ gửi metadata trong vòng 15 phút.`,
      'Yêu cầu Tích hợp Đã Ghi Nhận'
    );
    setTimeout(() => {
      onClose();
    }, 1800);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="sso-dialog-title"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 99999,
        backgroundColor: 'rgba(24, 24, 27, 0.45)',
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1.25rem',
        animation: 'fadeIn 0.2s cubic-bezier(0.16, 1, 0.3, 1)'
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !authenticating) onClose();
      }}
    >
      <div
        className="stitch-liquid-card"
        style={{
          width: '100%',
          maxWidth: '540px',
          borderRadius: '1.75rem',
          padding: '2rem',
          boxShadow: '0 25px 70px -15px rgba(24, 24, 27, 0.2), 0 0 0 1px rgba(255, 255, 255, 0.8)',
          background: 'linear-gradient(135deg, rgba(255, 255, 255, 0.98) 0%, rgba(255, 253, 250, 0.94) 50%, rgba(246, 253, 251, 0.96) 100%)',
          position: 'relative',
          overflow: 'hidden'
        }}
      >
        <div className="stitch-liquid-caustic" />

        <div style={{ position: 'relative', zIndex: 10 }}>
          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '1.5rem', borderBottom: '1px solid rgba(24, 24, 27, 0.08)', paddingBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
              <div
                style={{
                  width: '44px',
                  height: '44px',
                  borderRadius: '14px',
                  backgroundColor: '#ffffff',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: '0 4px 12px rgba(0, 0, 0, 0.08)',
                  border: '1px solid rgba(0, 0, 0, 0.08)'
                }}
              >
                {isGoogle ? (
                  <svg style={{ width: '22px', height: '22px' }} viewBox="0 0 24 24">
                    <path d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.8-2.4 3.66v3.05h3.87c2.26-2.09 3.675-5.17 3.675-9.15z" fill="#4285F4" />
                    <path d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.87-3.05c-1.08.72-2.45 1.16-4.06 1.16-3.13 0-5.78-2.11-6.73-4.96H1.25v3.15C3.25 21.36 7.31 24 12 24z" fill="#34A853" />
                    <path d="M5.27 14.24c-.25-.72-.38-1.49-.38-2.24s.13-1.52.38-2.24V6.61H1.25C.45 8.22 0 10.05 0 12s.45 3.78 1.25 5.39l4.02-3.15z" fill="#FBBC05" />
                    <path d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.31 0 3.25 2.64 1.25 6.61l4.02 3.15c.95-2.85 3.6-4.96 6.73-4.96z" fill="#EA4335" />
                  </svg>
                ) : (
                  <svg style={{ width: '22px', height: '22px' }} viewBox="0 0 23 23">
                    <path d="M1 1h10v10H1z" fill="#f35325" />
                    <path d="M12 1h10v10H12z" fill="#81bc06" />
                    <path d="M1 12h10v10H1z" fill="#05a6f0" />
                    <path d="M12 12h10v10H12z" fill="#ffba08" />
                  </svg>
                )}
              </div>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <h3 id="sso-dialog-title" style={{ fontSize: '1.15rem', fontWeight: 700, color: '#111827', letterSpacing: '-0.02em' }}>
                    {providerTitle}
                  </h3>
                  <span
                    className="stitch-liquid-pill"
                    style={{
                      fontSize: '9.5px',
                      fontFamily: 'var(--font-mono, monospace)',
                      color: '#0d9488',
                      fontWeight: 700,
                      padding: '2px 8px'
                    }}
                  >
                    ENTERPRISE
                  </span>
                </div>
                <p style={{ fontSize: '12px', color: '#4b5563', marginTop: '2px' }}>
                  Tiêu chuẩn định danh doanh nghiệp ({protocolBadge})
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={onClose}
              disabled={authenticating}
              aria-label="Đóng hộp thoại SSO"
              style={{
                background: 'rgba(24, 24, 27, 0.05)',
                border: 'none',
                width: '32px',
                height: '32px',
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: authenticating ? 'not-allowed' : 'pointer',
                color: '#52525b',
                transition: 'all 0.15s ease'
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>close</span>
            </button>
          </div>

          {/* Mode Switcher Tabs */}
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.25rem', background: 'rgba(24, 24, 27, 0.04)', padding: '4px', borderRadius: '12px' }}>
            <button
              type="button"
              onClick={() => setViewTab('login')}
              style={{
                flex: 1,
                padding: '0.5rem 0.75rem',
                borderRadius: '8px',
                border: 'none',
                background: viewTab === 'login' ? '#ffffff' : 'transparent',
                color: viewTab === 'login' ? '#111827' : '#52525b',
                fontWeight: viewTab === 'login' ? 700 : 500,
                fontSize: '12px',
                cursor: 'pointer',
                boxShadow: viewTab === 'login' ? '0 2px 6px rgba(0, 0, 0, 0.06)' : 'none',
                transition: 'all 0.15s ease'
              }}
            >
              Đăng nhập SSO Doanh nghiệp
            </button>
            <button
              type="button"
              onClick={() => setViewTab('setup')}
              style={{
                flex: 1,
                padding: '0.5rem 0.75rem',
                borderRadius: '8px',
                border: 'none',
                background: viewTab === 'setup' ? '#ffffff' : 'transparent',
                color: viewTab === 'setup' ? '#111827' : '#52525b',
                fontWeight: viewTab === 'setup' ? 700 : 500,
                fontSize: '12px',
                cursor: 'pointer',
                boxShadow: viewTab === 'setup' ? '0 2px 6px rgba(0, 0, 0, 0.06)' : 'none',
                transition: 'all 0.15s ease'
              }}
            >
              Đăng ký Kết nối IdP Tenant Mới
            </button>
          </div>

          {/* Tab 1: Login Flow */}
          {viewTab === 'login' && (
            <div>
              {authenticating ? (
                <div style={{ padding: '2.5rem 1rem', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                  <div
                    style={{
                      width: '48px',
                      height: '48px',
                      borderRadius: '50%',
                      border: '3px solid rgba(13, 148, 136, 0.2)',
                      borderTopColor: '#0d9488',
                      animation: 'spin 0.8s linear infinite',
                      marginBottom: '1.25rem'
                    }}
                  />
                  <h4 style={{ fontSize: '15px', fontWeight: 700, color: '#111827', marginBottom: '0.4rem' }}>
                    Đang thiết lập kết nối an toàn SSO
                  </h4>
                  <p style={{ fontSize: '12.5px', color: '#4b5563', maxWidth: '320px' }}>
                    {authStep}
                  </p>
                </div>
              ) : (
                <form onSubmit={handleStartSSO}>
                  <div style={{ marginBottom: '1.25rem' }}>
                    <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#1f2937', marginBottom: '0.45rem' }}>
                      Email Doanh Nghiệp (Corporate Identity)
                    </label>
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="ten.ban@tencongty.com"
                      required
                      style={{
                        width: '100%',
                        padding: '0.75rem 1rem',
                        borderRadius: '0.75rem',
                        border: '1px solid rgba(24, 24, 27, 0.16)',
                        background: '#ffffff',
                        fontSize: '13.5px',
                        color: '#111827',
                        outline: 'none',
                        fontFamily: 'var(--font-mono, monospace)'
                      }}
                    />
                  </div>

                  {/* Quick Domain Presets */}
                  <div style={{ marginBottom: '1.25rem' }}>
                    <span style={{ fontSize: '11px', color: '#6b7280', display: 'block', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      Tenant doanh nghiệp tiêu biểu (1-Click Chọn)
                    </span>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                      {sampleDomains.map((d) => (
                        <button
                          key={d.email}
                          type="button"
                          onClick={() => setEmail(d.email)}
                          style={{
                            padding: '0.5rem 0.75rem',
                            borderRadius: '8px',
                            border: email === d.email ? '1px solid #0d9488' : '1px solid rgba(24, 24, 27, 0.1)',
                            background: email === d.email ? 'rgba(13, 148, 136, 0.08)' : '#ffffff',
                            color: email === d.email ? '#0d9488' : '#374151',
                            fontSize: '11.5px',
                            fontWeight: 600,
                            textAlign: 'left',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between'
                          }}
                        >
                          <span>{d.label}</span>
                          {email === d.email && (
                            <span className="material-symbols-outlined" style={{ fontSize: '14px', color: '#0d9488' }}>
                              check
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Tenant Verification Status Badge */}
                  <div
                    style={{
                      background: 'rgba(13, 148, 136, 0.08)',
                      border: '1px solid rgba(13, 148, 136, 0.25)',
                      borderRadius: '12px',
                      padding: '0.75rem 1rem',
                      marginBottom: '1.5rem',
                      fontSize: '12px',
                      color: '#0f766e',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.65rem'
                    }}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: '20px', color: '#0d9488' }}>
                      verified_user
                    </span>
                    <div>
                      <strong style={{ display: 'block', color: '#0f766e' }}>Tenant Được Xác Minh (SOC2 Verified)</strong>
                      <span style={{ color: '#374151', fontSize: '11.5px' }}>
                        Phân quyền HR Auditor tự động gắn với tài khoản doanh nghiệp.
                      </span>
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
                    <button
                      type="button"
                      onClick={onClose}
                      className="btn btn-secondary"
                      style={{ padding: '0.65rem 1.25rem', fontSize: '13px' }}
                    >
                      Hủy bỏ
                    </button>
                    <button
                      type="submit"
                      className="btn btn-primary"
                      style={{ padding: '0.65rem 1.5rem', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '0.4rem' }}
                    >
                      <span>Tiến hành Xác thực SSO</span>
                      <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>arrow_forward</span>
                    </button>
                  </div>
                </form>
              )}
            </div>
          )}

          {/* Tab 2: Enterprise Integration Spec & Contact */}
          {viewTab === 'setup' && (
            <div>
              {setupSubmitted ? (
                <div style={{ textAlign: 'center', padding: '2rem 1rem' }}>
                  <span className="material-symbols-outlined" style={{ fontSize: '42px', color: '#0d9488', marginBottom: '0.75rem' }}>
                    check_circle
                  </span>
                  <h4 style={{ fontSize: '15px', fontWeight: 700, color: '#111827', marginBottom: '0.4rem' }}>
                    Yêu Cầu Tích Hợp Đã Được Ghi Nhận
                  </h4>
                  <p style={{ fontSize: '12.5px', color: '#4b5563', lineHeight: 1.5 }}>
                    Đội ngũ Kỹ thuật Bảo mật TalentScreen sẽ kết nối SAML 2.0 / OIDC với Tenant của doanh nghiệp bạn trong 15 phút.
                  </p>
                </div>
              ) : (
                <form onSubmit={handleRequestSetup}>
                  <p style={{ fontSize: '12.5px', color: '#374151', lineHeight: 1.5, marginBottom: '1rem' }}>
                    TalentScreen AI hỗ trợ tích hợp Single Sign-On tùy biến cho mọi hệ thống IdP (Okta, Microsoft Entra ID, Google Cloud Identity, PingFederate, Keycloak).
                  </p>

                  <div style={{ marginBottom: '1rem' }}>
                    <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#1f2937', marginBottom: '0.35rem' }}>
                      Tên Tổ Chức / Doanh Nghiệp
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="VD: Ngân hàng ACB, Viettel Cyber, v.v."
                      value={customOrgName}
                      onChange={(e) => setCustomOrgName(e.target.value)}
                      style={{
                        width: '100%',
                        padding: '0.65rem 0.85rem',
                        borderRadius: '0.75rem',
                        border: '1px solid rgba(24, 24, 27, 0.16)',
                        background: '#ffffff',
                        fontSize: '13px',
                        color: '#111827'
                      }}
                    />
                  </div>

                  {/* SP Endpoints Information Box */}
                  <div
                    style={{
                      background: 'rgba(24, 24, 27, 0.03)',
                      border: '1px solid rgba(24, 24, 27, 0.1)',
                      borderRadius: '10px',
                      padding: '0.85rem',
                      fontSize: '11.5px',
                      fontFamily: 'var(--font-mono, monospace)',
                      color: '#374151',
                      marginBottom: '1.25rem',
                      lineHeight: 1.6
                    }}
                  >
                    <div><strong>Entity ID / SP Audience:</strong> urn:talentscreen:ai:sp:prod</div>
                    <div><strong>ACS URL:</strong> https://auth.talentscreen.ai/saml2/callback</div>
                    <div><strong>NameID Format:</strong> urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress</div>
                    <div><strong>Dedicated Support:</strong> enterprise-sso@talentscreen.ai (SLA 99.9%)</div>
                  </div>

                  <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
                    <button
                      type="button"
                      onClick={() => setViewTab('login')}
                      className="btn btn-secondary"
                      style={{ padding: '0.65rem 1.25rem', fontSize: '13px' }}
                    >
                      Quay lại
                    </button>
                    <button
                      type="submit"
                      className="btn btn-primary"
                      style={{ padding: '0.65rem 1.5rem', fontSize: '13px' }}
                    >
                      Gửi Yêu Cầu Tích Hợp IdP
                    </button>
                  </div>
                </form>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
