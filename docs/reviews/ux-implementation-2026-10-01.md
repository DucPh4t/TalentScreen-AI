# TalentScreen AI — implementation và nghiệm thử UX

Ngày: 2026-10-01. Thư mục làm việc duy nhất: `/Users/nguyenducphat/TalentScreen AI/`.

> **Tư liệu lịch sử:** Tại thời điểm lập báo cáo, Copilot còn tồn tại và các dòng bên dưới ghi lại lần nghiệm thử đó. Chat Copilot đã được gỡ khỏi sản phẩm ở thay đổi sau; bảng phạm vi và kết quả Copilot trong tài liệu này không mô tả ứng dụng hiện tại.

## Kết luận

Các cải tiến UX và Copilot có giới hạn đã được implement và chạy qua kiểm thử backend, build Docker, HTTP và trình duyệt. Local frontend vẫn ở port 2004. Đây là nghiệm thử kỹ thuật MVP; không phải ký G1–G7 hoặc chứng minh độ chính xác, fairness hay mức tương đồng AI–HR trên tuyển dụng thật.

Các thay đổi có sẵn trong working tree, chưa commit/push. Các chỉnh sửa có từ trước được giữ nguyên.

## Phạm vi đã implement

| Nhóm | Hành vi cuối |
| --- | --- |
| Luồng HR | 4 bước theo thứ tự rà soát CV → đánh giá/bằng chứng → quyết định HR → chuẩn bị phỏng vấn; nút bước tiếp theo theo tình trạng nguồn |
| Tiến độ | Trạng thái đọc tệp và phân tích lấy từ server; polling ở tab đang hiển thị; không giả lập phần trăm; lỗi tải được thông báo và có làm mới |
| Dashboard | Đếm toàn bộ công việc còn lại của các đợt open/paused truy cập được; bộ lọc; preview tối đa 5 hồ sơ; nhãn số liệu không che việc tải thiếu |
| Reviewer | Hàng đợi chấm độc lập riêng; hồ sơ chưa nộp nhãn vẫn xuất hiện dù HR đã quyết định; dẫn thẳng vào form; ẩn cột AI/quyết định và nút upload không phù hợp ở trang đợt |
| Tiếp nhận | PDF/DOCX, tối đa 20 tệp/lượt và 10 MiB/tệp; validation trước upload; xử lý tuần tự; cảnh báo đang tải; khóa đóng modal trong lúc tải; theo dõi riêng từng tệp |
| Retry upload | SHA-256 theo nội dung, key idempotency ổn định cho tạo application/upload; key và ID opaque lưu sessionStorage theo user/đợt/hash; không lưu nội dung CV; đăng xuất xóa cache retry; chọn lại cùng tệp trong cùng phiên giúp tiếp tục đúng hồ sơ |
| Rà soát | Tên tiêu chí tiếng Việt; thang điểm 0–4; bằng chứng mở bằng nút dùng bàn phím được; nút điều chỉnh ở từng dòng; xác nhận từng tiêu chí trước quyết định |
| HR override | Chọn đoạn trích đã duyệt; server kiểm tra membership/span/quote/nguồn hiện hành; sửa status/score/rationale/thiếu thông tin; lý do từng thay đổi và tổng hợp; lưu draft rồi finalize; AI gốc và lịch sử được giữ |
| Chấm độc lập | CV và form hai cột trên desktop, một cột trên mobile; chọn đoạn CV; autosave server theo reviewer; khôi phục draft; version conflict; cảnh báo đóng/reload khi chưa lưu; xác nhận trước khóa nhãn |
| Câu hỏi | Quản lý câu hỏi chuẩn tại thiết lập đợt; xem và duyệt đúng nội dung trước dùng; trang ứng viên chỉ tạo gợi ý theo nguồn đánh giá còn hiệu lực |
| Copilot | Owner-only, thu gọn mặc định; hỏi theo hồ sơ đang mở; xem giải thích từ đánh giá AI đã lưu, phần còn thiếu hoặc câu hỏi làm rõ; không quyết định tuyển dụng/gửi thư/thực thi hành động |
| Responsive | Workspace dùng nền ít gây nhiễu; focus bàn phím; thanh điều hướng wrap; recommendation và metrics wrap; bảng cuộn trong wrapper |

