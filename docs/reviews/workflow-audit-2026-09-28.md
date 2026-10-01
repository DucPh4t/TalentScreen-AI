# Rà soát workflow TalentScreen AI — 28/09/2026

Phạm vi: mã trong workspace local, giao diện tại cổng 2004, backend local và tám CV PDF do chủ dự án xác nhận được bạn bè đồng ý dùng để thử bản đã che qua DeepSeek. Đây là rà soát sản phẩm/kỹ thuật do một AI thực hiện, **không phải** phê duyệt chính thức của HR hoặc chuyên môn IT, không phải shadow trên hồ sơ ứng tuyển thật cho JD đã duyệt và không ký G1–G7.

## Kết luận nghiệp vụ

Luồng nền tảng là hợp lý: tạo JD và rubric có phiên bản → HR duyệt rubric → tiếp nhận CV → parse/OCR và kiểm tra chất lượng → che thông tin nhạy cảm → người có quyền rà soát/duyệt bản đã che → AI đánh giá từng tiêu chí kèm bằng chứng → HR rà soát, chỉnh sửa và ký xác nhận → Owner quyết định cuối cùng → audit và xóa theo yêu cầu. Điểm số là quan sát theo bằng chứng CV, không phải điểm tuyệt đối về năng lực. Thiếu bằng chứng phải dẫn tới `needs_clarification` hoặc rà soát thủ công, không tự loại ứng viên.

Trạng thái hiện tại chỉ phù hợp **sandbox/rehearsal**. `.env` giữ `APP_ENV=sandbox`, `LLM_PROVIDER=mock`, `RAG_MODE=full_text_baseline`. DeepSeek đã được thử riêng với dữ liệu synthetic và tám CV sau bước che; không đồng nghĩa app thường ngày đang tự gọi DeepSeek hay sẵn sàng dùng cho tuyển dụng thật.

## Phát hiện ưu tiên

| Mức | Phát hiện | Trạng thái/hành động |
| --- | --- | --- |
| P0 | Một trong tám bản CV sau bước che cũ còn số điện thoại viết cách nhóm. Bản đó đã đi qua một lần đánh giá DeepSeek trong app; tám CV cũng đã được gửi qua runner thử trực tiếp. | Đã thu hồi phiên bản đã che bị lỗi, xóa con trỏ kết quả hiện hành, chặn đọc kết quả liên quan (`410`), thu hồi raw grant tạm. Đã sửa detector và thêm kiểm tra thông tin liên hệ ở lúc duyệt và ngay trước egress. Không thể thu hồi dữ liệu đã gửi ở phía nhà cung cấp chỉ bằng thao tác local. Cần xem xét xử lý sự cố với chủ dữ liệu/chủ quy trình theo chính sách trường. |
| P0 | Tác vụ tạo câu hỏi phỏng vấn trước đây gọi provider trực tiếp, thiếu ngân sách và kiểm tra bản đã che tại thời điểm gửi. | Đã chuyển qua orchestrator có quota/ledger, preflight snapshot và kiểm tra bản đã che. Cần kiểm thử tải/chi phí bằng dữ liệu giả trước pilot. |
| P0 | Quyết định có thể dùng attestation đã cũ sau khi hồ sơ thay đổi. | Đã thêm kiểm tra generation, tài liệu hiện hành và bản đã che hiện hành tại thời điểm quyết định. |
| P0 | Bản sanitized/rubric cũ có thể bị xếp hàng đánh giá; worker dùng generation đang tải mới nên không so đúng snapshot. | Đã khóa đầu vào hiện hành khi tạo run và kiểm tra snapshot trước/sau model call. |
| P1 | Giao diện đăng nhập trước đây có SSO mô phỏng, mật khẩu demo và tuyên bố SOC2/ISO/hiệu quả chưa có chứng cứ. | Đã bỏ các mục mô phỏng, vô hiệu hóa tài khoản demo local và sửa copy. |
| P1 | Chưa có nhãn HR và IT độc lập, holdout vận hành cho một JD thực tế, hay real shadow đúng nghĩa. | Chưa thể xác nhận độ tương đồng AI–HR hoặc ký G5. Tám CV của bạn bè chỉ là bộ thử kỹ thuật và có thể không khớp cùng vị trí tuyển dụng. |
| P1 | Màn hình review hiện lộ AI trước khi HR chấm độc lập. | Cần màn nhập nhãn HR/IT riêng và khóa nhãn trước khi hiện AI; có thể tạm dùng form độc lập theo runbook. |
| P1 | Intake chưa lưu đủ nguồn CV, căn cứ được phép xử lý, phiên bản thông báo/đồng ý, phạm vi gửi provider và hạn lưu theo từng hồ sơ. | Bổ sung trước khi tiếp nhận CV thật của trường. Không nên suy từ việc tệp được upload rằng mọi mục đích xử lý đã được chấp thuận. |
| P1 | Chưa có số đo SLO, diễn tập xóa/restore/rollback đủ, HR UAT thực tế. | G6/G7 tiếp tục pending. |
| P1 | Một số handler có thể tự ghi trạng thái nghiệp vụ `failed` rồi trả về bình thường; worker tổng có thể đánh dấu Job `succeeded`. | Cần đồng bộ trạng thái Job và Assessment/InterviewDraft để dashboard vận hành và cảnh báo lỗi không báo sai. |

