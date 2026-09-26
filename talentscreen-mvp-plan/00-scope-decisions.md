# TalentScreen AI — quyết định nền tảng và phạm vi bàn giao

Ngày lập: 2026-09-26. Trạng thái: đặc tả triển khai, chưa phải phần mềm đã chạy hoặc kết quả đánh giá đã đạt.

## 1. Yêu cầu người dùng đã xác nhận

- Một người triển khai trong 1–2 tháng; mốc bốn tuần là bản chạy thử nội bộ, mốc tám tuần là mục tiêu pilot có điều kiện.
- Đích sản phẩm: HR sử dụng trên đợt tuyển dụng thật để hỗ trợ quyết định. Mọi quyết định tuyển dụng do HR phê duyệt.
- Domain IT. Người lập kế hoạch được phép soạn JD mẫu. Chưa có CV mẫu; cần tìm nguồn dataset phù hợp và thiết kế dữ liệu tổng hợp.
- Máy phát triển MacBook Air M4 (GPU tích hợp Apple Silicon; dung lượng RAM chưa xác nhận). Có API được người dùng gọi là `deepseek-chat`.
- Chạy local hiệu quả trước, chuẩn bị deploy sau; chưa yêu cầu triển khai cloud trong nhiệm vụ hiện tại.
- Stack: FastAPI, Next.js, PostgreSQL + pgvector, Docker.
- Không dùng giới tính, tuổi, quê quán, tên trường và các thuộc tính cá nhân không liên quan để đánh giá. Có bằng chứng CV + JD, audit, quyền xóa, kiểm soát chi phí, đo AI–HR agreement.

## 2. Hai quyết định người dùng đã xác nhận bổ sung

| ID | Xác nhận của người dùng | Cách triển khai | Hệ quả |
|---|---|---|---|
| G-PRIVACY | Đã được phép dùng DeepSeek theo chính sách của trường. | Ghi nhận cấu hình policy được phép cho DeepSeek; real CV vẫn đi qua sanitizer và HR kiểm tra bản gửi. Không cần hỏi lại quyền dùng DeepSeek đã được xác nhận. | Phải cấu hình key, budget, retention thực tế và kiểm thử ranh giới dữ liệu; không mặc định được phép dùng thêm vendor khác. |
| G-HR | Có thể mời HR và người chuyên môn IT tham gia. | Lập các buổi duyệt JD/rubric, chấm độc lập và UAT; thời lượng/số người cụ thể chưa có. | Khả năng mời không đồng nghĩa đã có nhãn hoặc đã nghiệm thu; real pilot cần kết quả thực tế. |

Các điều kiện này không chặn phát triển local, mock provider, dữ liệu synthetic hoặc viết đặc tả. Nếu kiểm thử, nhãn HR hoặc vận hành vẫn chưa đạt khi hết tám tuần, bàn giao phần mềm cùng báo cáo gate chưa đạt; không tự tuyên bố pilot sẵn sàng.

## 3. Các default đã chốt để AI implement không phải đoán

