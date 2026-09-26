# 09 — Kế hoạch triển khai theo dependency và tiêu chí nghiệm thu

## 1. Cách dùng backlog

Đây là task contract cho một AI implement cùng một người phát triển. Không yêu cầu user tự chọn thư viện hoặc viết đặc tả còn thiếu. Trước mỗi task đọc tài liệu liên quan, kiểm tra trạng thái repo và ghi lại lựa chọn khác với plan thành decision record có lý do. Không đánh dấu hoàn tất chỉ vì tạo file hoặc mock UI.

Ưu tiên P0 = cần trước assisted pilot thật; P1 = bổ sung sau vertical slice nhưng trước khi công bố hỗ trợ tính năng đó; P2 = ngoài MVP. Thứ tự theo dependency, không theo sự hấp dẫn của tính năng. Có thể làm UI dùng mock song song với backend nhưng phải nối thật trước nghiệm thu task.

Thời gian là ước lượng **giờ kỹ thuật tập trung**, không tính thời gian chờ HR, quyền truy cập hoặc vendor outage. Một người dành khoảng 30–40 giờ/tuần có 120–160 giờ trong bốn tuần và 240–320 giờ trong tám tuần. Bốn tuần là mục tiêu bản nội bộ; sáu–tám tuần là mục tiêu pilot hẹp sau các gate. Không hứa production-ready theo ngày lịch nếu chưa đạt kiểm thử.

## 2. Milestones

| Mốc | Thời gian mục tiêu | Kết quả nhìn thấy | Điều kiện chuyển mốc |
|---|---|---|---|
| M0 — nền và nghiệp vụ | Tuần 1 | Local doctor, login, JD/rubric seed draft, source fixtures, HR review rubric | Account/scope test pass; JD được HR/IT góp ý, không còn tiêu chí bị cấm |
| M1 — intake và nguồn | Tuần 2 | Upload PDF, parse, sanitized review/approve, source viewer; queue bền vững | Không mất nguồn, không egress raw, worker recovery pass |
| M2 — đánh giá hoàn chỉnh | Tuần 3–4 | Provider adapter+mock, fulltext baseline, scoring code, HR review/decision, audit, manual path | E2E synthetic chạy thật qua toàn pipeline; role/score/source invariants pass |
| M3 — hardening và evaluation | Tuần 5–6 | OCR/DOCX verified, hybrid benchmark, prompt regression, deletion, backup, onboarding, independent labels | Gate chất lượng/bảo mật/chi phí có báo cáo; chưa có dữ liệu thì chưa claim HR agreement |
| M4 — shadow và assisted pilot | Tuần 7–8 | Một batch nhỏ CV thật chạy shadow; HR ký nghiệm thu thực tế; sau đó mới bật trợ lý cho batch hẹp | Tất cả gate P0 và incident rollback drill; nhận biết failure còn lại |

Nếu không đủ thời gian, cắt DOCX/hybrid rollout/dashboard nâng cao trước, vẫn giữ PDF, nguồn, privacy, HITL, deletion và test. Nếu tạm không hỗ trợ DOCX, API/UI phải nói rõ định dạng đó chưa hỗ trợ, không nhận file rồi xử lý giả. Hybrid có thể được implement/test nhưng để feature flag off nếu không cải thiện baseline.

## 3. Danh sách task cấp triển khai

### B00 — Khởi tạo monorepo, doctor và cấu hình [P0, 3–5h]

- **Depends:** đọc 00–05 và 07; không dependency code.
- **Tạo:** tree theo02, Python/Node lockfiles, `.gitignore`, `.env.example`, Make targets, config typed, README chạy local.
- **Làm:** kiểm tra macOS/arm64, Docker/DB, MPS availability, OCR/model cache; default provider mock; validate config theo môi trường.
- **AC:** `make doctor` không lộ secret, chỉ rõ prerequisite còn thiếu; `.env` và data private không track Git; repo có một đường chạy được từ máy sạch theo hướng dẫn.
- **Test:** config thiếu key trong mock vẫn chạy; real provider thiếu rate/model/probe bị báo rõ; startup không tự gọi API trả phí.

