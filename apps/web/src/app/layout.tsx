import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'TalentScreen AI — Hệ thống hỗ trợ tuyển dụng dựa trên bằng chứng',
  description: 'Trợ lý AI hỗ trợ HR đối chiếu CV với tiêu chí JD đã phê duyệt. Quyết định cuối cùng thuộc về HR.',
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
            <span className="badge badge-sandbox">Sandbox · Dữ liệu mẫu</span>
            <span style={{ marginLeft: '0.8rem', color: '#a8a29e' }}>
              Môi trường thử nghiệm cục bộ với dữ liệu synthetic
            </span>
          </div>
          <div style={{ color: '#78716c', fontSize: '0.8rem' }}>
            TalentScreen AI v0.1.0
          </div>
        </div>
        {children}
      </body>
    </html>
  );
}
