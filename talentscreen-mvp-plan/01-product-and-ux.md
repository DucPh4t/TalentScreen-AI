# TalentScreen AI — đặc tả sản phẩm, workflow và UX MVP

Nguồn quyết định: [00-scope-decisions.md](00-scope-decisions.md). Đây là đặc tả để triển khai, không phải tuyên bố phần mềm đã đạt điều kiện pilot. Hợp đồng API, enum kỹ thuật và concurrency theo [03-data-api-state-machines.md](03-data-api-state-machines.md); nếu tên hiển thị trong tài liệu này khác enum, giữ mapping ở frontend, không tạo thêm state backend tùy ý.

## 1. Kết quả phải bàn giao và phạm vi

Một HR có thể tạo đợt tuyển Backend Python, duyệt JD/rubric, upload CV, kiểm tra văn bản đã loại thông tin bị cấm, yêu cầu AI lập bảng đối chiếu có nguồn, sửa đánh giá với lý do và phê duyệt quyết định. Một reviewer IT có thể góp ý/đánh giá theo quyền được cấp. Người quản trị quản lý account, cấu hình và vận hành; không có quyền đọc hồ sơ hoặc quyết định tuyển dụng chỉ vì có role `admin`.

MVP chạy local trước; tuần 4 là vertical slice dùng synthetic, tuần 8 là ứng viên assisted pilot có điều kiện. Việc có thể mời HR/IT không chứng minh đã có nhãn chuẩn hoặc nghiệm thu. Màn hình phải hiện một trong ba nhãn lấy từ cấu hình server: `Sandbox · Dữ liệu mẫu`, `Shadow · Dữ liệu thật — AI chưa hỗ trợ quyết định`, `Pilot có hỗ trợ · Dữ liệu thật`. Người dùng không đổi mode bằng một toggle phía client.

Real-shadow được mở sau khi đạt gate quyền sử dụng dữ liệu, privacy, kỹ thuật, provider/budget, rubric đã duyệt, kiểm thử synthetic và vận hành/đào tạo cho shadow theo tài liệu 06/09. Giai đoạn này dùng để thu nhãn HR độc lập và đo lỗi thực tế; chưa cần đạt gate chất lượng trên dữ liệu thật hoặc UAT assisted. Chỉ mở assisted pilot sau khi báo cáo real-shadow, chất lượng và UAT đều đạt đúng tiêu chí đã ghi trước. Không dùng yêu cầu “đã đạt real-shadow” để chặn việc bắt đầu real-shadow.

Ngoài MVP: cổng ứng viên, email/tin nhắn, ATS, SSO, hội đồng phê duyệt nhiều cấp, khảo sát tính cách, tìm dữ liệu mạng xã hội, tự xác minh CV, tự chọn top-N, tự loại ứng viên, dịch toàn bộ CV mặc định, multi-tenant. Không dựng nút giả cho các chức năng này.

## 2. Personas, quyền và điều kiện thao tác

Account role và membership của đợt tuyển là hai lớp. Một account có thể có nhiều role được cấp rõ; membership không tự sinh từ role. Quyền raw CV là grant riêng có phạm vi. Kiểm tra ở API cho mọi request; việc ẩn nút chỉ phục vụ UX.

| Tác nhân | Phạm vi và tác vụ | Không mặc nhiên được phép |
|---|---|---|
| `admin` | Tạo/vô hiệu hóa account, cấu hình budget/provider, xem metric vận hành; quản lý membership theo chính sách | Đọc CV, cấp điểm, duyệt rubric/final decision, xem nội dung evidence |
| `recruiter` + membership `owner` | Quản lý đợt được phân công; upload; duyệt sanitized khi đồng thời có raw grant; duyệt rubric; xem/sửa đánh giá; final decision; yêu cầu xóa | Xem raw/duyệt sanitized nếu chưa có raw grant; đọc đợt khác; bỏ qua stale/quality gate |
| `recruiter` + membership `reviewer` | Xem sanitized đã được cấp quyền; tạo HR revision/proposal; xem nguồn; soạn câu hỏi; sửa sanitized draft khi có raw grant | Duyệt rubric, duyệt bản gửi ngoài, final decision hoặc thay đổi membership |
| `reviewer` + membership `reviewer` | Reviewer IT: upload CV trong phạm vi; xem tiêu chí và evidence; tạo HR revision/proposal; sửa sanitized draft khi được cấp raw grant rõ ràng | Xóa, xem raw nếu chưa có grant, thao tác quản trị hoặc final decision |

