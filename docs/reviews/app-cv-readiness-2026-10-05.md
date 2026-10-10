# TalentScreen AI — Kiểm tra chạy app và xem CV, 05/10/2026

## Kết luận

App đủ để trình diễn nội bộ luồng tiếp nhận PDF → đọc nội dung → rà soát bản đã che và mở CV PDF gốc có kiểm soát → đánh giá mock → chờ HR quyết định. Đã kiểm tra trực tiếp cả văn bản đã che và PDF gốc hiển thị trên canvas trong bản dev sau khi khởi động lại; production build cũng qua. **Chưa đủ bằng chứng nghiệm thu để hỗ trợ quyết định trong đợt tuyển dụng thật hoặc phát hành công khai.** Không ký G1–G7 bằng kiểm thử này.

Phạm vi: chỉ `/Users/nguyenducphat/TalentScreen AI/`. Không gọi DeepSeek, không quyết định tuyển dụng và không thay đổi hồ sơ thật. Ba PDF do agent tự tạo, ghi rõ dữ liệu hư cấu. Chúng không phải holdout, real-shadow hoặc nhãn HR/IT độc lập. Các approval trong đợt demo chỉ để kiểm tra phần mềm.

## App đang chạy

- Frontend: http://localhost:2004.
- Backend: http://127.0.0.1:8001. Cổng 8000 đang thuộc VXA Travel; không dừng ứng dụng đó.
- PostgreSQL hiện có và worker TalentScreen đang chạy.
- APP_ENV=sandbox, LLM_PROVIDER=mock. API key có được cấu hình không đồng nghĩa provider DeepSeek đang được sử dụng.
- Tài khoản `hr_demo_1005`: chỉ role recruiter, không phải admin; chỉ truy cập đợt demo vừa tạo. Mật khẩu cấp riêng trong trao đổi, không lưu ở repo. Không thay mật khẩu/tài khoản cũ.
- Đợt: `8f45a1bc-2e17-4b80-8ca3-ddb7b5948bad`.
- Ba hồ sơ: `CAND-18ABB6` chờ quyết định (mock); `CAND-4A974A` sẵn sàng phân tích; `CAND-1A178E` cần rà soát bản đã che.

Khởi chạy lại từ thư mục gốc, trong ba terminal:

```sh
make dev-backend BACKEND_PORT=8001
make dev-web BACKEND_PORT=8001
make dev-worker
```

Cần PostgreSQL đang chạy và `.env` đã cấu hình. Mặc định Makefile vẫn dùng backend 8000; override cả backend và web nếu cần tránh xung đột cổng.

## Lỗi thật đã sửa

| Lỗi | Bản sửa | Xác minh |
|---|---|---|
| Makefile chạy backend từ services/backend nên không đọc đúng root .env; storage tương đối lệch giữa các tiến trình | Chạy backend/worker từ root; thêm BACKEND_PORT và target dev-worker; proxy frontend theo cùng cổng | Readiness qua frontend 200, DB/storage/schema đều true; upload/worker xử lý được ba PDF |
| Hai raw grants còn hiệu lực cùng người/hồ sơ làm GET application lỗi 500 vì scalar_one_or_none | Kiểm tra tất cả grants còn hiệu lực và chỉ cho xem filename khi có raw_cv scope | Test hai quyền chồng nhau, quyền khác scope, revoke và expiry; live GET application 200 |
| Thiếu import Decimal ở service assessment và decision | Bổ sung import | Các ca chấm AI và HR revision từng thất bại đã qua lại |
| Worker ghi trạng thái sau failed flush bằng session chưa rollback, khiến process chết | Rollback trước ghi kết quả; unexpected assessment error ghi run failed và kết thúc job, không tự phát lại cùng invocation | Hai ca regression tạo IntegrityError thực: ingestion retry_wait; assessment failed; worker trả kết quả bình thường |
| UI chưa xem CV PDF gốc; native PDF iframe trắng trong browser tích hợp | Tải có session sau khi cấp raw_cv 30 phút, kết xuất bằng PDF.js lên canvas, phân trang; tự hủy bản trong RAM khi đóng/đổi tab/hết hạn; endpoint no-store | Browser mở CV synthetic, canvas hiện nội dung và trạng thái Trang 1/1; production build qua |

Lần chấm mock đầu tiên của demo thực sự thất bại do thiếu Decimal; retry sau đó đụng unique invocation và worker chết. Giữ lịch sử thất bại, đánh dấu tác vụ synthetic đó failed với mã `DEMO_RECOVERY_AFTER_DECIMAL_FIX`, rồi tạo lượt chấm mới đã thành công. Không sửa kết quả thất bại thành thành công. Bản sửa worker không chứng nhận phục hồi đầy đủ khi process chết cứng sau provider call hoặc mất lease.

## Bằng chứng kiểm thử