### B01 — Data model, migration và domain enums [P0, 4–8h]

- **Depends:** B00; **Spec:** 03.
- **Tạo:** migrations cho core entities, FK/unique/index, domain enums, migration smoke.
- **Làm:** candidate/application/document versions tách biệt; role+membership; rubric/source/run snapshots; row_version và generation; PostgreSQL thật trong integration tests.
- **AC:** migrate empty DB và upgrade từ snapshot thử đều pass; invalid FK/cross-application link bị chặn ở service/DB appropriate; không SQLite-only test cho queue/pgvector.
- **Test:** duplicate application/run/idempotency keys, delete dependencies, approved version immutability.

### B02 — Authentication, session, CSRF và authorization [P0, 6–10h]

- **Depends:** B01; **Spec:** 03,05.
- **Tạo:** login/logout/me, admin account bootstrap CLI, role/membership guards, raw grants.
- **AC:** session cookie đúng môi trường, logout/reset thu hồi session, reviewer không finalize decision, admin không có raw grant không đọc raw CV, cross-requisition ID denied.
- **Test:** SEC-01..05, last-admin guard, expired session, direct endpoint bypass UI, origin/CSRF failure.

### B03 — Requisition và JD version [P0, 4–6h]

- **Depends:** B02; **Spec:** 01,03 và JD example.
- **Tạo:** list/detail/create requisition, memberships, JD editor/version history, archived/active state.
- **AC:** owner mới đổi JD; title+description validation; publish/change version có audit; JD draft không tự làm các run dùng approved rubric cũ thay đổi.
- **Test:** concurrent edits trả409/precondition failure, old source references vẫn truy vết được.

### B04 — Rubric seed, editor, approval và policy [P0, 6–10h]

- **Depends:** B03; **Spec:** 00,01,03,examples/rubric.
- **Tạo:** import seed draft, criterion editor có6IDs, weights/anchors/source refs, approve endpoint, immutable version.
- **AC:** weights=100, đúng IDs, đủ anchors0..4, thresholds70/floor 2 hiện để HR duyệt; forbidden criteria cảnh báo/chặn publish; AI draft chưa được coi approved.
- **Test:** missing/duplicate criterion, noninteger weight/score, stale edit, reviewer approve denied. Dùng seed không cần provider; Rubric Agent được nối ở B14 theo task scope.

### B05 — Intake upload và private storage [P0, 6–10h]

- **Depends:** B02,B03; **Spec:** 02,03,05.
- **Tạo:** application+document upload, limits, safe blob paths, quarantine/status, idempotency.
- **AC:** PDF/DOCX route capability rõ; MIME/magic/size checks; no public storage URL; cùng idempotency key/body không tạo hai đơn; file lỗi có lý do và manual route.
- **Test:** path traversal, fake extension, oversized/empty file, cross-scope download, batch partial failures không rollback file hợp lệ không liên quan.

### B06 — Parse PDF, normalization và provenance [P0, 8–12h]

- **Depends:** B05; **Spec:** 02–05.
- **Tạo:** parser helper, canonical NFC/LF text, page metadata, source span registry, text quality diagnostics.
- **AC:** nguồn text đúng trang; codepoint offsets tái dựng đúng quote tiếng Việt/emoji; không silent truncate; quote viewer không cần LLM tạo offset.
- **Test:** one/two-column fixture, missing page, unicode, encrypted PDF, source hash mismatch, deterministic parsing fixture.

### B07 — Durable PostgreSQL worker [P0, 8–12h]

- **Depends:** B01,B05; có thể cùng lúc phát triển B06 qua handler mock.
- **Tạo:** claim/heartbeat/lease/fencing, retry schedule, cancellation, recovery sweeper, job API.
- **AC:** restart không mất queued job; worker cũ không commit sau lease mới; không transaction mở qua network call; provider_outcome_unknown không auto-resend mù.
- **Test:** hai workers tranh job, kill giữa stage, stale heartbeat, timeout, samejob duplicate, tombstone race scaffold.