Default mỗi đợt có một owner chịu trách nhiệm. Admin có thể đồng thời là recruiter owner khi được cấp tường minh; audit ghi quyền đã sử dụng. Viewer chưa được phân công không thấy tên, số hồ sơ hay nội dung đợt. Raw grant không được hiểu thành quyền export hàng loạt.

MVP cho HR yêu cầu xóa ở application/candidate theo quyền và quy trình dữ liệu ở tài liệu 05; destructive scope được trình bày rõ trước xác nhận. Admin vận hành luồng xóa không cần mở CV.

## 3. Hợp đồng sản phẩm và cách diễn giải điểm

1. Candidate và application khác nhau: một ứng viên có thể nộp nhiều đợt. Không tự merge CV theo tên/email hoặc tự suy luận cùng người.
2. Mỗi run khóa CV version, sanitized version đã duyệt, JD/rubric version và manifest AI. Cập nhật bất kỳ nguồn đầu vào làm recommendation cũ stale.
3. AI output bất biến. HR tạo revision riêng: bản nháp có thể sửa; bản finalized được khóa và trở thành nguồn để owner review quyết định. Không đổi rubric/weight trên từng candidate.
4. Ba outcome criterion: `assessed` + integer 0..4 + nguồn; `insufficient_evidence` + null; `conflicting_evidence` + null. Danh sách kỹ năng đứng riêng không đủ gán điểm. Không có tiêu chí `not_applicable` theo ứng viên.
5. `coverage`, `observed_score`, `comparable_score` và recommendation do backend tính đúng công thức 00. Frontend không tự làm tròn rồi quyết định. Hiển thị một chữ số thập phân; các ngưỡng so trên giá trị chưa làm tròn.
6. Bất kỳ criterion null: `needs_clarification`. Nếu complete, comparable ≥70 và ba core ≥2: `consider_next_round`. Còn lại: `review_required`. Ngưỡng phải được owner duyệt với rubric; chúng chưa được validated.
7. Quyết định `advance`, `request_information`, `not_advance` chỉ do owner. Không có tự động hóa đổi vòng. HR có thể quyết định khác AI khi đã review nguồn, ghi lý do và đủ các điều kiện an toàn.
8. `insufficient_evidence` về nghiệp vụ không phải lỗi xử lý. OCR thất bại, output invalid, budget exhausted là lỗi/tạm dừng kỹ thuật và không tạo recommendation hợp lệ.

**Điểm cần hiệu chuẩn với HR/IT:** cả sáu criterion ở mức2 cho tổng50, mức3 cho tổng75. Mức2 mô tả thực hiện một chức năng thông thường, nên threshold70 không mặc nhiên là ngưỡng phù hợp cho mọi ứng viên junior. Giữ70 trong seed theo quyết định nền, nhưng phải đánh giá trên hồ sơ mẫu trước khi duyệt cho đợt thật. `review_required` là yêu cầu HR xem xét, không là nhãn tiêu cực hoặc đề xuất loại.

**Copy phải dùng thống nhất:**

| Vị trí | Copy tiếng Việt |
|---|---|
| Banner trang đánh giá | `AI hỗ trợ đối chiếu CV với tiêu chí đã duyệt. HR kiểm tra bằng chứng và quyết định bước tiếp theo.` |
| Nhãn observed | `Điểm trên tiêu chí đã có bằng chứng` |
| Tooltip observed | `Điểm này chỉ dùng các tiêu chí hiện đánh giá được. Đây không phải xác suất được tuyển hay phép đo năng lực tuyệt đối.` |
| Nhãn coverage | `Độ bao phủ bằng chứng` |
| Tooltip coverage | `Tỷ lệ trọng số tiêu chí đã có đủ thông tin để đánh giá. Thiếu thông tin không đồng nghĩa không đáp ứng.` |
| Null | `Chưa đủ thông tin` / `Bằng chứng mâu thuẫn — cần kiểm tra` |
| Evidence label | `Thông tin ứng viên cung cấp; chưa được xác minh độc lập.` |
| AI suggestion | `Có thể cân nhắc vòng tiếp theo` / `Cần làm rõ thông tin` / `Cần HR xem xét` |
| Incomplete tổng | `Chưa có điểm dùng để so sánh toàn bộ tiêu chí.` |
| Stale | `Nguồn hoặc tiêu chí đã thay đổi. Kết quả này chỉ còn giá trị lịch sử. Hãy đánh giá lại, hoặc chuyển sang đọc tài liệu hiện hành để HR quyết định thủ công khi đủ quyền.` |
| Override | `Thay đổi của bạn được lưu riêng cùng lý do. Đánh giá AI ban đầu được giữ để truy vết.` |
| CTA decision | `Ghi nhận quyết định của HR` |

