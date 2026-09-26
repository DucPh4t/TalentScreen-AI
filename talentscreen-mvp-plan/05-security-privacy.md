# 05 — Bảo mật, quyền dữ liệu và kiểm soát fairness

Đọc cùng [quyết định nền](00-scope-decisions.md), [hợp đồng dữ liệu/API](03-data-api-state-machines.md), [AI](04-ai-rag-prompts.md) và [vận hành](07-operations-deployment.md). Đây là yêu cầu thiết kế/kiểm thử, không phải chứng nhận tuân thủ pháp luật.

## 1. Phạm vi và mô hình đe dọa

Người dùng đã xác nhận được phép dùng DeepSeek theo chính sách trường. Ghi nhận điều này trong cấu hình triển khai; không hỏi lại cùng một quyền. Việc này không tự mở quyền gửi CV cho một vendor khác, đưa hồ sơ lên dịch vụ tracing, lưu dataset công khai, hoặc dùng CV để huấn luyện.

Tài sản cần bảo vệ: file CV, text OCR, danh tính/liên hệ, source spans, embedding, kết quả đánh giá, ghi chú HR, quyết định, bộ gán nhãn, khóa API, session và backup. Tất cả dữ liệu dẫn xuất của CV vẫn là dữ liệu ứng viên; vector không được coi là đã ẩn danh.

Các tác nhân trong threat model: người chưa đăng nhập; reviewer đọc vượt đợt; HR cấp quyền sai; CV chứa lệnh độc hại/HTML/URL; parser bị file bất thường; tác vụ cũ ghi sau khi xóa; người vô tình gửi log hoặc commit bí mật; mất máy/backup. Admin hệ điều hành có thể đọc dữ liệu khi ổ đĩa đang mở khóa là giới hạn của single-host pilot; RBAC ứng dụng không phải cơ chế chống chủ máy có toàn quyền.

Không triển khai đánh giá nét mặt, tính cách, âm thanh, tìm ứng viên trên Internet, tự gửi email hoặc tự từ chối. Parser/LLM không có các tool này.

## 2. Phân loại và ranh giới dữ liệu

| Loại | Ví dụ | Được gửi DeepSeek? | Được vào log thông thường? |
|---|---|---|---|
| D0: synthetic | CV hoàn toàn hư cấu, JD tự soạn, fixtures | Có, khi bật provider và có budget | Chỉ fixture ID, không mặc định log payload |
| D1: raw cá nhân | CV gốc, contact, tên thật, raw OCR, raw filename | Không trong thiết kế này | Không |
| D2: sanitized nhưng có thể liên kết | Mô tả công việc/dự án đã che, source spans | Có sau policy đã cấu hình + HR duyệt bản sanitized version cụ thể | Không |
| D3: assessment/HR | Nhận định, overrides, quyết định, nhãn annotation | Chỉ phần tối thiểu cần cho task đã định nghĩa; HR notes không gửi mặc định | Không |
| D4: vận hành | latency, token counts, error code, random run ID | Không cần gửi | Có; không kèm raw text, contact hoặc đoạn quote |

Luồng egress duy nhất của ứng dụng: DeepSeek adapter nhận `ApprovedSanitizedSnapshot` và task input typed. Không adapter nào nhận `DocumentRaw` hoặc arbitrary storage path. Ngoài runtime, việc tải model Python/Docker phải là bước cài đặt; CV không được đưa vào request tải dependency.

Đối với prompt/dataset evaluation, ưu tiên fixture synthetic. Nhãn HR trên CV thật vẫn nằm trong cùng vùng bảo vệ; tắt external judge và tracing cloud trừ khi phạm vi xử lý đã được cấu hình tương ứng. Không tự coi chính sách cho DeepSeek là chính sách cho một LLM judge khác.

## 3. Authentication và authorization

### 3.1 Session

- Account tạo bởi admin, không public signup. Không có default password dùng chung hoặc credential seed cho môi trường thật.
- Password hash bằng Argon2id qua thư viện duy trì tốt; triển khai chọn thông số theo hướng dẫn thư viện và đo thời gian hash, lưu trong lockfile, không tự viết cryptography. Password tối thiểu 12 ký tự; cho phép passphrase dài; không ghi password vào logs.
- Login trả opaque session cookie; lưu hash token ở server, không localStorage JWT. Xoay session khi login/reset quyền. Idle timeout đề xuất 30 phút, absolute lifetime 8 giờ; hết hạn yêu cầu login lại nhưng form có cảnh báo trước.
- Cookie HttpOnly, SameSite=Lax và Path rõ ràng; Secure bắt buộc ở HTTPS. Local HTTP chỉ bind loopback và ghi nhận development exception; không mở chế độ đó ra LAN.
- Mutation cookie-auth cần CSRF token + kiểm tra Origin đúng allowlist. Không dùng `Access-Control-Allow-Origin: *` cùng credentials.
- Limit login theo account và IP: ví dụ 5 attempts/phút trước cooldown tăng dần; thông báo chung, không tiết lộ account tồn tại. Admin reset bằng thao tác có audit, hủy các session cũ; không gửi mail reset trong MVP.