### B08 — Sanitization, HR approval và source viewer [P0, 10–16h]

- **Depends:** B06,B07; **Spec:** 01,03,05.
- **Tạo:** detector rules Việt–Anh, raw-to-sanitized mapping, immutable edits, side-by-side reviewer UI có quyền, approve hash.
- **AC:** CV thật không embed/egress trước owner+rawgrant review; edit sau approve tạo version mới; filename/header/footer/metadata không lộ trong payload; missing raw grant có đường xin phân công người có quyền.
- **Test:** school/name/contact counterfactual invariance, synonym tech vs organization, sanitized/source mismatch, revoke approval khi sửa.

### B09 — DeepSeek adapter, capabilities và cost ledger [P0, 6–10h]

- **Depends:** B07,B08; **Spec:** 04,07.
- **Tạo:** Provider interface, mock có fault injection, adapter dùng httpx, capability probe bằng dữ liệu synthetic, parser JSON và cơ chế reserve/settle chi phí.
- **AC:** Giữ `deepseek-chat` trong cấu hình; không tự fallback model. Ánh xạ đúng token/usage. Phân loại được response rỗng, bị cắt, refusal, model không hỗ trợ và network timeout. Tối đa hai attempt mỗi stage và bốn external call mỗi run; billing chưa rõ không được coi là miễn phí.
- **Test:** Race khi giữ ngân sách; che secret; nhánh 401/402/429/5xx; không có retry trùng trong SDK; kiểm tra approval trước khi gửi dữ liệu thật.

### B10 — Full-text assessment baseline và output validation [P0, 8–12h]

- **Depends:** B04,B08,B09; **Spec:** 04 và contracts.
- **Tạo:** Manifest bất biến cho run, context builder, assessment prompt, validator có kiểu dữ liệu, repair có giới hạn và lưu kết quả AI bất biến.
- **AC:** Đúng sáu criterion, mỗi ID xuất hiện một lần; giữ các invariant về score/status/evidence. Chỉ chấp nhận nguồn trong span registry được phép. Nêu rõ giới hạn kiểm tra ngữ nghĩa; input vượt budget không bị cắt âm thầm.
- **Test:** Span thuộc hồ sơ khác, quote bị sửa, thiếu criterion, score ngoài miền; `insufficient_evidence` bắt buộc score null; từ chối output khi model tự thêm trường quyết định tuyển dụng.

### B11 — Deterministic scoring/recommendation engine [P0, 4–6h]

- **Depends:** B04; song song B10 vì pure functions; **Spec:** 00,04.
- **Tạo:** Các hàm tính observed score, coverage, comparable score; threshold policy; quy tắc sort/tie và reason codes.
- **AC:** Hồ sơ incomplete không có comparable score và không được xếp hạng chung. Ngưỡng 70 và core floor 2 lấy từ rubric đã duyệt. AI không sinh tổng điểm hoặc quyết định tuyển dụng; trạng thái kết quả còn hiệu lực được lưu riêng với điểm.
- **Test:** Không criterion nào assessed; coverage một phần; tất cả sáu criterion đạt 3 thì điểm 75; tổng điểm cao nhưng core=1 dẫn đến `review_required`; điểm 69,99 không được làm tròn trước khi so ngưỡng; conflict dẫn đến `needs_clarification`.

### B12 — Review workspace và danh sách ứng viên [P0, 10–14h]

- **Depends:** B10,B11; UI skeleton có thể trước đó.
- **Tạo:** Routes, bảng, filters và trang chi tiết theo tài liệu 01; status chips, ma trận criterion, source panel, job polling và các trạng thái stale/error/empty.
- **AC:** Danh sách mặc định theo thời gian nhận; không dùng điểm tổng lớn ở đầu trang để dẫn dắt HR. Bấm quote mở đúng nguồn sanitized. Nhãn cho điểm incomplete rõ ràng. UI không tự tính policy; keyboard, focus và trạng thái loading sử dụng được.
- **Test:** Playwright chạy từ upload đến assessment; các trạng thái401/403/404/error/timeout; mở URL trực tiếp theo role; nút retry có idempotency; polling không tạo job.

