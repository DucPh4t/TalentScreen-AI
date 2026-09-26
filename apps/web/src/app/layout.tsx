import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'TalentScreen AI — Hệ Thống Trợ Lý Sàng Lọc Hồ Sơ Kỹ Thuật',
  description: 'Hỗ trợ hội đồng tuyển dụng đánh giá năng lực lập trình dựa trên bằng chứng minh bạch, công bằng và bảo mật tuyệt đối.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi">
      <body>
        <div className="env-banner">
          <div>
            <span style={{ color: '#38bdf8', fontWeight: 600 }}>TalentScreen AI</span>
            <span style={{ margin: '0 0.5rem', color: '#475569' }}>•</span>
            <span>Môi trường: <strong>Local Sandbox</strong></span>
          </div>
          <div>
            <span className="badge badge-open" style={{ fontSize: '0.7rem' }}>
              DeepSeek Model Active
            </span>
          </div>
        </div>

        <header className="app-header">
          <div className="header-inner">
            <a href="/" className="brand-logo">
              <span className="brand-badge">TS-AI</span>
              <span>TalentScreen AI</span>
            </a>
            <nav className="nav-links">
              <a href="/requisitions" className="nav-link">Đợt tuyển dụng</a>
              <a href="/retention" className="nav-link">Chính sách lưu trữ</a>
            </nav>
          </div>
        </header>

        <main className="main-content">
          {children}
        </main>
      </body>
    </html>
  );
}
