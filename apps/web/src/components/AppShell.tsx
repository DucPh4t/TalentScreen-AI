'use client';

import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { IconShield, IconSparkles, IconFileText } from './Icons';

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isRootLogin = pathname === '/';

  if (isRootLogin) {
    return <>{children}</>;
  }

  return (
    <>
      {/* Global App Header for internal pages matching Travertine Liquid Glass Luxury */}
      <header className="app-header">
        <div className="header-inner">
          <Link href="/dashboard" className="brand-logo" aria-label="TalentScreen AI — trang chủ">
            <div className="brand-icon-box">
              <span className="material-symbols-outlined">neurology</span>
            </div>
            <div className="brand-copy">
              <span className="brand-name">TalentScreen AI</span>
              <span className="brand-pill">Ed. 2025</span>
            </div>
          </Link>

          <nav className="nav-links" aria-label="Điều hướng chính">
            <Link href="/dashboard" className={`nav-link ${pathname === '/dashboard' ? 'active' : ''}`}>
              <IconFileText size={16} />
              <span>Tổng quan</span>
            </Link>
            <Link href="/requisitions" className={`nav-link ${pathname.startsWith('/requisitions') ? 'active' : ''}`}>
              <IconFileText size={16} />
              <span>Đợt tuyển dụng</span>
            </Link>
            <Link href="/sandbox" className={`nav-link ${pathname.startsWith('/sandbox') ? 'active' : ''}`}>
              <IconSparkles size={16} />
              <span>Tập huấn</span>
            </Link>
            <Link href="/retention" className={`nav-link ${pathname.startsWith('/retention') ? 'active' : ''}`}>
              <IconShield size={16} />
              <span>Lưu giữ dữ liệu</span>
            </Link>
          </nav>

          <div className="header-actions">
            <div className="header-audit-badge">
              <span className="audit-dot" />
              <span>SOC2 &amp; ISO 27001 AUDITED</span>
            </div>
            <span className="header-context">Cổng HR (2004)</span>
          </div>
        </div>
      </header>

      <div className="env-banner" role="note">
        <div className="env-banner-inner">
          <span className="env-status-dot" aria-hidden="true" />
          <span>AI đưa ra đánh giá tham khảo đối chiếu rubric. HR kiểm tra bằng chứng và quyết định tuyển dụng cuối cùng.</span>
        </div>
      </div>

      <main className="main-content">
        {children}
      </main>

      <footer className="app-footer">
        <div className="footer-inner">
          <div className="footer-left">
            <strong>TalentScreen AI</strong>
            <span>•</span>
            <span>Nền tảng kiểm định nhân tài thế hệ mới © 2025</span>
          </div>
          <div className="footer-right">
            <span>Tiêu chuẩn ISO 27001</span>
            <span>•</span>
            <span>Bảo vệ quyền riêng tư &amp; Zero-Bias</span>
          </div>
        </div>
      </footer>
    </>
  );
}
