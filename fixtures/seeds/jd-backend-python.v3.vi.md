# JD mẫu — Chuyên viên phát triển phần mềm Backend Python

**Mã:** `JD-BACKEND-PYTHON-001` · **Revision:** `3` · **Ngôn ngữ:** tiếng Việt · **Trạng thái:** `draft_unapproved`.

**Nguồn quyết định chưa xác minh:** trong worktree hiện không có biên bản quyết định chung HR–IT ngày 09/10/2026 hoặc tài liệu tương đương để xác thực các lựa chọn của v3. V3 là bản nháp do AI tổng hợp từ JD/rubric v2, báo cáo AI-simulated review và các giả định được đề xuất trong quá trình soạn; không được coi các nội dung dưới đây là quyết định của HR–IT. Theo mô tả của người yêu cầu về nhận xét độc lập HR/IT, threshold 50–55 còn chờ họp, trọng số là các khoảng và stack chưa xác nhận; bản nhận xét nguồn chưa có trong worktree để đối chiếu nguyên văn. File này vẫn `draft_unapproved`; chỉ dùng sandbox, không công bố hoặc dùng để sàng lọc ứng viên thật.

## 1. Vị trí và công việc

**Đề xuất AI chưa xác nhận:** Junior cứng (1–2 năm kinh nghiệm thực tế) đến Middle (2–3 năm kinh nghiệm thực tế). Đây không phải cấp độ đã được HR–IT thống nhất; HR/IT cần xác nhận cấp độ, phạm vi tự chủ và việc có nên nêu số năm hay không. Không dùng số năm làm điều kiện loại tự động.

**Mô tả nhiệm vụ đề xuất, chưa xác nhận:** tiếp nhận đặc tả nghiệp vụ để xây dựng API/dịch vụ backend cho hệ thống nội bộ; các ví dụ quản lý văn bản, đăng ký hỗ trợ và quản lý sinh viên chỉ là minh họa do AI soạn, không phải hệ thống hoặc nhiệm vụ đã xác nhận. Python, PostgreSQL, migration, tối ưu truy vấn, phối hợp frontend, Docker và Git cũng chưa được xác nhận là yêu cầu công việc thực tế. HR/IT phải thay bằng nhiệm vụ, dữ liệu, môi trường triển khai và stack thực tế trước khi công bố.

**Chế độ làm việc và hình thức kiểm tra vòng 2 chưa xác nhận.** Onsite/hybrid, take-home trong 48 giờ hay phỏng vấn/live-coding 45 phút là các phương án AI nêu ra để thảo luận; chưa có nguồn trong worktree xác nhận đây là lựa chọn của đơn vị hoặc Ban Giám hiệu, cũng chưa có căn cứ cho thời hạn phải chốt trước ngày mở hồ sơ ba ngày làm việc. HR/đơn vị tuyển dụng cần cung cấp thông tin thật.

## 2. Tiêu chí dùng ở vòng CV

**Phân loại và cách tính dưới đây là đề xuất AI chưa được HR–IT quyết định.** Bản nháp hiện đặt `python_backend`, `api_design`, `sql_data` là must-have và `testing_debugging`, `security_privacy`, `delivery_ops` là nice-to-have; cấu hình hiện tại vẫn gán trọng số cho cả sáu. Chưa rõ nice-to-have là điểm cộng không phạt khi evidence yếu/thiếu, hay vẫn là tiêu chí có trọng số khi có evidence. Cần HR–IT chốt trước khi dùng rubric.

| Requirement ID | Criterion ID / trọng số đề xuất AI | Nội dung draft để HR/IT đối chiếu, chưa phải yêu cầu công việc đã xác nhận |
|---|---|---|
| `JD-PY-03` | `python_backend` /25 | Trực tiếp lập trình chức năng backend bằng Python; tổ chức mã nguồn phân tách rõ tầng controller/router và service nghiệp vụ; xử lý ngoại lệ và mã lỗi có kiểm soát. |
| `JD-API-03` | `api_design` /25 | Trực tiếp thiết kế và triển khai API HTTP/RESTful có hợp đồng request/response rõ ràng; validate dữ liệu đầu vào; trả mã trạng thái HTTP phù hợp và format JSON lỗi nhất quán. |
| `JD-SQL-03` | `sql_data` /20 | Làm việc với RDBMS PostgreSQL hoặc MySQL; thiết kế bảng có khóa chính/khóa ngoại; viết truy vấn quan hệ (JOIN, GROUP BY); dùng transaction bảo đảm toàn vẹn khi có nhiều thao tác ghi đồng thời. |
| `JD-TEST-03` | `testing_debugging` /15 | Viết automated test bằng pytest/unittest hoặc tái hiện bug và viết regression test ngăn lỗi tái phát. |
| `JD-SEC-03` | `security_privacy` /10 | Áp dụng xác thực JWT/Session, RBAC; quản lý secret qua biến môi trường; không để lộ dữ liệu nhạy cảm trong log. |
| `JD-OPS-03` | `delivery_ops` /5 | Sử dụng Git trong làm việc nhóm; biết viết Dockerfile và docker-compose để chạy local/staging. |

Không chấm tuổi, giới tính, quê quán, ảnh, tình trạng gia đình, tên/danh tiếng trường, ngôn ngữ, độ dài CV, khoảng nghỉ, số năm đứng riêng, chức danh, tên framework/database đứng riêng hoặc thành tích của cả nhóm khi chưa rõ đóng góp cá nhân. Thiếu thông tin không phải score 0.

