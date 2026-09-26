export default function HomePage() {
  return (
    <main className="container" style={{ paddingTop: '2.5rem', paddingBottom: '3rem' }}>
      <header style={{ marginBottom: '2.5rem' }}>
        <h1 style={{ fontSize: '2rem', fontWeight: 700, marginBottom: '0.75rem', letterSpacing: '-0.02em' }}>
          TalentScreen AI
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '1.1rem', maxWidth: '720px' }}>
          AI hỗ trợ đối chiếu CV với tiêu chí đã duyệt. HR kiểm tra bằng chứng và quyết định bước tiếp theo.
        </p>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem', marginBottom: '2.5rem' }}>
        <div className="card">
          <h2 style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '0.75rem' }}>
            Hệ thống & Trạng thái
          </h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '1rem' }}>
            Kiểm tra trạng thái kết nối backend và các dịch vụ cơ bản.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.875rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.4rem' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Môi trường:</span>
              <span className="badge badge-sandbox">Sandbox</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.4rem' }}>
              <span style={{ color: 'var(--text-secondary)' }}>LLM Provider:</span>
              <span style={{ color: 'var(--accent-primary)', fontWeight: 600 }}>mock (Local safe)</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.4rem' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Quyền quyết định:</span>
              <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>Chỉ HR có quyền</span>
            </div>
          </div>
        </div>

        <div className="card">
          <h2 style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '0.75rem' }}>
            Vị trí tuyển dụng mẫu
          </h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '1rem' }}>
            Chuyên viên phát triển phần mềm Backend Python cho hệ thống nội bộ trường.
          </p>
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: 'auto' }}>
            <span className="badge badge-success">6 tiêu chí rubric</span>
            <span className="badge" style={{ backgroundColor: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8' }}>
              Trọng số 100
            </span>
          </div>
        </div>
      </div>

      <div className="card" style={{ borderColor: 'var(--border-strong)' }}>
        <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.5rem', color: 'var(--text-primary)' }}>
          Nguyên tắc bất biến (Core Invariants)
        </h3>
        <ul style={{ paddingLeft: '1.2rem', color: 'var(--text-secondary)', fontSize: '0.875rem', lineHeight: '1.7' }}>
          <li>Không sử dụng tuổi, giới tính, quê quán, tên trường để đánh giá ứng viên.</li>
          <li>CV gốc không gửi ra bên ngoài; CV thật bắt buộc phải qua bước HR duyệt bản lọc PII (sanitized).</li>
          <li>Mọi tiêu chí được chấm bắt buộc phải có trích dẫn bằng chứng cụ thể từ hồ sơ.</li>
          <li>Thiếu thông tin (insufficient evidence) không được coi là 0 điểm; điểm số do code backend tính toán độc lập.</li>
        </ul>
      </div>
    </main>
  );
}