Nháp độc lập có thời hạn hiệu lực 24 giờ, được loại khi truy cập sau hết hạn/nguồn đổi hoặc khi xóa CV. Chưa có scheduler chứng minh xóa vật lý mọi nháp ngay đúng mốc 24 giờ. Nháp HR cần bấm lưu; autosave áp dụng cho form chấm độc lập.

## Ranh giới của Copilot

- Model nhận câu hỏi và metadata tiêu chí `{criterion_id, label, status, score}`. Không gửi raw CV hoặc nguyên văn toàn bộ CV cho tính năng này.
- Model chỉ chọn mode và ID trong schema cố định. Server lấy lại rationale, missing information và quote đã lưu, kiểm tra quote với source span và nội dung sanitized. Không dùng văn bản tự sinh của model làm bằng chứng.
- Có đủ CV/JD/rubric đã duyệt và assessment hiện hành trước gọi. Chặn khi assessment mới đang chạy; kiểm tra lại snapshot sau lời gọi.
- Prompt: `copilot-select-v1`, file `services/backend/app/services/copilot_prompt.py`. Request JSON-only, thinking disabled, tối đa 256 token đầu ra, timeout 45 giây.
- Tối đa 3 câu hỏi/phút/actor, giới hạn admission Copilot đồng thời, ledger dự phòng và quyết toán ngân sách. Không tự retry hay fallback provider.
- Lưu hash/version/ID/mã lỗi trong audit/jobs; không lưu toàn bộ hội thoại. Người dùng không nhập thông tin định danh vào câu hỏi. Đây là trợ lý hỏi đáp theo từng hồ sơ, chưa phải agent hội thoại có memory hoặc công cụ tự hành động.

