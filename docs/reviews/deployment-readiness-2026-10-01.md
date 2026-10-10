# TalentScreen AI — Review khả năng triển khai, 01/10/2026

## Kết luận và phạm vi

**Có thể dựng sandbox/staging nội bộ bằng Docker. Chưa đủ bằng chứng để phát hành công khai và dùng AI hỗ trợ quyết định trên đợt tuyển dụng thật.** G1–G7 chưa được ký qua review này.

Review thực hiện trên `/Users/nguyenducphat/TalentScreen AI/`, giữ các thay đổi đang có. Không triển khai cloud, không dùng CV thật, không gọi DeepSeek trả phí, không công bố khóa. Môi trường kiểm thử tách riêng: Compose project `talentscreen-review-20261001`, PostgreSQL/volume riêng, backend loopback 18000, web loopback 12004. App local 2004 và dữ liệu thật không dùng làm môi trường smoke. Migration bổ sung được áp dụng trên DB local sau khi đã qua tests.

## Những lỗi đã sửa trong lượt review

| Mức | Lỗi trước sửa | Bản sửa / xác minh |
|---|---|---|
| P0 triển khai | Docker backend lấy sai build context; không có root Alembic config/seed; wheel có thể thiếu package app | Build từ repo root, copy app đúng thứ tự, đóng gói migrations + rubric/question seeds; chạy migration container |
| P0 triển khai | Proxy Next có thể trỏ 127.0.0.1 bên trong web container; thiếu next.config runtime | Truyền BACKEND_API_URL lúc build và giữ next.config; smoke đi qua frontend proxy |
| P0 triển khai | Worker ở mạng internal không có egress; kế thừa HTTP healthcheck mặc dù là CLI | Worker tham gia edge + DB network; bỏ probe HTTP sai; kiểm tra bằng job thật với mock |
| P0 dữ liệu | Authenticated user ngoài đợt có thể xem/hủy job, gọi sweep | Scope job theo application/document/interview + membership; cancel Owner/Admin; sweep Admin; audit khi hủy; outsider tests |
| P1 bảo mật | Diagnostic cấu hình truy cập vô danh; pilot có thể dùng signing key mặc định / HTTP | Diagnostic Admin-only; pilot yêu cầu key >=32 ký tự, origin HTTPS, bật approval; tắt OpenAPI pilot; Secure cookies với HTTPS |
| P1 chi phí | Hai worker đầu tiên có thể tạo hai kỳ ngân sách; settlement lặp cộng chi phí hai lần | Transaction advisory lock khi tạo kỳ; settlement idempotent; chặn số tiền âm; concurrent reservation/settlement regression |
| P1 vận hành | Dashboard có số queue wait cố định, price verified luôn true, readiness không kiểm tra schema/ghi storage | Telemetry thật hoặc null; price flag dựa trên cấu hình; readiness thử ghi/đọc storage và kiểm tra Alembic head; stale schema test trả 503 |
| P1 nghiệp vụ | Unique constraint ngăn reviewer chấm rubric mới trên cùng thế hệ CV | Migration e43a2f981207 đưa rubric vào khóa snapshot; giữ nhãn cũ; đánh dấu blind_enforced thực tế; regression rubric đổi |
| P1 tải lên | Endpoint đọc toàn bộ upload vào RAM rồi mới kiểm tra kích thước | Đọc tối đa giới hạn file + 1 byte, trả 413 khi quá giới hạn; ingress vẫn phải hạn chế toàn bộ request |
| P1 dependency | npm audit báo PostCSS high, backend container cài runtime phiên bản tự trôi | Next 15.5.27 + PostCSS 8.5.28; khóa 44 Python runtime packages; audit lại |
| P1 UI | Admin xem intake nhưng không xem queue metadata; nút matrix/chấm độc lập hiện sai vai trò; lỗi tải metadata bị ghi thành chưa sẵn sàng | Queue metadata cho Admin theo chính sách intake; matrix Owner-only, chấm độc lập Reviewer-only; lỗi tải hiển thị chưa xác định; nhãn có bản đánh giá không khẳng định bằng chứng còn hiệu lực |
| P1 tài liệu | Runbook tuyên bố zero-downtime/SEC-11 hoàn chỉnh khi chưa có bằng chứng | Viết lại đúng Compose, maintenance, rollback constraints và recovery gaps |

