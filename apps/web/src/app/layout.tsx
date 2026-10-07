import type { Metadata } from "next";
import "./globals.css";
import AppShell from "../components/AppShell";
import { ToastProvider } from "../components/Toast";

export const metadata: Metadata = {
  title: "TalentScreen AI | Không gian tuyển dụng",
  description: "Không gian HR rà soát CV theo JD, tiêu chí và bằng chứng; con người quyết định cuối cùng.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="vi"><body><ToastProvider><AppShell>{children}</AppShell></ToastProvider></body></html>;
}