### B13 — HR revision, attestation, final decision và audit [P0, 6–10h]

- **Depends:** B12,B02; **Spec:** 01,03,05.
- **Tạo:** Override có lý do và nguồn; HR revision bất biến khi finalized; attestation và decision theo ba basis `assessment_review`, `manual_document_review`, `technical_information_request` trong03; history và audit metadata.
- **AC:** Override không ghi đè kết quả AI. Quyết định có nguồn/snapshot rõ ràng. Approval stale không được âm thầm dùng để finalize. Khi thông tin nghiệp vụ còn thiếu, HR vẫn có quyền quyết định thủ công với lý do; không ép AI tạo đủ điểm để quyết định.
- **Test:** Reviewer không final hiring decision được (vẫn finalize HR revision của mình); xung đột hai quyết định đồng thời; stale source; OCR lỗi vẫn raw manual được khi đúng grant/safety; technical basis chỉ request_information; response đến sau cancel không publish; audit raw không lộ nội dung. Nếu có export quyết định sau MVP thì chỉ xuất nội dung được phép.

### B14 — Rubric Agent và Interview Agent [P0, 6–10h]

- **Depends:** B09,B10,B13; **Spec:** 04.
- **Tạo:** Tác vụ rubric draft có nguồn JD; import seed `examples/interview-question-bank.v1.json` ở trạng thái draft; bank editor/approval/version ở cấp rubric; sinh follow-ups theo yêu cầu; schema validation; persist AI draft và HR revision của follow-ups theo03.
- **AC:** Rubric/bank draft không tự publish. Câu core và hướng dẫn chấm được lấy nguyên văn, đúng thứ tự từ approved bank snapshot; model chỉ tạo follow-ups. Cùng rubric/bank version có cùng core questions. Owner thay bank ở cấp rubric bằng phiên bản mới; trang candidate chỉ cho owner/reviewer sửa follow-ups, lưu HR revision riêng và reload không mất. Follow-ups gắn criterion/source hoặc gap cần làm rõ. Không hỏi thuộc tính bị cấm hoặc gửi email/lời mời; nguồn/rubric/bank đổi làm bộ câu hỏi stale theo03.
- **Test:** Core bank bất biến qua nhiều candidate và nhiều lần gọi; payload cố sửa core ở candidate bị từ chối; reviewer không approve bank; follow-up save/reload/concurrent edit; tham chiếu source/criterion/gap; output sai schema; không gửi dữ liệu ngoài snapshot; cap chi phí của run; không hiện AI questions làm nhiễu nhãn HR trong shadow.

### B15 — Local OCR và DOCX rendering [P1, 6–12h]

- **Depends:** B06,B07; **Spec:** 02,05,07.
- **Tạo:** OCR `vie+eng`, render DOCX sang PDF để đếm trang, kiểm tra chất lượng parse và các nhánh lỗi kỹ thuật.
- **AC:** Render không làm mất nguồn/provenance; giới hạn số trang DOCX được kiểm tra thực tế. Parse/OCR thất bại không biến thành `insufficient_evidence` về năng lực. Nếu thiếu capability, API công bố rõ định dạng chưa hỗ trợ.
- **Test:** Ngưỡng ảnh mờ/nghiêng; PDF có cả text và scan; DOCX chứa bảng/hai cột; không có renderer; timeout/OOM và dọn file tạm.

### B16 — Local multilingual embeddings và hybrid retrieval [P1, 6–10h]

