"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "../lib/api";
import { useToast } from "./Toast";
import { IconBarChart, IconFileText, IconShield, IconX, IconChevronRight } from "./Icons";

const navigation = [
  { href: "/dashboard", label: "Tổng quan", icon: IconBarChart },
  { href: "/requisitions", label: "Đợt tuyển dụng", icon: IconFileText },
  { href: "/retention", label: "Dữ liệu & riêng tư", icon: IconShield },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { error } = useToast();
  const [menuOpen, setMenuOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  useEffect(() => { setMenuOpen(false); }, [pathname]);

  if (pathname === "/") return <>{children}</>;

  const currentPage = pathname.startsWith("/applications") ? "Hồ sơ ứng viên"
    : navigation.find(item => pathname.startsWith(item.href))?.label || "Không gian tuyển dụng";

  async function logout() {
    setLoggingOut(true);
    try {
      await api.logout();
      router.replace("/");
    } catch {
      error("Chưa đăng xuất được. Vui lòng thử lại.");
    } finally { setLoggingOut(false); }
  }

  return (
    <div className="workspace-shell">
      <a className="skip-link" href="#main-content">Chuyển đến nội dung chính</a>
      <aside className="workspace-sidebar" aria-label="Không gian tuyển dụng">
        <div className="sidebar-brand-row">
          <Link href="/dashboard" className="product-brand" aria-label="TalentScreen AI — tổng quan" onClick={() => setMenuOpen(false)}>
            <span className="product-mark" aria-hidden="true">ts</span>
            <span>TalentScreen<span className="brand-ai"> AI</span><small>Không gian tuyển dụng</small></span>
          </Link>
          <button type="button" className="mobile-menu-toggle" aria-expanded={menuOpen} aria-controls="workspace-navigation"
            onClick={() => setMenuOpen(!menuOpen)} onKeyDown={event => { if (event.key === "Escape") setMenuOpen(false); }}>
            {menuOpen ? <IconX size={18} /> : <IconChevronRight size={18} />}<span>{menuOpen ? "Đóng" : "Menu"}</span>
          </button>
        </div>
        <nav id="workspace-navigation" className={`workspace-navigation ${menuOpen ? "is-open" : ""}`} aria-label="Điều hướng chính"
          onKeyDown={event => { if (event.key === "Escape") { setMenuOpen(false); document.querySelector<HTMLButtonElement>(".mobile-menu-toggle")?.focus(); } }}>
          <p className="navigation-caption">Không gian làm việc</p>
          {navigation.map(({ href, label, icon: Icon }) => {
            const active = pathname.startsWith(href) || (href === "/requisitions" && pathname.startsWith("/applications"));
            return <Link key={href} href={href} className={`workspace-nav-link ${active ? "active" : ""}`} aria-current={pathname.startsWith(href) ? "page" : undefined} onClick={() => setMenuOpen(false)}>
              <Icon size={19} /><span>{label}</span>
            </Link>;
          })}
        </nav>
        <div className="sidebar-assurance"><IconShield size={18} /><div><strong>HR quyết định cuối cùng</strong><p>AI hỗ trợ bằng chứng và đánh giá.</p></div></div>
        <div className="sidebar-product-meta"><span className="status-marker status-open" /> Không gian nội bộ</div>
      </aside>
      <div className="workspace-body">
        <header className="workspace-topbar">
          <span className="topbar-page">{currentPage}</span>
          <div className="topbar-actions"><span className="topbar-assurance"><IconShield size={15} /> Đánh giá có bằng chứng</span>
            <button type="button" className="btn btn-quiet btn-sm" disabled={loggingOut} onClick={() => void logout()}>{loggingOut ? "Đang đăng xuất…" : "Đăng xuất"}</button>
          </div>
        </header>
        <main id="main-content" className="main-content" tabIndex={-1}>{children}</main>
        <footer className="app-footer"><span>TalentScreen AI</span><span>Truy cập theo phân quyền · HR kiểm duyệt kết quả</span></footer>
      </div>
    </div>
  );
}