### 3.2 Quyền và phạm vi

Account có thể có nhiều role explicit; membership của requisition và raw grant vẫn kiểm tra riêng. UI chỉ là lớp hỗ trợ; mọi endpoint và background write phải thực thi quyền ở service/backend.

| Hành động | Admin không có membership | Recruiter owner của requisition | Reviewer được phân công |
|---|---|---|---|
| Quản lý account, runtime config | Có | Không mặc định | Không |
| Xem danh sách/hồ sơ của requisition | Không mặc định | Có | Có trong phạm vi |
| Tạo/sửa JD draft, rubric draft | Không mặc định | Có | Đề xuất qua review nếu được thiết kế; không publish |
| Duyệt rubric và policy ngưỡng | Không | Có | Không |
| Sửa/duyệt sanitized text | Không mặc định | Owner sửa/duyệt cần raw_cv grant | Sửa draft/đánh dấu khi có raw_cv grant; owner duyệt cuối |
| Xem raw CV/contact | Chỉ khi có grant riêng + membership | Chỉ khi có grant riêng | Chỉ khi có grant riêng |
| Tạo assessment/interview draft | Không mặc định | Có | Có nếu membership cho phép |
| Sửa nháp đánh giá/đính nguồn | Không | Có | Có |
| Quyết định vòng tiếp theo | Không | Có | Không |
| Khởi tạo yêu cầu xóa | Người có trách nhiệm dữ liệu theo policy | Có đối với hồ sơ thuộc phạm vi | Gửi đề nghị, không xóa trực tiếp |
| Xử lý kỹ thuật deletion job | Có với metadata tối thiểu | Theo dõi trạng thái trong phạm vi | Không |

Admin có thể xem metadata requisition tối thiểu phục vụ cấp membership, nhưng không có quyền đọc application/CV/assessment nhờ ngoại lệ này. Admin không được tự nâng quyền xem raw bằng một nút không có dấu vết. Việc cấp role/membership/grant cần audit actor, mục đích, scope và thời hạn. Giữ ít nhất một admin active; không cho tự xóa last-admin. Không suy diễn quyền bằng email domain.

Truy vấn trả 404 cho tài nguyên ngoài phạm vi khi cần tránh lộ existence; backend vẫn ghi reason code phù hợp. Export, original-file download, source span endpoints, job status và audit phải có cùng scope checks như trang hồ sơ.

Manual document decision cũng cần owner + raw grant + file safety passed + source review có audit; không dùng đường manual để mở file bị quarantine. Technical information request chỉ ghi yêu cầu xử lý lỗi, không dùng thiếu grant/parse failure để quyết định loại. Tham chiếu raw và ghi chú HR trong manual decision vẫn là dữ liệu cá nhân: cùng access/deletion policy, không đưa vào telemetry hoặc model payload.

## 4. Upload, parser và trình xem tài liệu

1. Giới hạn 10 MiB/file, 10 trang, 20 file/batch theo 00; streaming upload có byte cap ở cả proxy và app, không đọc vô hạn vào RAM.
2. Allowlist PDF/DOCX; kiểm tra magic/content type thực, không chỉ đuôi. `.doc`, `.docm`, zip tùy ý, PDF có password và file hỏng trả lỗi hỗ trợ rõ. Không sửa đuôi rồi cố parse.
3. DOCX là zip: chặn path traversal, file entry vượt kích thước, zip bomb, external relationship fetch, macro và embedded attachment. HTML trong CV/dataset không đưa thẳng vào DOM.
4. Lưu bằng UUID/object key do server sinh trong thư mục private; filename người dùng chỉ ở metadata restricted, không dùng làm path hoặc model input.
5. Parse trong subprocess có timeout/resource cap; dùng helper container không mạng cho các bước parse/render không cần MPS, mount đúng file input read-only và một thư mục output riêng. Không chạy shell từ filename hoặc nội dung.
6. OCR local CPU; không tự gửi ảnh/raw CV sang vision API khi OCR lỗi. Không fetch URL trong CV. Text extraction phải báo coverage/quality theo trang, không coi trang trắng/OCR mất dấu là ứng viên thiếu kỹ năng.
7. Raw preview chỉ qua backend có quyền, không public static route; kiểm soát CSP, không thực thi script, không link-out tự động. Sanitized viewer ưu tiên text plain, nguồn có page/section/line để truy vết.
8. Temp file tồn tại tối đa đến khi stage kết thúc; crash janitor dọn theo TTL và kiểm tra file không thuộc active lease. Không lưu vào thư mục đồng bộ cloud tự động khi pilot dữ liệu thật.