- **Depends:** B08,B10; **Spec:** 04.
- **Tạo:** E5-base ghim revision trên CPU/MPS; chunks theo tokenizer; truy vấn pgvector exact có scope; nhánh lexical kết hợp RRF; giữ provenance và fallback full-text.
- **AC:** Áp bộ lọc nguồn trước xếp hạng; không đọc chéo CV. Từ khóa kỹ năng không tự thành điểm. So với baseline trên cùng input trước khi bật hybrid. Khi fallback vượt budget, chuyển thủ công với lý do rõ.
- **Test:** Tiếng Việt/Anh/mixed; công nghệ hiếm; thành tích song ngữ trùng nhau; embedding sai version; top-k không đủ nguồn; recall trên gold spans.

### B17 — Deletion, retention và data inventory [P0, 8–12h]

- **Depends:** B07,B08,B13; **Spec:** 03,05.
- **Tạo:** Yêu cầu xóa có scope, tombstone/generation, hủy job, đối soát cleanup, trạng thái external/backup và retention sweep.
- **AC:** Thu hồi truy cập ngay; cleanup idempotent cho sources/vectors/cache/notes; xóa đúng phạm vi application. Response LLM đến sau yêu cầu xóa không làm dữ liệu xuất hiện trở lại.
- **Test:** SEC10/11; purge thất bại một phần và retry; candidate có nhiều application; yêu cầu sai scope; dọn export hết hạn và file tạm.

### B18 — Dataset bootstrap và fixture factory [P0, 4–8h]

- **Depends:** B00,B04; nên làm dần từ tuần 1; **Spec:** 08.
- **Tạo:** Inspect/import source registry; dữ kiện synthetic chuẩn; layouts cho parser; chia tập theo family; artifacts về attribution/license.
- **AC:** Không import nguồn chưa xác định. Bắt đầu 12 family rồi mở rộng 60 dev/30 holdout, smoke là tập con 10 family. Không commit PII thật, không để một family xuất hiện ở nhiều split. Nhãn heuristic từ source không được coi là nhãn HR.
- **Test:** DATA01..10; schema sai, thiếu SHA, PII bị quarantine; seed tạo dữ liệu có thể tái lập.

### B19 — Evaluation harness, metrics và HR annotation [P0, 8–12h]

- **Depends:** B10,B11,B18; **Spec:** 06.
- **Tạo:** CLI export/import JSON annotation + private metadata/store theo03§15; nhãn độc lập khi chưa xem AI; freeze theo round; báo cáo so sánh, phân nhóm theo ngôn ngữ/độ khó và tổng hợp chi phí. Không làm portal annotation riêng trong MVP.
- **AC:** HR không thấy AI trước khi ghi baseline. Lưu nguồn gốc nhãn. Mẫu số chính xác, tính cả unknown và lỗi kỹ thuật. MAE/kappa chỉ tính trên cặp nhãn hợp lệ có thể so sánh; coverage được báo riêng.
- **Test:** Fixture có metric biết trước; kappa là N/A ở ca không đủ dữ liệu/một lớp; không loại lỗi khỏi báo cáo; kiểm tra splits/audit. Không yêu cầu mọi test gọi external API.

### B20 — Prompt regression và release/rollback [P0, 4–8h]

- **Depends:** B19; **Spec:** 04,06.
- **Tạo:** Prompts/schema/release manifest trong Git; runner so sánh prompt; CI offline dùng mock; paid dev smoke chỉ khi chủ động bật; script/config rollback.
- **AC:** Regression đã biết về schema, PII, source hoặc injection chặn release. Thay prompt có báo cáo baseline về chi phí và chất lượng. Rollback theo bundle tương thích; không ghi đè kết quả quá khứ.
- **Test:** Ma trận contract; assertions xác định; chạy lặp không dùng cache output; cảnh báo model drift; diễn tập rollback thực.

### B21 — Sandbox onboarding và help UI [P0, 4–6h]