Không có biểu tượng cúp, badge “ứng viên tốt nhất”, màu đỏ cho thiếu thông tin, thanh điểm tổng quá lớn, AI confidence giả lập hoặc danh sách mặc định xếp từ cao xuống thấp.

## 4. Luồng chuẩn và các điểm chặn

**Chuẩn bị đợt:** owner tạo JD → soạn hoặc dùng AI đề xuất rubric → chỉnh sửa → duyệt phiên bản → bắt đầu tiếp nhận. Rubric draft không được dùng cho assessment thật. Seed chỉ là bản nháp để tiết kiệm nhập liệu.

**Tiếp nhận:** owner chọn file → frontend kiểm tra sơ bộ → server kiểm tra loại/kích thước/giới hạn → tạo application + job → parse/OCR cục bộ → sanitizer → owner review bản sanitized → approve phiên bản cụ thể → mới được phép gọi external assessment. Không gọi DeepSeek trong lúc upload/parse/redaction chưa duyệt. Thay đổi sanitized text sinh version mới, hủy hiệu lực approval cũ; không sửa raw CV.

**Review bản gửi ngoài:** quyền approve đòi đồng thời owner và raw CV grant còn hiệu lực. Màn hình hai cột đối chiếu raw/derivative an toàn với sanitized. Nếu không có raw grant, chỉ được xem bản sanitized đã công bố theo quyền; không thể sửa hoặc approve bản gửi ngoài. Reviewer có raw grant được sửa draft/đề xuất nhưng không final approve. Highlight các vùng bị che và những mục parser nghi lỗi. Owner kiểm tra cả header/footer, chữ OCR, nội dung section, link/file metadata được gửi. Có thể che thêm hoặc sửa lỗi OCR bằng bản text mới; không được thêm năng lực không có trong CV. Chỉnh sửa có lịch sử và ánh xạ nguồn theo hợp đồng backend. Nếu thiếu trang/nguồn không đáng tin: chuyển xử lý thủ công hoặc yêu cầu nộp lại.

Checkbox duyệt: `Tôi đã kiểm tra nội dung văn bản sẽ gửi để đánh giá, bao gồm thông tin cá nhân còn sót và lỗi trích xuất.` Nút: `Duyệt bản này để đánh giá`. Hiển thị provider được cấu hình và text snapshot thực tế; không ám chỉ đã ẩn danh tuyệt đối. Quyền dùng DeepSeek đã được trường cho phép; workflow này là kiểm tra nội dung từng hồ sơ, không hỏi lại user về quyền dùng vendor.

**Đánh giá:** owner bấm chạy → backend kiểm tra gate, budget và snapshot → worker chạy → UI theo dõi. Bản đánh giá chưa hợp lệ không được dùng để tuyển dụng. Cancel/retry chỉ theo endpoint hợp đồng, không tạo lượt gọi ngoài không giới hạn từ nút refresh. Sau cancel, UI xác nhận backend đã hủy hiệu lực run trước khi chuyển đường quyết định; response đến muộn không được publish thành kết quả hiện hành hoặc thay đổi quyết định HR, dù vendor vẫn có thể tính phí call đã nhận.

**HR review:** mở criterion → xem nguồn và anchor → ghi nhận đã review. Nếu giữ nguyên AI hợp lệ, owner có thể attestation trực tiếp trên run đó, không bắt tạo HR revision giống hệt. Nếu sửa đánh giá, tạo/sửa nháp → finalize HR revision → owner review effective revision. Sau đó chọn quyết định, ghi lý do và xác nhận. Evidence review gắn với effective result/snapshot/generation; không tái dùng checkbox cũ sau thay đổi. Khi AI không hợp lệ hoặc không chạy được, dùng basis manual/technical ở mục5; không gán điểm0 cho phần chưa biết để mở khóa quyết định.

**Riêng real-shadow:** HR ghi nhận đánh giá độc lập theo rubric và quyết định theo quy trình hiện tại, chưa thấy output AI. Backend phải chặn endpoint trả điểm, recommendation, giải thích và câu hỏi AI cho người đang gán nhãn trước khi nhãn được khóa; không chỉ che bằng CSS. Đầu mối evaluation chỉ mở báo cáo khác biệt sau khi nhãn/đánh giá HR đã đóng băng. Không hiển thị gợi ý AI để điều chỉnh quyết định đang diễn ra trong shadow.