1. Một trường/organization; môi trường synthetic sandbox tách deployment/database/storage với pilot thật. Không làm SaaS đa tenant trong MVP.
2. Một JD mẫu chính: **Chuyên viên phát triển phần mềm Backend Python cho hệ thống nội bộ trường**, junior–middle. Không đòi uy tín trường, tuổi, giới tính, số năm cứng, ảnh hay địa phương. HR sửa/duyệt trước dùng thật.
3. HR upload PDF/DOCX; chưa có cổng ứng viên, email tự động, ATS, SSO, scraping LinkedIn, xác minh background hoặc lịch phỏng vấn.
4. Một candidate có nhiều application; mỗi application thuộc một requisition. Mỗi assessment run khóa một CV version và một rubric version. Không tự suy đoán/merge danh tính giữa các CV.
5. Ba vai trò account: `admin`, `recruiter`, `reviewer`. Quyền tuyển dụng gắn membership của requisition; quyền xem raw CV là grant riêng, admin không mặc nhiên được xem raw. `recruiter` được phân công làm owner mới duyệt rubric và final decision. Một người có thể có cả account admin và membership owner nhưng phải cấp rõ.
6. Local runtime mặc định: PostgreSQL/pgvector qua Docker; Next.js, FastAPI và Python worker chạy native trên macOS để local embedding có thể dùng MPS. Cùng code phải có profile Docker CPU để chuẩn bị deploy. Không giả định GPU Apple được truyền vào Linux container.
7. Modular monolith và một worker; hàng đợi PostgreSQL, không Redis/Celery/Kubernetes/LangGraph trong MVP. Một job active mỗi worker; LLM concurrency mặc định 1.
8. Ba task LLM hữu hạn: rubric draft (mỗi JD revision), assessment (mỗi application snapshot), interview draft (on demand). Backend điều phối, retrieval và tính điểm; không autonomous tool loop, không LLM quyền ghi quyết định.
9. Provider mặc định DeepSeek qua HTTP adapter; model yêu cầu giữ cấu hình `deepseek-chat` cho đến synthetic capability probe. Không tự thay bằng model khác. Tài liệu hiện tại có tên model khác, vì vậy identifier/capabilities/pricing phải được kiểm tra trước bật kết nối thật; không giả định JSON Schema strict chỉ vì JSON mode tồn tại.
10. Baseline assessment dùng toàn văn sanitized cho CV ngắn; pgvector hybrid retrieval có feature flag và benchmark. Không bắt buộc RAG ở mọi CV. Default local embedding đề xuất `intfloat/multilingual-e5-base` dense 768 chiều; benchmark CPU/MPS trước khi pin revision. BGE-M3 là challenger, không chạy đồng thời trong vận hành MVP.
11. Lọc trước embedding/external calls. MVP real-data path có **HR duyệt bản sanitized** trước khi nội dung CV được gửi ngoài; automatic redaction không được coi là hoàn hảo. Không sửa trực tiếp raw CV. Map nguồn vào bản text sanitized version cố định.
12. Sáu tiêu chí cố định trong rubric seed: `python_backend` 20, `api_design` 25, `sql_data` 20, `testing_debugging` 15, `security_privacy` 10, `delivery_ops` 10. Tổng trọng số 100. Đây là seed draft, phải HR duyệt để có hiệu lực. Không có veto bằng cấp hoặc số năm trong JD này.
13. Criterion outcome: `assessed` (score integer 0..4 + evidence), `insufficient_evidence` (score null), `conflicting_evidence` (score null). Mỗi criterion xuất hiện đúng một lần. Skills-only listing không đủ để gán mức năng lực; evidence strength và mức đáp ứng không nhập làm một. 0 chỉ dùng có căn cứ rõ theo anchor; không dùng cho vắng thông tin. Không có `not_applicable` tùy từng candidate trong MVP.
14. `coverage` = tổng trọng số assessed / 100. `observed_score` = 100 × sum(weight × score/4) / sum(assessed weight), null nếu không có assessed. `comparable_score` chỉ có khi coverage=1 và không conflict/lỗi kỹ thuật. Không sort/rank chung bằng observed_score khi coverage<1.
15. Đề xuất backend: `needs_clarification` nếu bất kỳ criterion null; `consider_next_round` nếu comparable_score≥70 và ba tiêu chí python_backend/api_design/sql_data đều≥2; còn lại `review_required`. 70 và floor2 là cấu hình draft phải được HR duyệt cùng rubric, không phải ngưỡng validated. Không có trạng thái AI `rejected`. Không top-N tự động; default list theo thời gian nhận, sort comparable score chỉ khi HR chủ động chọn và tách incomplete rõ.
16. Technical run state và hiring decision state là hai hệ độc lập. HR decision: `advance`, `request_information`, `not_advance`; không tự quyết định bằng score. Mọi final decision cần review/acknowledgement, lý do, owner identity và snapshot; reviewer có thể đề xuất/sửa nháp, không final approve. `decision_basis` gồm `assessment_review` (AI hợp lệ hoặc HR revision trên sanitized source), `manual_document_review` (owner có raw grant đọc file an toàn, không cần AI/OCR thành công), `technical_information_request` (chỉ yêu cầu gửi lại/bổ sung hồ sơ vì lỗi kỹ thuật, không tạo điểm hoặc kết luận năng lực). Hợp đồng riêng cho từng basis ở03; lỗi AI không khóa toàn bộ công việc của HR.
17. Giới hạn khởi đầu: 10 MiB/file (10.485.760 bytes), 10 trang, 20 CV/batch, một job worker; giới hạn này kiểm chứng bằng load test, không công bố là năng lực đạt sẵn. File không hỗ trợ bị từ chối rõ trước admission và có đường xử lý thủ công. Không tự truncate trang/text/token.
18. Retry tối đa hai attempt cho một bước LLM (lần đầu + một retry/repair), giới hạn tổng assessment 4 external calls kể cả retrieval fallback/repair; tài liệu lỗi hoặc budget hết chuyển xử lý thủ công. Không dùng fallback model tự động.
19. Prompt/schema/model/parser/sanitizer/retriever/rubric được version. Kết quả AI bất biến, HR revisions riêng; bất kỳ thay đổi nguồn đã dùng đều làm recommendation cũ stale, cần chạy/duyệt lại có kiểm soát.
20. Prototype budget: cap mặc định USD 10 cho development/eval và USD 10/tháng cho pilot API, có thể cấu hình sau khi user chốt; chỉ là giới hạn chi tiêu phần mềm, không dự báo chi phí, không mua credit hoặc gọi API trong nhiệm vụ lập plan. Cần rate card được xác minh trước external calls; mock mode miễn phí là default.
21. Chưa có con số HR availability, retention, cloud provider hoặc RAM. Plan phải cung cấp cấu hình đề xuất và gate rõ; không biến giả định thành sự thật.

## 4. Nguyên tắc ưu tiên khi triển khai

- Yêu cầu người dùng và xác nhận bổ sung có ưu tiên cao nhất. Sau đó là tài liệu này; nếu tài liệu chi tiết mâu thuẫn, sửa tài liệu và test trước khi implement phần bị ảnh hưởng.
- Hợp đồng máy đọc và các ví dụ phải thống nhất với quyết định trên. Không tự hạ yêu cầu privacy/HITL để làm demo xanh.
- Tuần 4 ưu tiên vertical slice hoạt động, tuần 5–8 ưu tiên độ tin cậy, evaluation và pilot gate; không cam kết một người hoàn thành production enterprise trong bốn tuần.
- Các test không có dữ liệu HR chỉ chứng minh hành vi kỹ thuật và nhãn synthetic. Tất cả con số accuracy, agreement, fairness, chi phí, latency phải được ghi là mục tiêu cho đến khi có kết quả đo.