P0 ở bảng là mức ảnh hưởng của lỗi đã sửa, không phải chứng nhận an toàn tổng thể. Docker chạy được không thay thế đánh giá nghiệp vụ/fairness/human sign-off.

## Bằng chứng kiểm thử

- Backend: **145/145 tests passed** trong lượt cuối, trên PostgreSQL Docker dùng một lần; database app không bị dùng cho pytest. Runtime local đã đồng bộ requirements.lock của image deploy. Script ép sandbox + mock và xóa API key khỏi môi trường test.
- Frontend: Next production build qua compile, type/lint checks, static-page generation. Dev/build dùng distDir riêng để tránh đè CSS.
- npm audit: **0 vulnerabilities reported** tại thời điểm kiểm tra.
- pip-audit với 44 packages trong requirements.lock: **No known vulnerabilities found**. Không phải kiểm thử penetration hay scan toàn bộ image OS.
- Compose config --quiet hợp lệ; backend và frontend images build được trên Linux ARM64 Docker Desktop.
- Stack isolated: migrate exit 0; DB/backend/web healthy; worker hoàn thành ingestion/assessment jobs.
- HTTP smoke qua frontend production: anonymous me/diagnostic 401; sai login 401; thiếu CSRF 403; đăng nhập/me/logout thành công; tạo JD, seed/approve rubric, JD egress, mở đợt, tạo application, upload DOCX synthetic, worker ingest, raw grant và approve sanitized, assessment mock, 6 tiêu chí, từng quote khớp source span, comparison và metrics. Owner bị từ chối reviewer context là kết quả đúng chính sách.
- Browser: sai mật khẩu hiện lỗi tiếng Việt; đúng mật khẩu chuyển dashboard; trang đợt hiển thị dữ liệu synthetic. Lỗi queue admin được phát hiện qua browser, sửa và xác minh lại trên image cuối: có trạng thái Đã rà soát, không có lỗi queue, không hiện nút matrix/chấm độc lập cho admin không được phân vai tương ứng.
- Test concurrency từng phát hiện trường hợp hai caller lấy khóa khác thứ tự vào hàm. Đã chuyển timestamp sang sau khi lấy advisory lock và bổ sung regression ép caller vào trước nhưng lấy khóa sau; không bỏ qua test thất bại.
- Local database migration: 9ac6410bf15d → e43a2f981207 thành công.
- Khi kiểm tra cuối, server dev local đang tắt; đã khởi động lại frontend 2004/backend 8000. Probe GET: trang 2004 HTTP 200, CSS HTTP 200 đúng text/css, backend readiness HTTP 200.
- Containers, networks, volumes và credentials của project staging riêng đã dọn sau kiểm thử; database/volume `talentscreen-postgres` được giữ. Images review vẫn ở Docker cache để tái sử dụng; chúng không chứa `.env` hoặc CV thật.

Chưa kiểm thử gọi provider thật, tải 50–100 CV đồng thời, mạng/429/timeout thực tế, multi-instance cloud, AMD64, TLS ingress hoặc restore dữ liệu sau xóa. Không lấy kết quả mock làm độ chính xác của DeepSeek.

## Các điểm còn chặn phát hành thật

### 1. Khôi phục sau xóa / backup volume — P0 trước khi dùng dữ liệu thật

`backup.sh` đọc host PRIVATE_STORAGE_ROOT, trong khi Compose dùng named volume. Chỉ backup được DB hoặc một thư mục host trống có thể bị hiểu sai là backup đầy đủ. DB và blob không được snapshot nguyên tử; writers phải được dừng. Migration/ledger CLI restore dùng local settings có thể lệch target psql. Cần wrapper container-native và kiểm tra manifest chứa đủ blobs.

