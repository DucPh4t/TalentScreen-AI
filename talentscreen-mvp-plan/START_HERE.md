# Bàn giao TalentScreen AI cho AI implement

Bạn đang nhận **bộ đặc tả để xây phần mềm**, không phải repository đã implement. Mục tiêu cuối là HR trường đại học dùng trợ lý trong một đợt tuyển dụng IT thật, trên cơ sở CV + JD có bằng chứng và HR quyết định cuối cùng.

## Prompt bàn giao có thể dùng trực tiếp

> Hãy triển khai TalentScreen AI theo bộ tài liệu trong thư mục `talentscreen-mvp-plan/`. Đọc README, 00-scope-decisions, 01-product-and-ux, 02-architecture, 03-data-api-state-machines, 04-ai-rag-prompts, 05-security-privacy và 09-implementation-backlog trước khi sửa code. Sau đó đọc các tài liệu chuyên đề và contracts khi làm task liên quan.
>
> Bối cảnh đã chốt: một người làm trong 4–8 tuần; MacBook Air M4; FastAPI, Next.js, PostgreSQL/pgvector và Docker; chạy local trước; có API được người dùng gọi là deepseek-chat; trường đã cho phép sử dụng DeepSeek theo chính sách; có thể mời HR và người chuyên môn IT duyệt rubric, chấm và nghiệm thu. Không hỏi lại các lựa chọn đã chốt này. JD Backend Python, rubric và fixture trong examples là bản mẫu do người lập plan soạn, không phải tài liệu HR đã duyệt.
>
> Trước tiên inspect repository và các hướng dẫn áp dụng, tạo hoặc tiếp tục implementation-progress.md, xác nhận trạng thái các task B00–B26. Tiến hành theo dependency; ưu tiên một vertical slice chạy được bằng mock/synthetic, rồi tích hợp provider và kiểm thử thực tế. Mỗi milestone phải có bằng chứng chạy và test, không chỉ UI mock hoặc file skeleton. Không triển khai cloud trong nhiệm vụ local nếu chưa được giao.
>
> Giữ các bất biến: không dùng thuộc tính bị cấm để chấm; raw CV không gửi DeepSeek; CV thật cần sanitized snapshot được HR có quyền duyệt; mọi criterion `assessed` phải có bằng chứng đúng application/version. `insufficient_evidence` có score null và được phép không có evidence; không tạo nguồn giả để lấp chỗ trống. `conflicting_evidence` có score null và các nguồn mâu thuẫn theo schema. Unknown không bằng0; tổng điểm và đề xuất do code tính; không tự loại/chuyển vòng; HR sửa được và có audit; xóa phải chặn job tái tạo dữ liệu; budget/rate/model phải được kiểm tra trước paid batch. Không làm autonomous agent loop, ATS, applicant portal, gửi email hay scraping ứng viên.
>
> Quyết định HR có ba basis theo03: assessment hợp lệ, đọc tài liệu an toàn thủ công, hoặc yêu cầu gửi lại vì lỗi kỹ thuật. AI/OCR lỗi không khóa mọi công việc của HR và không tạo điểm0. Nếu giữ AI hợp lệ thì có thể attest trực tiếp; chỉ cần HR revision khi sửa/đánh giá lại. Stale được kiểm tra theo basis và snapshot hiện hành. Response của analysis đã cancel không được publish hay thay đổi quyết định HR.
>
> Core interview questions lấy nguyên văn từ approved question bank gắn rubric, không để model sinh lại cho từng candidate. Model chỉ tạo follow-ups; HR chỉ sửa follow-ups tại candidate và lưu revision. Owner muốn đổi bank phải tạo/duyệt phiên bản ở cấp rubric; seed bank chưa approved.
>
> Giữ model identifier cấu hình của user và chạy capability probe bằng synthetic khi có key; tài liệu hiện tại có tên model khác nên không tự thay model hoặc giả định strict JSON Schema. Không expose key cho frontend hoặc log payload. Không tự tải/nhập dataset có nguồn quyền sử dụng chưa rõ. Không tuyên bố đạt chất lượng AI–HR, fairness, SLO hoặc privacy khi chưa có kết quả kiểm chứng.
>
> Với quyết định kỹ thuật thông thường, tự chọn trong các ràng buộc và ghi decision record; không hỏi user mỗi package/field. Nếu cần thay đổi nghiệp vụ, phạm vi dữ liệu hoặc chính sách đã chốt, nêu rõ xung đột và câu hỏi cụ thể. Nếu thiếu HR labels, model access hoặc policy retention thực tế, vẫn hoàn thành các task độc lập; ghi gate còn thiếu, không bịa kết quả để đóng task.
>
> Kết thúc mỗi task: ghi file thay đổi, invariant được đáp ứng, test đã chạy và kết quả, giới hạn còn lại. Kết thúc milestone: cung cấp lệnh tái hiện demo synthetic và bảng acceptance pass/fail/not-run. Real-shadow bắt đầu sau các gate kỹ thuật/privacy/provider/rubric/synthetic và vận hành/đào tạo shadow; thu nhãn HR trước khi cho xem AI, chưa dùng AI để hỗ trợ quyết định. Chỉ chuyển sang assisted pilot khi quality gate trên real-shadow và UAT cùng toàn bộ gate áp dụng trong09 đạt trên build thực và HR/IT nghiệm thu. Không yêu cầu hoàn thành real-shadow như điều kiện để bắt đầu chính giai đoạn đó.