**Hồ sơ cần thêm thông tin:** HR ghi `request_information`; hệ thống chưa gửi email. HR liên hệ ngoài hệ thống theo quy trình của trường. Thông tin bổ sung trong MVP phải được đưa vào CV version mới hoặc tài liệu CV bổ sung trong định dạng đầu vào được hỗ trợ, rồi parse/sanitize/approve lại; không ghi thêm lời khai vào nguồn CV cũ. Không fetch portfolio/link trên internet.

## 5. Routes, thành phần và validation

Các route dưới đây là route UI. API cụ thể và DTO theo tài liệu 03. Mọi form có label, helper, lỗi gắn field, trạng thái submitting và chống double-submit. Thông báo không đưa nội dung CV vào toast, analytics hoặc console.

### `/login`, `/onboarding`

- Login bằng cơ chế account/session nội bộ; HttpOnly cookie + CSRF, không lưu token ở localStorage. Generic error `Thông tin đăng nhập không hợp lệ.`; account disabled/session hết hạn theo backend. Không triển khai tự đăng ký/public reset password trong MVP.
- Onboarding có 5 bước ở mục 8; lưu tiến độ theo account + phiên bản hướng dẫn. Role khác nhau thấy bước có quyền tương ứng. Có nút `Xem lại hướng dẫn` trong menu trợ giúp.

### `/requisitions` — danh sách đợt

- Cột: tên đợt, trạng thái đợt, owner, số application trong phạm vi được phép, rubric active version, thời điểm cập nhật.
- Default sort: cập nhật mới trước; tìm theo tên/mã đợt. Không tìm danh tính ứng viên tại màn hình này.
- Form tạo: tên 5–200 ký tự; JD text bắt buộc 100–50.000 ký tự; owner theo policy; label môi trường đọc-only. Unicode được giữ; whitespace-only bị từ chối. Độ dài văn bản chỉ là giới hạn nhập, không đánh giá năng lực.
- Empty: `Chưa có đợt tuyển dụng được phân công.` Owner đủ quyền thấy `Tạo đợt tuyển dụng`. Error: mã hỗ trợ + retry; không hiển thị đợt của account khác từ cache cũ.

### `/requisitions/[id]` — workspace đợt + upload

- Header: JD revision, rubric version/status, owner, trạng thái gate. Tabs: `Hồ sơ`, `JD & tiêu chí`, `Lịch sử`.
- Bảng application: mã hồ sơ, nhận lúc, trạng thái xử lý, trạng thái HR, số tiêu chí đủ bằng chứng, phiên bản nguồn, người phụ trách review. Không hiện tên/trường/ảnh trong bảng; danh tính chỉ ở panel riêng cho raw grant nếu có nhu cầu nghiệp vụ.
- Default sort thời gian nhận tăng dần để xử lý công bằng theo hàng đợi. Filter trạng thái kỹ thuật, HR, stale, incomplete. Pagination server-side. Không score-sort chung incomplete. Nếu HR chọn sort comparable, UI tạo nhóm complete có sort và nhóm incomplete tách biệt, giữ rõ bộ lọc/số lượng cả hai nhóm.
- Upload mục tiêu hỗ trợ PDF/DOCX, tối đa 10 MiB/file (10.485.760 bytes), 10 trang, 20 file/batch. UI chỉ cho định dạng mà capability backend đang bật và đã kiểm thử; nếu DOCX bị hoãn, hiển thị `Phiên bản này chỉ nhận PDF` và chặn DOCX rõ ở cả API. Frontend kiểm tra extension/size/count; server kiểm tra MIME thực và page count sau parse/render. Tài liệu ngoài giới hạn bị từ chối rõ, không truncate. Không mở macro, không tải link ngoài. Upload progress từng file, kết quả từng item; một file lỗi không làm mất kết quả file khác.
- Duplicate hash chỉ kiểm trong cùng application: cùng current document trả409 kèm version hiện có. Không dò checksum giữa các candidate hoặc cảnh báo xuyên application. Owner chủ động chọn candidate đã biết trước upload; không tự merge hay suy luận danh tính từ file.
- Empty: `Chưa có hồ sơ. Tải CV để bắt đầu.` Rubric draft vẫn cho upload/parse nhưng khóa nút assessment và giải thích gate.

### `/requisitions/[id]/rubric` — JD và rubric