- Backend cuối: **158/158 tests passed**, PostgreSQL/pgvector dùng một lần, không dùng DB ứng dụng cho pytest. Có một cảnh báo deprecation HTTP 413; không phải test failure.
- Frontend `npm run build`: exit 0 sau khi tích hợp PDF.js 6.3.289; compile/type checks và tạo routes thành công. `npm install` báo 0 vulnerabilities. Dev/build dùng thư mục output riêng.
- `git diff --check`: qua.
- HTTP qua frontend proxy: login/me/logout; tạo JD/rubric, duyệt rubric và JD demo; mở đợt; upload ba PDF; ingestion thành công; quyền rà soát; duyệt hai bản đã che; mock assessment; seed/approve question bank; kiểm tra ba stage.
- Role isolation: list requisitions của demo trả đúng một đợt, me chỉ role recruiter.
- Readiness `/api/v1/admin/readiness`: HTTP 200, database/storage/schema true. Readiness này không đo AI quality hay worker heartbeat.
- PDF gốc synthetic `/api/v1/documents/7766f990-246e-4382-b450-87fdfde0572e/raw-preview`: HTTP 200 application/pdf, bytes bắt đầu bằng %PDF với raw grant còn hiệu lực.
- Browser: đăng nhập → dashboard → đợt có ba hồ sơ → chi tiết hồ sơ → tab Rà soát CV. Văn bản đã che lấy từ PDF; CV gốc được tải sau khi cấp raw_cv, kết xuất lên canvas với điều hướng trang. Thử trực tiếp native iframe cho kết quả trắng nên đã dùng PDF.js. Tab đánh giá ghi rõ mock không đánh giá năng lực, cả sáu tiêu chí N/A, coverage 0; không coi là điểm thật.
- Browser verification used synthetic demo CVs and local PDF rendering; the screenshots were removed, while the interaction and test results remain documented above.

Không kiểm thử lại Docker/cloud/TLS, provider live, DOCX/OCR, PDF nhiều trang, tải 50–100 CV, export hoặc toàn bộ luồng quyết định HR ở browser trong lượt này. Các báo cáo trước có phạm vi và ngày riêng.

## Các điểm còn thiếu

1. **Định dạng ngoài PDF:** viewer hiện xử lý PDF; DOCX chưa có bản PDF render để xem trực tiếp. Cần bổ sung chuyển DOCX an toàn thành PDF trong pipeline, kiểm tra bố cục tiếng Việt và giữ quyền/audit nhất quán. PDF viewer dùng canvas nên không có toolbar tải/in của browser; PDF bytes ở bộ nhớ trình duyệt trong thời gian xem. Đây không phải DRM và người dùng vẫn có thể chụp màn hình.
2. **DeepSeek/AI thật:** runtime hiện mock. Cần kiểm tra synthetic live với provider/model thực tế và schema, usage/cost, timeout/429 trước khi bật trên batch thật. N/A của mock không chứng minh matching, grounding hoặc fairness. Không đổi provider âm thầm trong lượt kiểm tra này.
3. **Nghiệm thu nghiệp vụ:** chưa có bằng chứng mới cho holdout khóa trước chỉnh prompt, nhãn HR/IT thật độc lập, agreement và real-shadow. Agent đóng vai hai người chỉ là mô phỏng; cần người chịu trách nhiệm trường ký gate theo dữ liệu nghiệm thu.
4. **Phạm vi rubric:** schema assessment vẫn yêu cầu đúng sáu tiêu chí; HR revision còn duyệt CriterionId chuẩn. Nhãn commit “dynamic rubric” không đủ để tuyên bố hỗ trợ mọi vị trí IT. Cần kiểm thử xuyên suốt JD-to-rubric, assessment, revision, comparison, interview khi mở rộng.
5. **Dữ liệu local lẫn fixtures:** có nhiều đợt/tài khoản/hồ sơ test cũ, một số bản ghi không còn blob. Tài khoản demo riêng tránh nhiễu giao diện nhưng chưa sửa tính toàn vẹn toàn bộ DB. Không tự xóa dữ liệu cũ. Cần inventory provenance và kiểm tra blob của đúng đợt thật trước pilot.
6. **Vận hành trước dùng thật:** tiếp tục các blockers trong deployment-readiness-2026-10-01.md: backup/restore và deletion ledger độc lập; idle heartbeat/scheduler/alerts; load/SLO; TLS/ingress/login throttling/upload limits khi public. Đặc biệt cần drill process chết sau LLM call và lease expiry để không phát lại invocation/budget hoặc treo assessment. Bản rollback worker hôm nay chỉ xử lý exception còn bắt được.

## Thứ tự tiếp theo

1. Thêm renderer DOCX→PDF và kiểm tra file PDF nhiều trang, lỗi hỏng/không hỗ trợ.
2. Kiểm thử synthetic qua DeepSeek thật, failure/replay và giới hạn chi phí.
3. Tách fixture khỏi dữ liệu pilot; xác minh đầy đủ blob/bản đã che của bộ CV được phép sử dụng.
4. Hoàn tất recovery/deletion và vận hành; thu nhãn/holdout/shadow thật theo protocol rồi nghiệm thu G1–G7.

Build/tests qua là điều kiện phần mềm cần có, không phải chứng nhận chất lượng tuyển dụng.