## Phần nên tinh giản trong MVP

- Giữ một pipeline đánh giá có schema và evidence validator; không cần thêm nhiều agent tự tranh luận cho một CV ngắn. Mỗi lượt agent thêm chi phí, thời gian và khó audit.
- Giữ `full_text_baseline` làm mặc định cho CV 1–2 trang. Chỉ bật hybrid RAG khi CV/JD dài đến mức mất bằng chứng hoặc chi phí vượt ngưỡng đã đo.
- Sandbox đào tạo, onboarding và trạng thái phê duyệt là hữu ích; loại các mô-đun demo giả hoặc chỉ số sản phẩm chưa đo. Các tình huống onboarding đang được khai báo cả frontend và backend, nên nên gom về một nguồn khi có thời gian.

## Bổ sung trước pilot thật

1. HR Owner và người chuyên môn IT ký JD/rubric/anchor/ngưỡng cho **một** vị trí thực tế; lưu ngày, phiên bản và người chịu trách nhiệm.
2. Mỗi CV thật có bản ghi nguồn, phạm vi cho phép dùng DeepSeek, thời hạn lưu, lịch sử truy cập và yêu cầu xóa. Thử rò rỉ PII bằng tập riêng, gồm số điện thoại cách nhóm, tên/trường song ngữ và các định dạng OCR khó. Bộ lọc regex chỉ là lớp hỗ trợ; người có quyền vẫn phải rà soát.
3. Thu nhãn HR/IT độc lập trước khi hiển thị AI; khóa holdout, chạy shadow trên hồ sơ ứng tuyển của cùng JD, đo MAE/kappa, coverage, tỉ lệ thiếu bằng chứng, sai dẫn chứng và sai khác theo ngôn ngữ.
4. Đo thời gian xử lý p95, lỗi OCR, lỗi provider, số lượt gọi và chi phí/CV; chạy diễn tập mất mạng, hết quota, thu hồi quyền, xóa hồ sơ và restore từ backup.
5. Chạy UAT với HR thật trên sandbox trước khi chuyển từ `shadow` sang `assisted`. Mọi kết quả AI chỉ là đề xuất; quyền quyết định phải thuộc HR.

## Giới hạn của lần rà soát

Đã thử một hồ sơ end-to-end với DeepSeek và kiểm tra local cả tám CV bằng detector hiện có; không chứng minh rằng mọi PII đã được loại bỏ. Một lần gọi trực tiếp ngoài workflow app không tạo audit log ứng dụng. Không dùng các kết quả đó để tuyên bố chất lượng chấm, fairness hoặc G1–G7 PASS. Lưu báo cáo thử nghiệm và mọi dữ liệu ứng viên thực trong private storage, không commit nội dung CV vào Git.