- Cột trái JD có requirement IDs và highlight nguồn; phải thấy bản seed là `Bản nháp mẫu — cần HR duyệt`.
- Criterion form: `id` cố định theo seed; label; mô tả; weight integer 1–100; nguồn JD; anchor 0..4 đủ năm mức; core floor nếu có. MVP luôn giữ đúng sáu criterion IDs theo 00, không thêm/bớt hoặc đổi ID dù rubric còn draft. Thay cấu trúc tiêu chí là thay đổi phạm vi ngoài MVP, không giải quyết bằng một control tùy ý ở UI.
- Validate tổng weight=100; đúng sáu IDs duy nhất; mỗi anchor không rỗng; source quote tồn tại trong JD revision; policy threshold trong 0..100 và core floor integer0..4; danh sách core đúng `python_backend`, `api_design`, `sql_data` theo seed. Linter cảnh báo yêu cầu bị cấm hoặc proxy; owner không được phê duyệt khi hard-block chưa được giải quyết.
- Có diff draft vs active trước duyệt. Nút `Duyệt rubric phiên bản N` chỉ owner; bắt buộc checkbox `Tôi đã kiểm tra tiêu chí, nguồn JD, trọng số và ngưỡng đề xuất.` Ghi owner/time/hash. Không có auto-approve sau AI generation.
- Active rubric read-only. Chỉnh sửa tạo draft version mới; trước publish phải hiển thị số assessment sẽ stale. Không silent rescore.
- Tab `Câu hỏi cốt lõi` quản lý question bank gắn rubric. Seed trong `examples/interview-question-bank.v1.json` là draft; owner xem, sửa và duyệt trước khi dùng. Bản approved khóa nội dung, thứ tự và hướng dẫn chấm. Thay đổi bank tạo phiên bản mới ở cấp rubric, có diff và approval của owner; không sửa core question riêng cho một ứng viên. Hiệu lực và staleness của các bộ câu hỏi đã tạo theo hợp đồng03.

### `/applications/[id]/sanitization` — kiểm tra văn bản

- Header: application mã, CV revision, parser/sanitizer versions, trạng thái chất lượng, số trang xử lý, sanitized version, trạng thái approval.
- Text editor phân section/page, highlight redaction, có tìm kiếm trong text để HR rà soát. Các nút `Che đoạn chọn`, `Lưu phiên bản chỉnh sửa`, `Báo lỗi trích xuất`, `Duyệt bản này để đánh giá`. Không nút restore tên/school hàng loạt.
- Chỉnh sửa bắt buộc lý do 10–1.000 ký tự; nhắc không thêm dữ kiện. Save tạo version + diff; approval chỉ trên saved version. Phải re-open review sau save trước approve.
- Block approval nếu parser quality fatal/missing pages, text rỗng, chưa lưu thay đổi, version đổi từ tab khác, source mapping không hợp lệ, actor không owner hoặc thiếu raw grant còn hiệu lực. Warning OCR không fatal phải có acknowledgement cụ thể; không giả định độ chính xác chỉ từ OCR confidence.
- Empty: `Chưa có văn bản để kiểm tra. Hồ sơ đang được trích xuất.` Failed: hiện loại lỗi và `Xử lý thủ công`/`Tải lại CV`. Stale: giữ bản cũ read-only + link phiên bản hiện tại.

### `/applications/[id]/assessment` — bằng chứng trước điểm

- Đầu trang không có hero score. Bảng chính: tiêu chí, outcome, mức theo anchor, evidence count, tình trạng HR review; mỗi hàng mở evidence drawer gồm quote, trang/section, source version và anchor.
- Score tổng/coverage/recommendation ở panel thu gọn `Xem tổng hợp`; sau khi mở vẫn giữ tooltip. Kịch bản đánh giá độc lập HR ở benchmark phải ẩn toàn bộ AI score/recommendation/explanation đến khi HR nộp; không chỉ che điểm tổng.
- Nút `Chạy đánh giá` chỉ khi rubric active + sanitized approved + gate/budget hợp lệ. Lúc running hiển thị bước và thời gian chờ, không dựng phần trăm tiến độ giả. Không refresh-trigger run.
- Lỗi có mã hỗ trợ, bước lỗi, hành động được phép; không đưa prompt hoặc CV thô vào lỗi. Recommendation absent nếu technical failure. Nút retry hiển thị khả năng tính phí, bị disable nếu retry/budget cap hết.
- Incomplete không bị ẩn; biểu diễn `4/6 tiêu chí đủ bằng chứng · coverage 70%` cùng danh sách cần làm rõ. Conflict hiển thị cả hai đoạn nguồn.

