import type { Metadata } from 'next';
import './globals.css';
import AppShell from '../components/AppShell';
import { ToastProvider } from '../components/Toast';

export const metadata: Metadata = {
  title: 'TalentScreen AI | Không gian tuyển dụng',
  description: 'Không gian HR rà soát hồ sơ IT theo JD, rubric và bằng chứng; quyết định cuối cùng thuộc về con người.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi">
      <head>
        <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=Instrument+Serif:ital@0;1&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet" />
      </head>
      <body>
        {/* Continuous luxury travertine desk background for all pages */}
        <div className="global-travertine-bg" aria-hidden="true">
          <img
            alt="Travertine stone desk"
            src="/bgAItalent.png"
          />
          <div className="global-tint-1" />
          <div className="global-tint-2" />
        </div>
        <ToastProvider>
          <AppShell>
            {children}
          </AppShell>
        </ToastProvider>
      </body>
    </html>
  );
}