- **Depends:** B12,B13,B18; **Spec:** 01.
- **Tạo:** Walkthrough và tooltips, lưu tiến độ onboarding, ranh giới demo và năm tình huống huấn luyện.
- **AC:** HR thực hành mở nguồn, nhận ra thiếu thông tin, sửa AI, quyết định và xem audit. Sandbox tách storage với pilot; không gửi email.
- **Test:** Checklist UAT với HR mới dùng; hoàn tất onboarding không tự cấp quyền dữ liệu thật; điều hướng bằng keyboard.

### B22 — Security regression và privacy review kỹ thuật [P0, 6–10h]

- **Depends:** B02,B08,B13,B17; **Spec:** 05.
- **Tạo:** Integration tests cho SEC01..15; assertions trên outbound capture; scanner secret/log; danh mục license dependency.
- **AC:** Security gate PASS trên build thực. Còn issue P0 thì chưa mở assisted pilot. Quyền dùng DeepSeek đã được ghi nhận, không hỏi lại user về quyền đã xác nhận.
- **Test:** Vượt role qua HTTP trực tiếp; file độc hại/injection; race khi xóa; thoát phạm vi nguồn; khôi phục backup và áp deletion ledger.

### B23 — Observability, load và budget operations [P0, 4–8h]

- **Depends:** B07,B09,B19; **Spec:** 07.
- **Tạo:** Số liệu tổng hợp cho admin; health/readiness/worker heartbeat; load fixtures P1/P2; báo cáo SLI và reason codes cho cảnh báo.
- **AC:** Đếm mọi job đã được nhận. Mốc đo latency không bỏ qua thời gian chờ queue; thời gian chờ con người được đo riêng. Rate card chưa rõ phải chặn paid batch; log không có PII.
- **Test:** Budget chạm cap; provider outage nhưng UI xử lý thủ công vẫn dùng được; timing embedding cold/warm; báo cáo burst 3/burst 20; không tuyên bố đạt SLO khi chưa đo.

### B24 — Packaging, backup và restore [P0, 6–10h]

- **Depends:** B17,B22; **Spec:** 02,07.
- **Tạo:** Docker CPU profile; production build; runbook migration; backup mã hóa và diễn tập restore cô lập.
- **AC:** Synthetic E2E trên CPU profile pass. Service chạy non-root, DB riêng tư. Restore DB+blob nhất quán và đã áp deletion ledger. Dữ liệu thật không nằm trong Git hoặc thư mục đồng bộ cá nhân.
- **Test:** Startup thiếu secret; migration lỗi và rollback/forward fix; frontend bundle không rò dữ liệu; môi trường restore tắt outbound.

### B25 — HR calibration, shadow và pilot gate [P0, 6–12h kỹ thuật + HR thời gian riêng]

- **Depends:** B19–B24, B15/B16 nếu chức năng đó được bật.
- **Làm:** Tổ chức các buổi ở mục 5; thu nhãn độc lập; review lỗi; đóng băng holdout; chạy shadow trên một batch nhỏ dữ liệu thật; xác nhận từng gate bằng báo cáo.
- **AC:** Dữ liệu thật được xử lý theo policy đã duyệt và đúng vai trò HR/IT. Không kết luận fairness chỉ từ synthetic. Lỗi đã biết có ảnh hưởng đáng kể phải có phương án xử lý; HR quyết định mọi hồ sơ.
- **Test:** UAT luồng trợ lý; override, clarification, source và history đúng. Pilot pass không cho phép bật quyết định tự động.

### B26 — Sửa lỗi còn lại và bàn giao vận hành [P0, 8–16h]

- **Depends:** B25; ưu tiên lỗi có tác động đến quyết định/privacy rồi UX.
- **Tạo:** Release report; giới hạn thực tế; phiên bản model/rate card đang vận hành; support runbook; chỉ mục bằng chứng nghiệm thu; demo script; known issues và backlog tương lai.
- **AC:** Setup từ checkout sạch đã được kiểm tra; tài liệu khớp code; owner biết dừng, rollback, xóa và backup. Không có test TODO được ghi PASS. Bàn giao source/bản build và hướng dẫn chạy, không chỉ screenshots.
- **Test:** Clean-install smoke, demo synthetic và các regression liên quan lỗi vừa sửa; đối chiếu manifest/build/reports; xác nhận các gate chưa chạy vẫn là not_run. Không chạy lại paid benchmark khi không có thay đổi hoặc lý do mới.