### `/applications/[id]/review` — revision và quyết định

- Mỗi criterion cho giữ kết quả AI hoặc tạo HR value riêng. Outcome assessed phải có score0..4, nguồn hợp lệ và lý do. Null outcome phải null score. Reason code gồm `missed_evidence`, `misinterpreted_role`, `wrong_anchor`, `source_error`, `other`; ghi mô tả 20–2.000 ký tự cho thay đổi, tránh tên/thuộc tính bị cấm. `other` luôn cần mô tả.
- `Lưu nháp` chưa phải quyết định. `Hoàn tất bản đánh giá HR` khóa revision, ghi actor/time; revision mới phải ghi liên hệ bản trước. AI-original tab read-only giúp audit nhưng không thay thế bản effective.
- Final decision form: choice 1 trong `advance`, `request_information`, `not_advance`; reason20–2.000 ký tự; nguồn/criterion liên quan; evidence-review acknowledgement gắn effective revision. Với incomplete có thể quyết định bằng quyền HR sau review tất cả tiêu chí và lý do rõ; không bắt buộc làm dữ liệu thành complete bằng điểm bịa.
- Nút final chỉ owner. Chọn rõ `Duyệt bản đánh giá`, `Đọc CV và quyết định thủ công`, hoặc `Yêu cầu gửi lại vì lỗi xử lý`; ánh xạ `assessment_review`, `manual_document_review`, `technical_information_request` ở03. Đường assessment khóa khi result invalid/draft/chưa review hoặc sanitized approval mất hiệu lực. Đường manual document cần raw grant, safe file đã đọc, rubric current và căn cứ criterion; không cần AI/OCR thành công. Đường technical chỉ có request_information, document/hash/error acknowledgement và reason; không cần sanitized text. Mọi đường chặn deleting/deleted, snapshot mismatch, đợt closed và analysis job chưa được cancel. Không có bulk final approve.
- Manual form không tự tạo điểm hoặc gán score0. Hiện sáu tiêu chí để owner xác nhận review; nhập ít nhất một căn cứ liên kết criterion với trang/section của raw file, tránh thông tin bị cấm. Nếu file không an toàn/không đọc được chỉ hiện yêu cầu nộp lại. Cancel analysis trước khi đổi đường manual; call đã gửi ngoài vẫn có thể tính phí, kết quả muộn không thay quyết định.
- Modal xác nhận hiện mã ứng viên, quyết định, decision basis, effective revision hoặc document/error reference, lý do, actor. Copy: `Đây là quyết định của HR. Hệ thống sẽ lưu người phê duyệt, lý do và phiên bản bằng chứng.` Nhấn confirm đúng một lần qua idempotency; xung đột tab khác trả409, refresh dữ liệu và review lại, không tự retry quyết định.

### `/applications/[id]/interview` — câu hỏi theo yêu cầu

- Chỉ sinh khi rubric, bank approved và nguồn đánh giá hiện hành hợp lệ; không auto-generate cho tất cả CV. Trong shadow không mở bộ câu hỏi AI cho người đang gán nhãn/quyết định. Chưa có interview-result scoring trong MVP.
- Tách hai panel. `Câu hỏi cốt lõi · Bank vN` read-only: backend lấy từ snapshot bank đã duyệt; cùng rubric/bank version thì các ứng viên nhận nội dung và thứ tự giống nhau. Model không được sinh lại, diễn đạt lại hoặc thay câu core. `Câu hỏi làm rõ hồ sơ` chứa follow-ups gắn criterion, nguồn hoặc gap cần xác minh cùng mục đích và hướng dẫn chấm.
- Owner/reviewer chỉ sửa follow-ups ở trang candidate. Nút `Lưu bản chỉnh sửa` tạo HR revision riêng theo API03, giữ AI draft gốc; reload phải đọc lại đúng revision đã lưu. Hiển thị người sửa, thời gian và base draft/source/bank version. Không cho override bank text trong payload candidate; chỉ owner được chuyển đến tab bank ở rubric để tạo bản thay đổi cho cả đợt.
- Validate follow-ups theo schema trong contracts, criterion ID hợp lệ và nguồn thuộc snapshot. Câu hỏi về gap có thể tham chiếu criterion/trạng thái thiếu thông tin thay vì bịa quote CV. Chặn thuộc tính bị cấm; không hỏi tuổi, gia đình, quê, tên trường hoặc suy đoán tính cách. Không tự gửi ra ngoài.
- Source/rubric/bank version thay đổi: bộ câu hỏi stale theo03, giữ bản cũ để audit và không trình bày là hiện hành; generate/review lại theo phiên bản mới. Edit conflict trả409 và yêu cầu refresh/diff, không ghi đè nháp khác.
- Empty: `Chưa có bộ câu hỏi. Tạo khi chuẩn bị phỏng vấn.` Bank chưa duyệt: `Cần owner duyệt bộ câu hỏi cốt lõi trước khi tạo câu hỏi cho hồ sơ.` Budget failure giữ nội dung đã lưu và bản chỉnh sửa đang mở, không clear form.