Cấu hình non-thinking đối chiếu [tài liệu DeepSeek](https://api-docs.deepseek.com/guides/thinking_mode/). Kiểm tra key không in giá trị khóa vào báo cáo/log.

## Bằng chứng kiểm thử

### Backend và build

- Lượt cuối: **156 tests passed**, pytest trên PostgreSQL Docker dùng một lần và mock provider. Không dùng DB tuyển dụng thật cho pytest.
- Regression mới: application idempotency khi mất response, payload conflict, nguồn stale, Copilot grounding/rate limit/phân quyền, unsafe source/JD chưa duyệt/provider failure, private draft khôi phục/version conflict/khóa nhãn, fabricated HR quote và assessment pending chặn dùng kết quả cũ.
- Alembic từ schema trống lên `b419ad53ef82` thành công. Local cũng ở schema head mới.
- Next production build hoàn tất compile/type/static generation; backend/web Docker build thành công trên ARM64. `git diff --check` sạch.
- Có một warning Starlette về tên hằng HTTP 413 deprecated; không làm thất bại test.
- Trong môi trường Compose/Bake đã gặp tranh chấp tag do build cả backend/migrate/worker dùng chung image. Build `backend web` một lần, rồi `up --no-build` chạy thành công; runbook đã dùng cách này.

### HTTP và trình duyệt

Staging riêng: Compose project `talentscreen-ux-review`, web loopback 12004/API 18000, DB và blob volume riêng, tài khoản Owner/reviewer test riêng. Chỉ dùng CV DOCX synthetic, không tải 8 CV thật vào môi trường này.

- HTTP smoke cuối qua frontend production: login sai/đúng, anonymous access, CSRF, readiness, JD/rubric duyệt, mở đợt, intake DOCX, worker parsing, sanitization approve, mock assessment 6 tiêu chí/null đúng, source grounding, progress, Copilot, comparison, Owner không impersonate reviewer, metrics và logout: PASS.
- Browser: login sai hiện lỗi tiếng Việt, login đúng đến dashboard; hàng đợi reviewer theo vai trò và link chấm độc lập: PASS.
- Browser upload qua file chooser: DOCX synthetic → trạng thái đang tải → đã tải, chờ đọc → danh sách có hồ sơ ở bước cần rà soát: PASS.
- Browser HR override: thêm bằng chứng Python có thật trong synthetic CV, score 2/4, rationale/lý do → lưu draft → finalize: PASS.
- Browser quyết định: ban đầu bị khóa khi chưa rà soát 6 tiêu chí; xác nhận đủ và ghi request_information trên hồ sơ synthetic: PASS. Không quyết định cho ứng viên thật.
- Browser question bank: tạo, xem và duyệt tại thiết lập đợt; tạo interview từ finalized HR revision → 6 câu hỏi chuẩn: PASS. Mock không bịa thêm follow-up.
- Browser independent review: IT-role và ghi chú được autosave, reload khôi phục đúng; hoàn thiện ghi chú 6 tiêu chí, xác nhận và khóa nhãn → form sửa biến mất: PASS. Nhãn này là diễn tập, không tính vào holdout nghiệm thu.
- Responsive trang assessment 375×812: document scrollWidth 367 ≤ viewport 375; không còn tràn ngang toàn trang. Bảng có cuộn ngang riêng. Đây là kiểm tra một breakpoint, không phải audit mọi thiết bị/trình đọc màn hình.
- Browser console error ở lần quan sát cuối: không có bản ghi error.
- Local probe: frontend2004 HTTP200, stylesheet HTTP200 đúng text/css, `/api/v1/admin/readiness` backend8000 HTTP200/status ready.

### DeepSeek live — synthetic, có thất bại được sửa

Hai lời gọi test tổng cộng, mỗi lượt đúng một request, không retry tự động:

1. Bản đầu HTTP503, 4,587 giây; invocation outcome_unknown, giữ reservation $0.00052170. Chưa có đủ usage để kết luận phí thực tế; không gán chi phí 0 hoặc tự giải phóng reservation.
2. Sau bản sửa explicit thinking disabled: **HTTP200, 1,040 giây**, provider DeepSeek, mode questions, chọn `python_backend`, trả 1 câu hỏi. Ledger succeeded: 467 token vào, 17 token ra, model deepseek-flash. Ước tính theo rate card lưu trong code $0.00016050, không phải hóa đơn provider hay xác minh giá mới ngày này.

File metadata: `ux-copilot-live-2026-10-01.json`. Kết quả không đo độ chính xác scoring của DeepSeek: assessment nguồn của bài test vẫn là mock và Copilot chỉ chọn thông tin có sẵn.

## Những phần còn chặn pilot/public deployment

Các blocker trong `deployment-readiness-2026-10-01.md` vẫn áp dụng: restore sau yêu cầu xóa và deletion ledger độc lập; TLS/ingress/login throttling; heartbeat/maintenance/alerts; workload/load/chaos thực tế; holdout HR và IT thật cùng shadow evaluation. Live probe Copilot không thay thế kiểm thử assessment thật, 429 thực tế, chi phí batch hoặc nghiệm thu G1–G7.

MVP vẫn gồm 6 tiêu chí Backend Python và full-text baseline. Rubric đa vị trí/JD-to-rubric, live scorecard, dossier export và email tự động không thuộc phạm vi cải tiến UX/Copilot của lượt này; chưa được công bố hoàn tất.

Local `.env` giữ `LLM_PROVIDER=mock` và có key đã cấu hình. Lượt live chạy bằng env staging riêng, không tự bật batch trả phí trên dữ liệu thật. Có thể chuyển provider sau khi kiểm tra chính sách/ngân sách và công việc đang chờ.

## Visual verification

Desktop and full-page assessment captures used synthetic data and are not retained in the repository. The interaction findings and environment details above remain the record; no real applicant CV or credential was present.

## Dọn môi trường test

Compose project talentscreen-ux-review cùng network/volumes synthetic đã được dọn sau nghiệm thử; env test chứa khóa cũng đã xóa. Reservation outcome_unknown nêu trên là trạng thái quan sát trước khi dọn database staging; chưa đối soát hóa đơn DeepSeek. App local, .env gốc, database và CV thật được giữ.