## 4. Thứ tự đường găng

```text
B00 -> B01 -> B02 -> B03 -> B04
                \-> B05 -> B06 -> B08 ----\
                        \-> B07 ----------> B09 -> B10 -> B12 -> B13
B04 -> B11 ---------------------------------------> B12
B04 -> B18 -> B19 <- B10/B11
B13 -> B14/B21
B07/B08/B13 -> B17 -> B22 -> B24
B19 -> B20/B23
All required gates -> B25 -> B26
```

B15 OCR/DOCX và B16 hybrid có thể làm khi baseline đã có; không chặn xây HR workspace bằng fixture có text. Tuy nhiên OCR/DOCX chưa đạt thì không công bố hỗ trợ loại đó; không đưa CV không đọc được vào scoring giả.

## 5. Kế hoạch cộng tác HR/IT

Người dùng xác nhận có thể mời HR và người chuyên môn IT; chưa có lịch cụ thể. Đặt lịch sớm, không đợi tuần cuối.

| Buổi | Mục tiêu | Thời lượng đề xuất | Đầu ra |
|---|---|---|---|
| H1 — Tuần 1 | Duyệt JD/rubric draft trên 6 fixtures | 60–90 phút cùng HR+IT | Rubric đã sửa; định nghĩa đủ bằng chứng; lý do chọn ngưỡng |
| H2 — Tuần 3 | Chấm độc lập tập calibration gồm 12–20 family; hai người chấm một tập con nếu khả thi | 2–3 giờ mỗi người, chia thành các phiên | Nhãn được ghi trước khi xem AI; điểm bất đồng; kết quả phân xử |
| H3 — Tuần 5/6 | Frozen holdout khoảng 30 family và CV thật được phép sử dụng khi có | 2–4 giờ, tùy độ dài CV | Báo cáo evaluation phân biệt synthetic/real |
| H4 — Tuần 7 | Walkthrough, tình huống lỗi và shadow batch thật | 60–90 phút + thời gian xét hồ sơ | Kết quả UAT, issues và quyết định readiness của HR |
| H5 — Tuần 8 | Review pilot và bàn giao runbook | 45–60 phút | Phạm vi release và người chịu trách nhiệm |

Đây là nhu cầu thời gian đề xuất, chưa phải lịch được user cam kết. Nếu chỉ có một người chấm, báo rõ reference từ một rater; không tạo số liệu HR–HR. Nếu chưa có CV thật, H3/H4 chưa chứng minh hiệu quả trên dữ liệu thực và assisted pilot chưa được bật.

## 6. Gate trước dữ liệu thật và assisted pilot

Gates áp theo giai đoạn, không yêu cầu đã có kết quả real-shadow mới cho bắt đầu real-shadow. Bảng dưới ánh xạ nhóm G1–G7 sang các gate chi tiết trong06; bản build phải lưu trạng thái riêng cho từng giai đoạn.

| Giai đoạn được mở | Điều kiện trước khi mở | Phần có thể còn pending |
|---|---|---|
| Local/sandbox synthetic | Tách dữ liệu/môi trường; contract tests phù hợp tính năng đang chạy; mock mặc định. Gọi API synthetic thật cần provider probe/rate card/budget | Nhãn HR và real-shadow; không được công bố readiness tuyển dụng thật |
| Real-data shadow | G1–G4; G-SYNTH-EVAL trong06; G6 cho phạm vi shadow gồm cap/load, người vận hành, rollback/restore/delete đã diễn tập; HR được hướng dẫn privacy, sanitized approval và gán nhãn độc lập | Kết quả chất lượng trên dữ liệu thật và UAT assisted. HR chưa xem AI khi chấm/quyết định; stage này tạo báo cáo real-shadow |
| Assisted pilot hẹp | Tất cả G1–G7, gồm G-SYNTH-EVAL + G-REAL-SHADOW/G-AI-QUALITY theo06, lỗi blocker đã đóng và UAT assisted đạt; HR/IT ký phạm vi sử dụng | Chỉ các giới hạn đã được ghi và không vi phạm gate; không biến metric undefined/insufficient_data thành pass |