## 3. Quy tắc scoring và recommendation

**Cấu hình đang có trong seed, chỉ là đề xuất AI chưa xác nhận:** trọng số 25/25/20/15/10/5 (tổng 100%), threshold 50/100 và floor 2/4 cho ba must-have. Không có nguồn HR–IT xác thực các giá trị chính xác này; mô tả người yêu cầu về nhận xét độc lập nêu threshold 50–55 và trọng số theo khoảng. Không diễn giải 50 hay các floor là quyết định đã chốt. Nếu được giữ sau hiệu chuẩn, các giá trị chỉ hỗ trợ HR/IT xem xét, không tự động từ chối hoặc quyết định tuyển dụng.

Các mô tả anchor 0–4 và điều kiện bằng chứng chi tiết trong rubric v3 là nội dung AI soạn để HR/IT rà soát, chưa được xác nhận là tiêu chuẩn công việc.

Đề xuất AI cho testing/debugging: test tự động cơ bản **hoặc** quy trình tái hiện bug rõ ràng đạt anchor 2; anchor 3 là điểm cộng xuất sắc, không bắt buộc. HR/IT chưa xác nhận mức phân biệt này.

Đề xuất AI về anchor 0: chỉ dùng nếu ứng viên nói rõ trong hồ sơ là chưa từng thực hiện năng lực tương ứng, phạm vi câu nói đủ rộng cho tiêu chí và không có evidence tích cực mâu thuẫn cùng phạm vi. CV không nhắc đến năng lực là `insufficient_evidence`, score `null`, không phải 0. HR/IT cần xác nhận cách áp dụng trước khi dùng thật.

**Giả định xử lý đang mô tả trong seed, chưa được HR–IT xác nhận:** khi thiếu evidence ở nice-to-have, rubric hiện dùng score `null`, hiển thị cần làm rõ và cho phép tính điểm chuẩn hóa trên tiêu chí có evidence. Cách tính khi evidence yếu nhưng có một phần, việc nice-to-have có được tính trọng số hay chỉ là điểm cộng, và việc thiếu evidence có nên ảnh hưởng recommendation vẫn cần quyết định HR–IT.

Nếu thiếu evidence ở must-have, seed hiện đề xuất score `null`, yêu cầu HR làm rõ và không tạo comparable score; đây chưa phải quy trình đã được HR–IT thông qua. Chưa chốt criterion cần hỏi, kênh liên hệ, mốc 24–48 giờ là hạn gửi yêu cầu hay hạn chờ phản hồi, và bằng chứng/log nào đủ để ghi nhận “không phản hồi”. Không ghi nhận không phản hồi hoặc từ chối ứng viên chỉ từ cấu hình nháp này.

Không tìm thấy nguồn HR–IT xác thực quy định cách xử lý hai phát biểu CV mâu thuẫn nhau. V3 giữ `conflicting_evidence`, score `null`, chờ HR xác minh như một lựa chọn thiết kế đang có trong seed; đây không phải quyết định chính sách đã được thông qua. Không gộp trạng thái này với thiếu bằng chứng hoặc score 0.

## 4. Stack và nội dung kỹ thuật chưa xác nhận

Không tìm thấy biên bản trong worktree để xác nhận Python 3.10+, PostgreSQL/MySQL/MariaDB, FastAPI/Django/Flask, Git hoặc Docker. V2 chỉ mô tả Python là ngôn ngữ chính, chấp nhận FastAPI/Django/Flask và nói chung về dữ liệu quan hệ; chính v2 cũng là draft. Các công nghệ cụ thể trong v3 là nội dung đề xuất/minh họa do AI soạn, không phải stack tuyển dụng đã xác nhận. HR/IT cần chỉ rõ công nghệ nào thực sự bắt buộc, ưu tiên, tương đương hoặc chỉ là ví dụ.

Do stack và phân loại must/nice chưa được xác nhận, không dùng tên framework, database, Git hay Docker để cộng/trừ điểm hoặc loại ứng viên ngoài policy đã được phê duyệt. Câu này là biện pháp thận trọng cho sandbox, không xác nhận rằng các công nghệ nêu trên thuộc JD thực tế. Các công nghệ khác cũng chưa được xác định là yêu cầu.

## 5. Cổng công bố và thông tin còn thiếu

**Cổng công bố: BLOCKED — draft/unapproved.** Trước khi công bố, HR/đơn vị có thẩm quyền phải xác nhận và cung cấp đơn vị/đầu mối, địa điểm, work mode, loại hợp đồng, đãi ngộ, thời gian và cách nhận hồ sơ, thông báo xử lý dữ liệu ứng viên. HR–IT phải xác nhận nhiệm vụ, cấp độ, công nghệ/môi trường nào thuộc yêu cầu thực tế và chọn hình thức vòng 2. Không tự điền các mục này bằng giả định.

## Lịch sử bản nháp

- Revision 3: bản nháp AI tổng hợp để rà soát nguồn; chưa tìm thấy biên bản quyết định chung HR–IT trong worktree. Phân loại, trọng số, threshold, floors, xử lý thiếu evidence, cấp độ/nhiệm vụ và stack đều cần xác minh; approval fields để trống, không phê duyệt.
