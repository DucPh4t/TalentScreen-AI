# Workflow tuyển dụng: sàng lọc → phỏng vấn

Hệ thống hỗ trợ tuyển dụng theo JD do người dùng nhập. AI cung cấp đánh giá tham khảo có bằng chứng; người có quyền Owner của đợt ghi kết luận. Quyền quản trị tài khoản không thay thế quyền thành viên của đợt tuyển dụng.

## 1. Chuẩn bị đợt tuyển dụng

1. Tạo đợt, nhập JD của vị trí cần tuyển. Không giới hạn vào Backend Python.
2. Cho phép gửi JD ra nhà cung cấp nếu dùng gợi ý AI; tạo và chỉnh rubric theo JD. Rubric động có 2–12 tiêu chí, trọng số và neo điểm 0–4.
3. Duyệt rubric hiện hành rồi mở nhận hồ sơ. Khi đổi JD, cần rubric đã duyệt theo JD mới; rubric/điểm cũ không được dùng như căn cứ hiện hành.
4. Thêm thành viên HR/người chuyên môn và phân quyền trong đợt.

## 2. Tiếp nhận và rà soát CV

Upload PDF/DOCX từ tab Hồ sơ của đợt đang nhận hồ sơ. Sau khi trích xuất, HR kiểm tra bản đã che định danh trước khi duyệt. Việc duyệt CV/rubric xếp job đánh giá đủ điều kiện vào hàng đợi; cần backend và worker đang chạy.

Trong hồ sơ ứng viên, đọc CV đã che, đối chiếu từng tiêu chí với trích dẫn ở **Đánh giá và bằng chứng**. RAG tìm phần CV liên quan theo tiêu chí; model đánh giá từ bằng chứng được cung cấp và output được kiểm tra. Không có bằng chứng được ghi là chưa đủ thông tin, không tự đổi thành 0 điểm. Ghi nhận tiêu chí đã rà soát được lưu riêng theo người dùng và nguồn hiện hành.

Nếu HR sửa đánh giá, phiên bản sửa đã chốt và còn hiện hành trở thành căn cứ hiệu lực. Điểm CV/AI và điểm quan sát trong phỏng vấn được giữ riêng.

## 3. Kết luận sàng lọc

Ở **Kết luận sàng lọc**, chọn một trong ba kết quả:

| Kết quả | Công việc tiếp theo |
| --- | --- |
| Mời phỏng vấn | Lập kế hoạch và chuẩn bị câu hỏi. |
| Yêu cầu bổ sung | Hồ sơ vẫn nằm ở trạng thái chờ ứng viên bổ sung; theo dõi và cập nhật căn cứ trước khi chốt lại. |
| Không tiếp tục | Lưu căn cứ và chuẩn bị phản hồi nếu cần. |

Nhập một lý do dựa trên năng lực và xác nhận một lần sau khi đã rà soát các tiêu chí. Server lưu xác nhận và quyết định trong cùng giao dịch. Nếu trái với khuyến nghị AI, lý do này cũng là căn cứ override. Kết luận mới thay thế kết luận cũ nhưng giữ lịch sử; nguồn/phiên bản thay đổi sẽ bị từ chối để tránh ghi đè.

Đây là kết luận sàng lọc, chưa phải quyết định tuyển hoặc offer. Thư phản hồi là template có chỉnh sửa và người duyệt, chưa gửi email tự động.

## 4. Phỏng vấn: Chuẩn bị / Ghi nhận / Tổng hợp

### Chuẩn bị

- Chọn lượt, đặt tên buổi trao đổi, thời gian theo múi giờ thiết bị, thời lượng, hình thức và thông tin tham gia thực tế.
- Chọn năng lực trọng tâm và người phỏng vấn là thành viên đang hoạt động của đợt; lưu kế hoạch trước khi ghi phiếu.
- Tạo câu hỏi gợi ý từ căn cứ hiện hành. Có thể sửa/bỏ câu hỏi làm rõ, nhập lý do để lưu phiên bản mới. Câu hỏi chung tùy thuộc ngân hàng câu hỏi được cấu hình; ngân hàng này là tùy chọn.
- Duyệt thư mời cần lịch và link/địa điểm/số liên hệ dùng được. Những nội dung như TBD, “sẽ gửi sau” hay placeholder chưa được coi là hoàn tất.

### Ghi nhận

Mỗi người được phân công ghi câu trả lời và điểm quan sát của mình. Lưu nháp hoặc **lưu và nộp** trong một thao tác. Tiêu chí trọng tâm cần điểm có quan sát hoặc giải thích rõ vì sao chưa quan sát được; tiêu chí chưa quan sát giữ điểm trống.

Owner đang tham gia phỏng vấn chỉ thấy phiếu người khác sau khi nộp phiếu của mình. Reviewer không có quyền chốt kết luận hội đồng. Khi đã ghi phiếu, trọng tâm/hội đồng của lượt được giữ cố định.

Sửa phiếu đã nộp dùng thao tác sửa có lý do, giữ phiên bản cũ. Nếu hai cửa sổ cùng sửa, phiên bản cũ nhận lỗi xung đột; tải lại, đối chiếu và chủ động áp dụng lại thay đổi. Refresh không được âm thầm đổi token rồi ghi đè nội dung người khác.

### Tổng hợp

Owner xem các điểm quan sát theo năng lực và những chênh lệch cần đối chiếu. Hệ thống không tự trộn điểm AI với điểm phỏng vấn để ra kết quả tuyển dụng.

Khi tất cả người được phân công đã nộp phiếu hiện hành, Owner ghi một trong bốn kết luận: tiếp tục vòng sau, cần thêm bằng chứng, không tiếp tục, hoặc **đề xuất tuyển**. Kết luận lưu người chốt, lý do, thời gian và các phiên bản phiếu làm căn cứ. Đề xuất tuyển chưa tạo offer và không tự gửi thông báo.

## 5. Khi dữ liệu hoặc ý kiến thay đổi

Đổi CV/JD/rubric làm các căn cứ liên quan thành cũ. Bộ câu hỏi cũng được đánh dấu cũ khi kết quả AI hoặc bản sửa HR hiệu lực thay đổi. Lượt có phiếu theo nguồn cũ được giữ để kiểm toán; cần mở lượt mới theo nguồn hiện hành.

Sửa phiếu sau kết luận khiến kết luận cần rà soát lại. Đổi quyết định/kế hoạch/kết luận hoặc sửa phiếu vô hiệu hóa thư phản hồi liên quan. Việc tạo kế hoạch tương lai không làm mất trạng thái đang chờ bổ sung hoặc không tiếp tục.

Phiếu cũ chưa có snapshot JD được coi là căn cứ cũ theo hướng thận trọng. Yêu cầu xóa hồ sơ xử lý cả tiến độ rà soát, kế hoạch, kết luận và lịch sử phiếu trong phạm vi hồ sơ.

## Phạm vi xác minh

Bản này đã được kiểm thử workflow, phân quyền, nguồn cũ, xung đột phiên bản, migration và responsive trên dữ liệu synthetic; xem [ledger](reviews/2026-10-08-hr-interview-workflow-b.md). Chưa có xác nhận chất lượng model trên holdout HR/IT độc lập, gửi email, đồng bộ lịch hoặc phát hành offer. Kết quả test không phải xác nhận hệ thống thay thế HR hay đủ điều kiện đưa ra quyết định tự động trên người thật.