Trong shadow, khóa output AI đối với người gán nhãn/quyết định đến khi phần đánh giá độc lập đã đóng băng; đầu mối evaluation chỉ mở báo cáo khác biệt sau đó. Không chỉ che điểm tổng trên UI trong khi API vẫn trả toàn bộ AI output. Dữ liệu thật vẫn phải qua tất cả kiểm soát privacy, quyền truy cập, sanitized approval và budget; shadow không phải ngoại lệ bảo mật.

| Gate | Bằng chứng cần có | Không được thay bằng |
|---|---|---|
| G1 — Quyền và cấu hình | Quyền dùng DeepSeek đã xác nhận; policy/retention/vendor config được ghi; key, rate card và capability probe hợp lệ | Chỉ có API key hoặc chỉ đọc tài liệu marketing |
| G2 — Nghiệp vụ | HR owner và IT duyệt phiên bản JD/rubric/ngưỡng | Seed JSON draft do AI tự soạn |
| G3 — Dữ liệu | Dữ liệu ứng viên được trường cho phép dùng; storage đúng phạm vi; sanitized approval; provenance của dataset | CV scrape công khai nhưng không rõ nguồn |
| G4 — Kỹ thuật | Tests về SEC, source, schema, scoring, state và race đều pass; không còn lỗi blocker P0 trong phạm vi chạy. Đây là gate lỗi kỹ thuật, không buộc task thu nhãn real-shadow đã hoàn thành trước khi bắt đầu shadow | Mock UI hoặc chỉ unit test với SQLite |
| G5 — Chất lượng | Benchmark synthetic và real-shadow riêng; nhãn độc lập, báo cáo holdout/real-data và error audit; tỷ lệ thiếu thông tin/lỗi kỹ thuật; các metric bắt buộc đủ dữ liệu theo06. Phần real-shadow là điều kiện chuyển sang assisted, không phải điều kiện bắt đầu shadow | LLM judge tự chấm, nhãn heuristic từ nguồn hoặc báo cáo synthetic được gọi là kết quả thực |
| G6 — Vận hành | Báo cáo budget/load; diễn tập rollback, restore và delete; có người vận hành được phân công | Các con số SLO được viết trong plan |
| G7 — Người dùng | HR hoàn thành walkthrough, hiểu điểm/coverage/override và có UAT assisted; trước shadow phải hoàn thành phần đào tạo privacy, kiểm tra nguồn và gán nhãn độc lập | Chỉ tick đã đọc tài liệu |

Gate fail không buộc bỏ toàn bộ dự án: giữ phạm vi local/synthetic/manual, ghi rõ phần chưa đạt và kế hoạch khắc phục. Không tự hạ gate hoặc xóa test fail để kịp deadline.

## 7. Cách AI implement báo tiến độ và bàn giao từng task

Với mỗi Bxx, lưu một note trong `implementation-progress.md`: trạng thái, commit/file thay đổi, quyết định, lệnh test và kết quả, giới hạn đã biết và bước tiếp theo. Báo `blocked_external` khi thiếu HR/data/provider thay vì bịa kết quả. Không ghi completed cho test chưa chạy. Mỗi milestone có một demo scenario tái lập bằng synthetic fixtures và checklist đủ để người khác kiểm tra.

Chỉ tạo service/module mới khi có task cần. Không xây lại design system lớn, cloud infrastructure, local LLM thay DeepSeek hoặc pipeline retraining ngoài phạm vi. Không thay đổi invariant về scoring/privacy/HITL để sửa một test case; phải sửa nguyên nhân hoặc xin chốt thay đổi nghiệp vụ thực sự.