Ledger hiện nằm cùng DB backup. Nếu backup tại t0 và ứng viên yêu cầu xóa t1 > t0, restore bản t0 không có lệnh xóa t1 để replay. `apply_deletion_ledger` cũng chủ yếu re-tombstone, chưa chứng minh physical purge cho snapshot cũ. Phải giữ ledger mới nhất ở nơi độc lập và drill: backup → delete → restore backup cũ → import ledger mới → purge text/files/identity/labels → assert không truy cập được. Chưa gọi SEC-11 hoặc G6 đạt.

### 2. Ingress công khai / đăng nhập — P0 trước khi mở Internet

Compose hiện chỉ bind loopback; chưa có domain/cert/HTTPS ingress đã kiểm thử, login rate limiting phân tán, per-account abuse protection và request-body limits toàn tuyến. Cần cấu hình TLS đúng APP_ORIGIN và probe cookie Secure/CSRF, hạn chế login theo IP + tài khoản, hạn chế upload và trusted proxies. CORS không thay thế rate limiting. Không đổi bind sang 0.0.0.0 để bỏ qua phần này.

### 3. Nghiệm thu AI và nghiệp vụ — P0 trước hỗ trợ quyết định thật

Cần reviewer HR và IT thật, nhãn độc lập trước khi xem AI, holdout khóa trước chỉnh prompt/rubric, kiểm tra agreement per-criterion, coverage, grounding và fairness. AI đóng vai HR/IT là test mô phỏng, không tạo ra bằng chứng độc lập. `blind_enforced` chỉ mô tả chế độ lúc nộp nhãn; không chứng minh người đó chưa xem AI qua chế độ khác trước đó. G5/G7 cần protocol và người chịu trách nhiệm trường ký; các gates khác cần đối chiếu artifact thực tế.

### 4. Provider và ngân sách — P1 trước bật batch trả phí

Chưa live-probe lại DeepSeek trong review này. Cần verify model/base URL, schema, timeout/429, cost/token usage với dữ liệu synthetic được duyệt; cập nhật giá và RATE_CARD_VERIFIED_AT đúng bằng chứng. Kiểm tra allowance, unknown-outcome reconciliation và pause batch khi ngân sách thiếu. Budget hiện là kỳ 30 ngày, không phải cap $10/ngày.

### 5. Vận hành / retention — P1 trước pilot

Worker health mới dựa trên lease job, không có idle heartbeat. Chưa có maintenance scheduler và alert delivery; retention chỉ chuyển status backup sau thời gian, không xóa backup objects. Cần heartbeat process, scheduled sweeps, backup lifecycle thật, alarm destination, và diễn tập worker chết/lease-expiry/cancel/provider retry với artifact. Đo p95/SLO/chi phí trên workload được duyệt; tests pass không chứng minh xử lý 95% CV dưới 5 phút.

## Giới hạn sản phẩm cần công bố

MVP hiện dành cho Backend Python với 6 criterion chuẩn và full-text baseline. Rubric động/JD-to-rubric đa vị trí, live interview scorecard, export dossier và email workflow chưa được coi là feature thương mại hoàn tất. Không quảng cáo hybrid pgvector ranking hoặc tuyển mọi vị trí khi validator vẫn cố định. Ưu tiên đảm bảo correctness/privacy trước mở rộng.

## Thứ tự làm tiếp

1. Container-native backup/recovery + external latest deletion ledger + drill SEC-11.
2. Chọn môi trường staging/domain, thiết lập TLS/ingress/throttling/upload limits, scan image và pin digests; verify target CPU architecture.
3. Heartbeat + maintenance schedule + alert + load/failure drills.
4. Provider synthetic verification và kiểm tra budget dựa trên giá đã xác minh.
5. Human holdout/shadow nghiệm thu, cập nhật bảng G1–G7 bằng artifact thật; chỉ chuyển assisted sau phê duyệt.

Xem `docs/runbooks/migration_and_restore.md` cho hướng dẫn vận hành đã sửa. Các kiểm thử tạo dữ liệu synthetic trong project tạm; cleanup chỉ được áp dụng đúng project đó, không xóa volume của app local.