## Trình tự đọc

1. [README](README.md): mục lục, trạng thái artifact và phạm vi.
2. [00 — Scope](00-scope-decisions.md): nguồn sự thật cho quyết định đã chốt.
3. [01 — Product/UX](01-product-and-ux.md), [JD](examples/jd-backend-python.vi.md), [rubric seed](examples/rubric-backend-python.v1.json).
4. [02 — Architecture](02-architecture.md), [03 — Data/API/state](03-data-api-state-machines.md).
5. [04 — AI](04-ai-rag-prompts.md), [assessment schema](contracts/assessment-output.schema.json), [ví dụ output](contracts/assessment-output.valid-example.json).
6. [05 — Security/privacy](05-security-privacy.md), [06 — Evaluation](06-evaluation-and-testing.md), [07 — Operations](07-operations-deployment.md), [08 — Data sourcing](08-data-sourcing.md).
7. [09 — Backlog](09-implementation-backlog.md), [10 — Review/traceability](10-audit-traceability.md), [11 — Sources](11-sources.md).

## Quy tắc giải quyết xung đột

Yêu cầu mới nhất của user ưu tiên cao nhất; kế đến 00. Contracts và examples phải khớp quy tắc của 00 và các invariant03/04; nếu không khớp, sửa đặc tả/example/test trước phần code bị ảnh hưởng. Không chọn một nhánh trái privacy/HITL chỉ vì dễ implement hơn. `draft`, `not_run`, `pending_validation` là trạng thái hợp lệ, không phải việc cần che giấu.

## Điều không nên hiểu sai

- Có API key không chứng minh alias hiện tại hoạt động; có sự cho phép DeepSeek không tự cho phép vendor khác.
- Có dataset public không có nghĩa có nhãn HR hay quyền dùng mọi nội dung cá nhân cho mọi mục đích.
- GPU M4 là GPU Apple Silicon dùng MPS phù hợp tác vụ local; không mặc định CUDA hoặc Linux-container GPU.
- Sáu tiêu chí và ngưỡng70 là seed draft để HR hiệu chuẩn, không phải chuẩn đã được kiểm định.
- Bốn tuần là mốc bản nội bộ; mục tiêu assisted pilot ở sáu–tám tuần có các điều kiện nghiệm thu thực tế.