### `/settings/users`, `/settings/budget`, `/audit`

- Users: admin quản lý role và membership; raw grant do owner cấp tại application theo03, admin không có quyền này chỉ từ role admin. Tất cả thay đổi có audit; quyền mới không mặc định tick. Không cho frontend tự sửa own-role.
- Budget: admin thấy cap, spent, reserved, remaining và rate-card status; input số dương/zero theo policy, loại currency USD. Thiếu rate card hoặc provider probe chưa đạt: external calls disabled. Thay cap không mua credit.
- Audit: filter event/time/actor/requisition trong quyền; cột thời gian UTC đã chuyển múi giờ hiển thị, actor, action, object code, revision, outcome. Log vận hành không có toàn bộ CV/prompt. Không cho sửa/xóa một event qua UI.

## 6. States dùng chung và khả năng tiếp cận

| Trạng thái | Quy tắc UI |
|---|---|
| Loading | Skeleton cấu trúc, `Đang tải…`; không hiện điểm mẫu; disable mutation khi chưa có snapshot |
| Empty | Giải thích nguyên nhân và CTA đúng quyền; không coi empty là error |
| Forbidden/not found | Thông báo chung không làm lộ object; xóa cache theo account/session |
| Session expired | Đăng nhập lại; bảo toàn nháp không chứa PII ở memory chỉ đến khi tab kết thúc, không localStorage |
| Network/API failure | Mã hỗ trợ + retry read; mutation uncertain phải tra status/idempotency, không tự gửi lại |
| Incomplete | Danh sách thiếu thông tin, không màu đỏ hay score0; HR vẫn xem nguồn và request info |
| Stale | Banner rõ, kết quả cũ read-only; khóa basis assessment dùng kết quả đó. Manual/technical vẫn có thể dùng khi snapshot tài liệu/lỗi hiện hành, quyền và điều kiện riêng đều hợp lệ; mọi basis vẫn chặn snapshot mismatch hoặc dữ liệu đang xóa |
| Budget/quality gate blocked | Nêu gate cụ thể và người có quyền xử lý; không hiện nút retry vô hạn |
| Deletion pending/deleted | Khóa mọi assessment/interview/edit; xóa cache chi tiết, hiển thị trạng thái tối thiểu |

Mọi tương tác dùng được bằng keyboard; focus quay lại nút mở khi đóng drawer/modal; aria-live cho trạng thái job; không dùng màu làm tín hiệu duy nhất; mức tương phản theo nền giao diện. Desktop là mục tiêu chính, nhưng ở chiều rộng768px không mất nút/nguồn; bảng có scroll ngang với tiêu đề còn đọc được. Hiển thị thời gian theo Asia/Ho_Chi_Minh, lưu UTC. Ngôn ngữ UI tiếng Việt, quote giữ nguyên Việt/Anh/mixed.

## 7. User stories và acceptance criteria bắt buộc