## 5. Sanitization và phê duyệt payload

### 5.1 Quy tắc đầu vào

Loại/che khỏi bản đánh giá: tên, giới tính/đại từ tiết lộ nếu không cần, ngày sinh/tuổi, quê quán/địa chỉ chi tiết, ảnh, contact, tên/uy tín trường, năm tốt nghiệp nếu không phục vụ tiêu chí đã duyệt, tình trạng hôn nhân, sức khỏe, tôn giáo, dân tộc và thông tin không liên quan. Với JD seed không có tiêu chí năm kinh nghiệm, không cần dùng các mốc học vấn để suy ra tuổi. Bậc học/chuyên ngành cũng không được cộng điểm vì JD seed không chấm bằng cấp.

Tên công ty, khách hàng, trường trong mô tả dự án có thể là proxy hoặc thông tin mật. Thay bằng placeholder trung tính, giữ nhiệm vụ và phạm vi kỹ thuật cần thiết. Không xóa Python/PostgreSQL/FastAPI chỉ vì viết hoa; dictionary phải phân biệt tổ chức với công nghệ. Không xem tên trường là thuộc tính nhạy cảm theo một phân loại pháp lý tự suy đoán; ở đây nó là thuộc tính bị cấm theo yêu cầu dự án.

Sanitizer gồm regex cho contact/date/URL, từ điển/context rules cho tổ chức/thông tin nhân thân, detector bổ sung đã kiểm thử Việt–Anh nếu dùng. Không hứa NER tự động đủ tốt. **HR phải xem và duyệt bản sanitized trước external call trên CV thật**. Với synthetic suite, có thể auto-approve chỉ khi dataset marker được hệ thống seed tạo; người upload không được tự gán `synthetic=true` để vượt kiểm soát.

### 5.2 Vòng đời bản sanitized

- Mỗi sửa tạo sanitized version mới, không in-place rewrite source đã được đánh giá.
- HR được thêm vùng che và sửa lỗi OCR theo raw source; mọi sửa nghĩa cần căn cứ, actor và reason. Không được tự thêm kinh nghiệm chưa có vào CV text.
- Nút duyệt xác nhận chính xác hash/text version sẽ gửi. Job lấy snapshot đã duyệt, không đọc "latest" lúc chạy.
- Sửa sanitized version thu hồi các queued job của bản cũ nếu chưa gửi. Kết quả cũ giữ lịch sử và stale; không ngầm cập nhật final decision.
- Trước gửi, kiểm tra tombstone, version approval, policy provider, budget, max input, forbidden-fields scan và source scope. Chỉ sau đó reserve cost + egress.
- Đầu ra LLM lại được quét thuộc tính bị cấm, schema và source references. Phát hiện thuộc tính bị cấm dẫn đến quarantine result, không chỉ che trên UI rồi cho điểm tiếp tục.

### 5.3 Thu hồi nguồn khi phát hiện thông tin bị cấm

Nếu một sanitized version đã được duyệt bị phát hiện còn PII hoặc thuộc tính bị cấm, owner dùng revoke với reason code rõ. Ngoài ngừng egress và làm kết quả stale, backend phải áp quarantine cho toàn bộ nội dung dẫn xuất từ phiên bản đó: spans/chunks, model request/response, assessment và citations, HR revisions có dùng nguồn, interview drafts và revisions, phần nội dung quyết định hoặc annotation chứa dữ liệu nguồn. Không chỉ chặn endpoint đọc sanitized text trong khi GET assessment/history vẫn trả lại cùng quote.

