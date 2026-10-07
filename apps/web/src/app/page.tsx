"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "../lib/api";
import { IconArrowRight, IconAlertTriangle, IconShield, IconFileText, IconCheckCircle } from "../components/Icons";

export default function HomePage() {
  const router = useRouter();
  const [loginName, setLoginName] = useState("");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [checkingAuth, setCheckingAuth] = useState(true);

  useEffect(() => {
    let active = true;
    api.getMe().then(() => { if (active) router.replace("/dashboard"); })
      .catch(() => { if (active) setCheckingAuth(false); });
    return () => { active = false; };
  }, [router]);

  async function handleLogin(event: React.FormEvent) {
    event.preventDefault();
    setLoginError("");
    setSubmitting(true);
    try {
      await api.login(loginName, password);
      router.replace("/dashboard");
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : "Thông tin đăng nhập không hợp lệ.");
    } finally { setSubmitting(false); }
  }

  return (
    <main className="auth-layout">
      <section className="auth-story" aria-label="TalentScreen AI">
        <a href="/" className="product-brand auth-brand"><span className="product-mark" aria-hidden="true">ts</span><span>TalentScreen<span className="brand-ai"> AI</span></span></a>
        <div className="auth-story-content"><span className="auth-eyebrow">Tuyển dụng, có cơ sở.</span><h1>Hiểu hồ sơ.<br /><span>Chọn đúng bước tiếp.</span></h1><p>Đối chiếu CV với yêu cầu vị trí. Tập trung vào năng lực, kiểm tra từng bằng chứng và giữ quyền quyết định trong tay HR.</p>
          <div className="auth-evidence-visual" aria-label="CV và JD được đối chiếu thành bằng chứng để HR rà soát">
            <div className="auth-source-row"><div><IconFileText size={20} /><strong>CV ứng viên</strong><span>Kỹ năng & kinh nghiệm</span></div><span className="auth-source-plus">+</span><div><IconFileText size={20} /><strong>Yêu cầu vị trí</strong><span>JD & tiêu chí đã duyệt</span></div></div>
            <div className="auth-evidence-result"><span className="auth-result-icon"><IconCheckCircle size={21} /></span><div><strong>Đánh giá đi cùng bằng chứng</strong><span>Trích dẫn rõ nguồn · HR kiểm chứng</span></div><IconArrowRight size={18} /></div>
          </div>
        </div>
        <p className="auth-story-footer"><IconShield size={16} /> Đánh giá tham khảo. Con người quyết định.</p>
      </section>
      <section className="auth-form-panel" aria-labelledby="login-title">
        <div className="auth-panel-meta">Cổng nhân sự <span>Tiếng Việt</span></div>
        <div className="auth-form-wrap">
          <span className="eyebrow">Không gian làm việc</span><h2 id="login-title">Chào mừng trở lại</h2><p className="auth-form-subtitle">Đăng nhập để tiếp tục công việc tuyển dụng.</p>
          {checkingAuth ? <p className="notice" role="status">Đang kiểm tra phiên đăng nhập…</p> : <form onSubmit={handleLogin}>
            {loginError && <div className="notice notice-error" role="alert"><IconAlertTriangle size={17} /><span>{loginError}</span></div>}
            <div className="form-group"><label className="form-label" htmlFor="login-name">Tên đăng nhập</label><input id="login-name" name="username" className="form-input" autoComplete="username" placeholder="Tên đăng nhập nội bộ" value={loginName} onChange={event => setLoginName(event.target.value)} required disabled={submitting} /></div>
            <div className="form-group"><label className="form-label" htmlFor="login-password">Mật khẩu</label><div className="auth-password"><input id="login-password" name="password" className="form-input" type={showPassword ? "text" : "password"} autoComplete="current-password" placeholder="Nhập mật khẩu" value={password} onChange={event => setPassword(event.target.value)} required disabled={submitting} /><button type="button" aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"} aria-pressed={showPassword} onClick={() => setShowPassword(!showPassword)}>{showPassword ? "Ẩn" : "Hiện"}</button></div></div>
            <button className="btn btn-primary auth-submit" type="submit" disabled={submitting || !loginName.trim() || !password}>{submitting ? "Đang đăng nhập…" : "Đăng nhập"}<IconArrowRight size={18} /></button>
            <p className="auth-account-help">Cần cấp tài khoản hoặc đặt lại mật khẩu?<br />Liên hệ quản trị viên nội bộ.</p>
          </form>}
        </div>
        <p className="auth-form-footer"><IconShield size={15} /> Dữ liệu ứng viên được truy cập theo phân quyền.</p>
      </section>
    </main>
  );
}