| ID | User story | Acceptance criteria quan sát được |
|---|---|---|
| US-01 | Owner mở đợt và duyệt rubric | Draft không chạy assessment thật; tổng weight sai bị chặn cả API; approve lưu đúng JD/rubric version và actor; sửa tạo version mới |
| US-02 | Owner upload batch | Tối đa20,10MiB,10trang; báo kết quả từng file; không truncate; file ngoài hỗ trợ không vào queue đánh giá; lỗi một file không mất file khác |
| US-03 | Owner kiểm tra sanitized trước vendor | Approve đòi owner+raw grant; reviewer+raw chỉ sửa draft; network test chứng minh zero external CV calls trước approval; sửa text hủy approval; payload ra ngoài khớp hash/version đã duyệt |
| US-04 | HR đối chiếu evidence | Mỗi assessed criterion có source thuộc đúng application/version; bấm mở đúng quote; quote không tồn tại bị chặn trước UI result hợp lệ |
| US-05 | Reviewer ghi nhận khác AI | Giữ AI original; HR revision có lý do, nguồn và actor; null không biến thành0; finalize khóa revision; reviewer không final decision |
| US-06 | Owner quyết định | Chỉ owner được gọi API; giữ AI có thể attest trực tiếp, sửa thì dùng finalized HR revision; review+reason+snapshot theo basis; stale/concurrent change bị chặn đúng basis; lỗi AI không khóa manual/technical hợp lệ; response của run đã cancel không publish |
| US-07 | HR xử lý thiếu thông tin | Skills-only là null; suggestion needs_clarification; có request_information; không gửi email, không mở đầu vào internet |
| US-08 | HR làm việc với CV Việt/Anh/mixed | Quote giữ ngôn ngữ gốc; tiếng Việt có dấu đúng; cùng criterion IDs/weights; không tăng điểm chỉ vì viết tiếng Anh |
| US-09 | Admin kiểm soát chi phí | Cap/rate-card gate ở backend; displayed reserved/spent đúng; double-click không nhân đôi job/chi phí; budget hết có đường thủ công |
| US-10 | HR sử dụng bản nguồn mới | Upload/sanitized/rubric revision mới làm run cũ stale; không kế thừa checkbox evidence review; lịch sử quyết định không bị ghi đè |
| US-11 | Người có quyền yêu cầu xóa | Phạm vi cần xóa được hiển thị; pending khóa mọi tác vụ; job không tái tạo dữ liệu; audit chỉ còn metadata được phép |
| US-12 | HR học bằng sandbox | Có nhãn sample trên mọi màn; không trộn DB/storage với real; 5 tình huống hoàn thành và ghi progress; mở lại hướng dẫn được |
| US-13 | Reviewer không được đọc ngoài phạm vi | Test trực tiếp object IDs, file URL và evidence endpoint không đọc chéo; admin-only cũng không được raw CV |
| US-14 | HR tạo câu hỏi grounded | On-demand; core từ approved bank snapshot giống nhau theo rubric/bank version; model không sinh lại core; candidate edit chỉ follow-ups và được persist thành HR revision; gắn criterion/source/gap; bank hoặc nguồn đổi gây stale; không tự gửi |

## 8. Onboarding, sandbox và UAT với HR/IT

Sandbox có deployment/database/storage riêng, mock provider mặc định và fixture synthetic được xác định rõ. Khi bật provider thật để test synthetic vẫn có budget/probe; không kéo real CV sang sandbox. Bộ mẫu gồm: đủ bằng chứng; mixed-language; thiếu thông tin; OCR lỗi; AI diễn giải sai từ “hỗ trợ” thành “chủ trì”.

Walkthrough5 bước: (1) nhận diện criterion không phù hợp trong draft; (2) review sanitized và che đoạn sót; (3) mở source so với anchor; (4) sửa một nhận định AI sai bằng HR revision; (5) quyết định giả lập và đọc audit. Dùng một đề xuất AI sai được gắn nhãn “tình huống huấn luyện”, không giả rằng hệ thống thực đã mắc lỗi đó.

Nghiệm thu onboarding: người HR hoàn tất các thao tác theo quyền mà người hướng dẫn không làm hộ; giải thích được observed/coverage/null; phát hiện lỗi được cài; biết xử lý thủ công và báo lỗi. Lưu kết quả task pass/fail, thời gian và lời góp ý; không dùng điểm onboarding để đánh giá hiệu suất nhân viên HR. Reviewer IT chỉ đi qua các bước thuộc quyền.

Lịch cộng tác và ước lượng công gán nhãn lấy theo H1–H5 trong [09-implementation-backlog.md](09-implementation-backlog.md), gồm buổi duyệt JD/rubric, các phiên chấm độc lập, holdout, shadow/UAT và bàn giao. Walkthrough20–30 phút chỉ là thời gian học thao tác, không bao gồm việc gán nhãn nhiều CV. Đây là nhu cầu kế hoạch, chưa phải giờ HR/IT đã cam kết. Thiếu buổi/nhãn phải ghi gate còn thiếu, không tự thay HR bằng LLM rồi tuyên bố đạt AI–HR agreement.

**Definition of Done về sản phẩm:** US-01..US-14 có bằng chứng test/demo; HR/IT duyệt seed rubric cho đợt thật; walkthrough có kết quả UAT; không còn lỗi chặn privacy/HITL; dashboard công bố trạng thái qualification và các gate chưa đạt. Một giao diện chạy được trên máy phát triển không đồng nghĩa đủ điều kiện production.