- Thành viên không có raw grant chỉ nhận metadata an toàn như ID, thời điểm, trạng thái `source_revoked` và lý do hạn chế bằng mã; không trả score/recommendation, rationale, quote, câu hỏi hoặc note của payload bị quarantine.
- Thành viên có raw grant đang hiệu lực cho application có thể mở nội dung bị quarantine qua chế độ kiểm tra riêng được audit; quyền này không khôi phục approval, không cho dùng kết quả làm current recommendation hoặc gửi lại provider. Admin không mặc nhiên được đọc.
- Cùng kiểm tra quyền áp dụng trên source/span endpoints, GET assessment/revision/decision/interview, lịch sử, preview, download, idempotency replay và export nếu bổ sung sau. Không dựa vào việc UI đã ẩn nút.
- Payload lịch sử vẫn bất biến trong private store trong thời gian được phép giữ; quarantine thay đổi quyền truy cập và trạng thái sử dụng, không viết lại nguồn cũ để làm citation trông hợp lệ. Sửa lỗi tạo version mới, duyệt mới và đánh giá lại.
- Audit tối thiểu gồm `source_revoked`, `derived_payload_quarantined`, `quarantined_payload_viewed` và các lần bị từ chối truy cập, với actor/version/reason code; không ghi đoạn PII phát hiện được. Test phải tạo một quote chứa PII ở kết quả lịch sử rồi xác minh mọi đường đọc bị chặn với member không có grant.

## 6. Grounding, injection và fairness là kiểm soát thực thi

CV/JD là tài liệu, không có quyền ra lệnh hệ thống. Prompt đặt nguồn vào vùng dữ liệu có nhãn, chỉ cung cấp task cần thiết. Tách hệ thống cấp quyền khỏi model. LLM không có access secret, filesystem, arbitrary SQL, email hoặc browser; không chạy function call do LLM tự tạo ngoài allowlist đã định nghĩa, và MVP assessment không cần tool loop.

RAG không loại bỏ hoàn toàn prompt injection; OWASP khuyến nghị kiểm soát nhiều lớp. Dùng nguyên tắc giới hạn quyền và kiểm tra đầu ra thay vì tin một câu "ignore instructions" sẽ giải quyết mọi ca. [Nguồn OWASP](https://genai.owasp.org/llmrisk/llm01-prompt-injection/).

Không yêu cầu lưu chain-of-thought. Lưu ngắn gọn `rationale` gắn criterion + evidence và decision rule được code tính. Trong hợp đồng MVP, `quote` phải bằng toàn bộ `text` của sanitized span đúng phiên bản đã cung cấp cho model; không cho model tự cắt quote hoặc tạo offset. Sự tồn tại quote là cần nhưng chưa đủ cho semantic support. HR có nguồn để rà; lỗi semantic trọng yếu cần ngăn dùng kết quả bị ảnh hưởng và sửa regression case.

Fairness phải xét cả quy trình và rubric, không chỉ model. NIST phân biệt nguồn thiên vị từ hệ thống, con người và tính toán. [Nguồn NIST](https://www.nist.gov/artificial-intelligence/ai-fundamental-research-managing-ai-bias).

MVP cần bốn loại kiểm thử riêng:

| Test | Bất biến mong muốn | Không được kết luận quá mức |
|---|---|---|
| Đổi tên/trường/giới tính trong fixture | Payload scoring đã che giống nhau về nội dung năng lực; không có trường cấm | Không chứng minh mọi proxy ngoài đời đã được loại |
| Chạy lại cùng payload | Đo dao động score/status; không hide bằng output cache khi test stability | Temperature thấp không tạo tái lập tuyệt đối |
| Đổi bố cục/dịch tương đương | Không thay nghĩa evidence/score ngoài tolerance đã xác định | Đây là robustness, không trực tiếp là demographic parity |
| Chèn injection | Không thay rubric/score bằng lệnh, không egress/tool trái phép | Test pass là trên bộ tình huống hữu hạn |

Không suy đoán giới tính/dân tộc để làm dashboard fairness. Không fine-tune theo tất cả quyết định HR. Ghi override reason để phân tích, sau đó hiệu chỉnh được kiểm thử và HR duyệt.

## 7. Bảo vệ lưu trữ, bí mật và audit

### 7.1 Lưu trữ

- Real-data local pilot cần xác nhận full-disk encryption đang bật (ví dụ FileVault trên máy Mac) và user OS có password, tự khóa màn hình. DB/data directory ngoài repository, quyền thư mục tối thiểu theo OS; không vô tình đưa vào iCloud/Drive/Git.
- Đây là bảo vệ at-rest ở mức volume; không giả vờ đã có field encryption/KMS. Production cloud tương lai cần encrypted disk/database/object store và quản lý key phù hợp deployment.
- HTTPS đến DeepSeek; không tắt TLS verification. Local loopback HTTP chỉ cho cùng máy; nếu HR truy cập từ máy khác thì phải có TLS và cấu hình LAN/private network đã kiểm tra.
- Lưu trữ raw tách logic khỏi sanitized/assessment. DB credentials runtime không có quyền tạo role/superuser. Migration role chỉ dùng lúc migration. Không bắt buộc SaaS RLS cho single-org MVP; nếu thêm RLS phải kiểm thử bằng đúng runtime role, vì owner/superuser có thể bypass. [PostgreSQL RLS](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).

### 7.2 Secrets

- `.env` thật không commit. `.env.example` chỉ chứa placeholder, không token. Next.js không nhận API key; không có `NEXT_PUBLIC_DEEPSEEK_API_KEY`.
- Dev key ở env/OS credential store theo lựa chọn triển khai; CI không có secret ở pull request không tin cậy. Mask Authorization, cookie, CSRF, DB URL có password và vendor error payload.
- Rotate key/session secret khi lộ; thu hồi old key ở provider do người vận hành thực hiện. Không tự gửi key vào prompt, bug report hoặc eval artifact.
- Model files tải từ revision pin, `trust_remote_code=false` nếu khả thi; không execute code của dataset. Dependency scan và lockfile là bắt buộc trước pilot.

### 7.3 Audit

Audit sự kiện: login/logout/reset, cấp/thu hồi role/grant, raw view/download, upload, sanitized edit/approve, rubric edit/approve, assessment queued/completed/failed, HR revision, final decision, re-open decision, delete requested/completed, provider config/prompt release/rollback, export.

Event fields tối thiểu: random event ID, actor ID, action, timestamp UTC, request ID, target type + opaque ID, version IDs, outcome, reason code; không dump before/after CV, quote, prompt hoặc contact. HR note và bản thay đổi nội dung nằm ở các bảng có quyền/xóa, audit chỉ tham chiếu. API user không update/delete audit; runtime app chỉ INSERT. Đây là append-only ở cấp ứng dụng, không phải chứng nhận chống mọi sửa đổi bởi DB admin. Thử nghiệm grant trong CI phải phản ánh giới hạn này.

Nếu cần nội dung để điều tra lỗi, tạo incident package tối thiểu được kiểm soát, TTL và scope riêng; mặc định dùng synthetic tái hiện. Không bật verbose payload logging để debug trên CV thật.

## 8. Retention và quyền xóa

### 8.1 Cấu hình trước pilot

Quyền dùng DeepSeek đã được user xác nhận. Thời gian giữ cụ thể của trường chưa được cung cấp; implement giao diện/CLI ghi chính sách đang áp dụng, người chịu trách nhiệm và ngày hiệu lực, không tự đặt "180 ngày" rồi coi là quy định pháp lý. Sandbox synthetic có TTL mặc định 30 ngày. Đề xuất kỹ thuật: raw temp xóa trong 24 giờ, local deletion active stores trong 24 giờ, rolling backup tối đa 7 ngày; owner dữ liệu xác nhận phù hợp chính sách thực tế trước real pilot.

Ghi rõ các lớp: hồ sơ đang tuyển, hồ sơ đã đóng, audit HR, audit kỹ thuật, export, backup và dữ liệu provider. Không dùng một TTL chung vì mục đích khác nhau. Xóa ứng viên ảnh hưởng tất cả applications; xóa một application không được làm mất application khác nếu còn quyền lưu. MVP không tự merge candidates nên request toàn ứng viên cần HR xác định scope chính xác.

### 8.2 Trình tự xóa bắt buộc

1. Xác thực người yêu cầu và scope; tạo `deletion_request` với idempotency key. Đánh dấu tombstone/increment generation trong cùng transaction và hủy queued jobs.
2. Ngay khi tombstone có hiệu lực, mọi read/public API/export ngừng trả payload. Worker kiểm tra generation trước từng stage, trước external call và trước commit.
3. Dọn raw object, parsed/sanitized text, source spans, embeddings, assessments, HR notes/revisions, question drafts, application-specific eval labels, caches, temp/rendered file và file export do hệ thống quản lý.
4. Worker đang chạy có thể vẫn nhận response từ API sau cancellation. Response bị bỏ, không lưu lại; các chi phí thực tế đã phát sinh vẫn vào ledger tối thiểu không chứa payload. Không hứa hủy được request đã đến vendor.
5. Retain sự kiện xóa tối thiểu không chứa nội dung ứng viên; đối với audit liên quan, xóa/detach reference nhận diện theo retention policy. Hash file/ID giả danh cũng có khả năng liên kết, không gọi là vô danh chỉ vì đã hash.
6. Kiểm tra inventory và chạy deletion verification; retry cleanup idempotent đến khi hoàn tất. Nếu một kho local lỗi, dùng enum `failed` thống nhất với03, ghi phần đã xóa/phần còn lỗi và `retryable` trong verification report; user access vẫn bị chặn. Retry dùng cùng deletion request và inventory, không tạo lại quyền đọc hoặc một hồ sơ mới. Không dùng enum `partial_failure` riêng.
7. Backup cũ được cách ly, không dùng cho vận hành, hết hạn theo retention; restore bắt buộc áp deletion ledger trước mở truy cập. Không báo đã xóa khỏi mọi backup ngay nếu thực tế chỉ có expiry.
8. Provider retention/deletion phải được ghi nhận theo dịch vụ API đang dùng; ứng dụng không có quyền tự bảo đảm vendor đã xóa log. Báo riêng `local_purge_complete`, `local_purge_completed_at`, `backup_status`, `backup_expiry_at`, `external_retention_status`; nếu có yêu cầu xóa ngoài provider thì theo dõi confirmation riêng.

`local_purge_complete=true` chỉ sau kiểm chứng mọi active store và job đã quiescent; không chờ vendor mới báo tiến độ local. `backup_status` có `pending_expiry|expired|not_applicable`; `external_retention_status` có `unknown|policy_retention_pending|deletion_requested|confirmed_deleted|not_applicable`. Khi local đã sạch nhưng còn phần backup/provider chưa hoàn tất theo policy, deletion request giữ `awaiting_external` và nêu rõ phần đang chờ. Chỉ chuyển `completed` khi các phần thuộc scope đã được kiểm chứng hoàn tất; không coi timeout hay thiếu phản hồi vendor là bằng chứng đã xóa. Unknown retention không phải lỗi cleanup local: không đổi `local_purge_complete` thành false chỉ để gộp mọi trạng thái vào một đèn báo.

Đừng để dòng chữ "Delete success" che khác biệt giữa khóa truy cập ngay, dọn active storage và hết hạn backup/provider. Test race phải cố tình cho LLM/mock trả kết quả sau tombstone để xác minh không tái sinh dữ liệu.

## 9. Bộ nghiệm thu bảo mật tối thiểu

| ID | Tình huống | Kết quả bắt buộc |
|---|---|---|
| SEC-01 | Không login gọi list/source/original/export | 401, không payload |
| SEC-02 | Reviewer A đoán ID hồ sơ thuộc B | 404/deny, không source/span metadata rò rỉ |
| SEC-03 | Admin không raw grant tải original | Deny; admin role không bypass |
| SEC-04 | POST quyết định từ reviewer hoặc LLM-origin input | Deny; final decision không được tạo |
| SEC-05 | Cookie mutation thiếu/sai CSRF hoặc Origin | Deny |
| SEC-06 | Fake PDF, zip bomb, path traversal, docm, oversized input | Bị từ chối trước parse unsafe; không chạy file |
| SEC-07 | Raw CV chứa tên/trường/contact ở filename/header/footer | Không xuất hiện trong captured outbound payload sau HR duyệt |
| SEC-08 | CV có lệnh tiết lộ secret hoặc cho điểm | Không tool/egress mới; kết quả chỉ theo rubric/evidence |
| SEC-09 | Quote/ID nguồn của application khác hoặc version cũ | Validation fail, không publish assessment |
| SEC-10 | Xóa khi worker đang gọi provider | Không ghi response sau tombstone; cleanup kiểm chứng |
| SEC-11 | Restore backup chứa candidate đã xóa | Áp deletion ledger trước khi service sẵn sàng |
| SEC-12 | Quét Git, logs, browser bundle, CI artifact | Không secret/CV thật/PII payload |
| SEC-13 | Sửa sanitized sau approval | Phiên bản mới cần duyệt; run/result cũ không silently cập nhật |
| SEC-14 | Dùng output model để chèn HTML/script | Render escaped plain text; không script execution |
| SEC-15 | Sandbox account/token cố truy cập pilot storage/API | Deny; deployment và credential riêng |

Chỉ ghi PASS sau khi chạy trên bản build, kèm ngày/commit/report. Thiết kế có các mục này chưa đồng nghĩa các kiểm soát đã hoạt động.
