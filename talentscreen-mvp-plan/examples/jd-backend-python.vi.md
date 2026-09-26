# JD mẫu — Chuyên viên phát triển phần mềm Backend Python

**Mã:** `JD-BACKEND-PYTHON-001` · **Revision:** `1` · **Ngôn ngữ:** tiếng Việt · **Trạng thái:** `draft_seed`.

Đây là JD tự soạn để phát triển và kiểm thử TalentScreen AI, không phải thông báo tuyển dụng đã được Trường đại học X phê duyệt. HR và người phụ trách kỹ thuật phải kiểm tra nhu cầu thực, chỉnh sửa và duyệt trước khi dùng cho một đợt tuyển thật. Rubric đi kèm cũng là bản nháp; không được tự phê duyệt từ seed.

## 1. Mục tiêu vị trí và bối cảnh công việc

Tham gia phát triển, bảo trì các dịch vụ backend cho hệ thống nội bộ của trường, ví dụ quản lý yêu cầu hỗ trợ, quy trình hành chính hoặc tích hợp dữ liệu nghiệp vụ. Mức công việc hướng tới junior–middle: thực hiện một tính năng thông thường trong phạm vi được giao, làm rõ yêu cầu và phối hợp với người phụ trách kỹ thuật để kiểm thử, bảo vệ dữ liệu và vận hành.

Python là ngôn ngữ chính. Kinh nghiệm với FastAPI, Django hoặc Flask đều có thể cung cấp bằng chứng phù hợp; không ưu tiên thương hiệu framework. Dữ liệu quan hệ và HTTP API là phần cốt lõi. Mô tả môi trường trường đại học nhằm làm rõ sản phẩm phục vụ, không dùng uy tín/tên tổ chức mà ứng viên từng học hoặc làm việc để chấm điểm.

Không quy định số năm kinh nghiệm cứng, bằng cấp bắt buộc, tuổi, giới tính, quê quán, ảnh, tình trạng gia đình hoặc danh tiếng cơ sở đào tạo. Không suy ra chất lượng ứng viên từ phong cách viết, độ dài CV, ngôn ngữ CV hoặc khoảng nghỉ trong lịch sử công việc.

## 2. Sáu yêu cầu năng lực được phép đánh giá

Các đoạn trích trong bảng này là nguồn chuẩn của rubric v1. Mỗi `requirement_id` ổn định trong JD revision này; thay đổi nội dung tạo JD revision mới. Trọng số là đề xuất để HR duyệt, không phải kết quả đã được xác thực.

| Requirement ID | Criterion ID / trọng số | Nội dung yêu cầu chuẩn để trích dẫn |
|---|---|---|
| `JD-PY-01` | `python_backend` /20 | Triển khai chức năng backend bằng Python từ một yêu cầu nghiệp vụ; tổ chức mã thành các phần có trách nhiệm rõ, xử lý lỗi và duy trì hành vi của chức năng khi sửa đổi. |
| `JD-API-01` | `api_design` /25 | Thiết kế và triển khai HTTP API có hợp đồng đầu vào, đầu ra và mã trạng thái phù hợp; kiểm tra dữ liệu đầu vào và xử lý lỗi để bên sử dụng API nhận được hành vi nhất quán. |
| `JD-SQL-01` | `sql_data` /20 | Làm việc với cơ sở dữ liệu quan hệ để lưu và truy vấn dữ liệu nghiệp vụ; thiết kế hoặc sửa cấu trúc dữ liệu, dùng ràng buộc và giao dịch khi cần để giữ tính đúng đắn của dữ liệu. |
| `JD-TEST-01` | `testing_debugging` /15 | Kiểm thử hành vi backend và tái hiện lỗi từ tình huống cụ thể; xác định nguyên nhân, sửa lỗi và bổ sung kiểm tra phù hợp để hạn chế lỗi tái diễn. |
| `JD-SEC-01` | `security_privacy` /10 | Áp dụng xác thực, phân quyền và bảo vệ dữ liệu trong phạm vi tính năng phụ trách; kiểm soát dữ liệu nhạy cảm trong truy cập, cấu hình và log, đồng thời xử lý các trường hợp truy cập không hợp lệ. |
| `JD-OPS-01` | `delivery_ops` /10 | Đưa thay đổi backend qua quy trình Git, kiểm tra và triển khai có kiểm soát; cấu hình môi trường, quan sát tình trạng dịch vụ và có cách xử lý khi bản triển khai gặp lỗi. |

### Hướng dẫn hiểu phạm vi yêu cầu

- **Python backend:** tìm hành động lập trình trên một chức năng cụ thể, không chỉ tên Python trong skills. Ví dụ phù hợp là triển khai xử lý yêu cầu hỗ trợ hoặc một thành phần tính toán nghiệp vụ; không yêu cầu dự án thương mại mới được tính.
- **HTTP API:** bằng chứng cần thể hiện ứng viên đã làm gì với một endpoint/tập endpoint hoặc hợp đồng API. “Biết REST” đứng riêng chưa đủ. Không mặc định API công khai Internet tốt hơn API nội bộ.
- **SQL và dữ liệu:** có thể là thiết kế bảng/quan hệ, truy vấn có mục đích, xử lý cập nhật đồng thời hoặc sửa vấn đề toàn vẹn dữ liệu. Tên PostgreSQL/MySQL/SQLite đứng riêng chưa cho thấy mức đáp ứng.
- **Kiểm thử và debug:** xem cách ứng viên mô tả một hành vi cần kiểm tra hoặc một lỗi đã xử lý. Không chấm điểm theo số lượng test, phần trăm coverage hoặc số bug nếu thiếu bối cảnh.
- **Security và privacy:** đánh giá biện pháp gắn với tính năng và ranh giới truy cập thực tế. Không yêu cầu CV công khai bí mật hệ thống, dữ liệu cá nhân hoặc chi tiết khai thác. Chứng chỉ hoặc từ khóa “JWT/OAuth” đứng riêng chưa đủ.
- **Delivery và vận hành:** chấp nhận tác vụ Git/test/deploy ở đồ án, nghiên cứu, cộng đồng hoặc công việc nếu có mô tả phần việc. Không bắt buộc cloud trả phí, Kubernetes hay hạ tầng quy mô lớn.

## 3. Bằng chứng ứng viên có thể cung cấp trong CV

Ứng viên có thể mô tả kinh nghiệm làm việc, dự án cá nhân, đồ án môn học, dự án nhóm, hoạt động nghiên cứu hoặc cộng đồng. Các nguồn này được xét theo cùng tiêu chí; không ưu tiên việc có lương, doanh nghiệp nổi tiếng hoặc một cơ sở đào tạo cụ thể.

Mỗi ví dụ nên cho biết **bối cảnh/tác vụ, hành động cá nhân đã thực hiện và chức năng hoặc cách kiểm chứng kết quả**. Không bắt buộc số liệu định lượng, độ dài mô tả, danh sách công nghệ dài hoặc cách trình bày chuyên nghiệp. Kết quả định lượng nếu có chỉ giúp hiểu tác vụ; không tự tạo điểm thưởng.

Trong dự án nhóm, cần phân biệt phần đóng góp của ứng viên với kết quả chung. “Nhóm phát triển hệ thống X” không đủ để suy ra ứng viên trực tiếp thiết kế API, quản lý dữ liệu hoặc chịu trách nhiệm vận hành. Hệ thống sẽ đánh dấu cần làm rõ nếu phần việc không xác định được.

CV có thể bằng tiếng Việt, tiếng Anh hoặc song ngữ. Tên thư viện, giao thức và thuật ngữ kỹ thuật có thể giữ nguyên. Ngôn ngữ dùng để viết CV không là tiêu chí đánh giá ngoại ngữ. Mô tả cùng một tác vụ bằng hai ngôn ngữ không được tính thành hai thành tích.

MVP chỉ đánh giá nội dung có trong file CV đã được HR kiểm tra; URL portfolio hoặc repository chỉ là văn bản tham chiếu, hệ thống không tự truy cập hoặc lấy nội dung ngoài. Nếu HR cần nguồn bổ sung, tiếp nhận bằng phiên bản tài liệu được quản lý và review lại.

## 4. Quy trình tuyển chọn liên quan đến TalentScreen AI

AI đề xuất bảng đối chiếu theo sáu tiêu chí cùng nguồn CV/JD. Thiếu mô tả hoặc thông tin mâu thuẫn dẫn đến yêu cầu làm rõ, không mặc định là không đạt. Điểm0 chỉ được dùng khi nguồn nói rõ tình trạng tương ứng anchor0; vắng thông tin không phải bằng chứng cho điểm0.

HR kiểm tra nguồn, có thể điều chỉnh nhận định có lý do và chịu trách nhiệm quyết định vào vòng tiếp theo. Phỏng vấn dùng một số câu hỏi cốt lõi theo JD, cộng câu hỏi làm rõ phần đóng góp hoặc bằng chứng chưa đủ. AI không gửi thông báo, không tự loại và không tự chuyển vòng.

Ngưỡng thử nghiệm trong rubric seed là comparable score≥70 và ba tiêu chí `python_backend`, `api_design`, `sql_data` mỗi tiêu chí≥2 khi đủ bằng chứng toàn bộ sáu tiêu chí. Đây chỉ là rule đề xuất draft cần HR duyệt; nó không thay thế đánh giá của người tuyển dụng và chưa có chứng cứ dự báo hiệu quả công việc.

Cả sáu tiêu chí đạt mức2 cho tổng50, mức3 cho tổng75. Vì mức2 mô tả thực hiện chức năng thông thường, HR/IT phải kiểm tra xem ngưỡng70 có phù hợp với mức junior–middle thực tế hay không. Trạng thái `review_required` yêu cầu người tuyển dụng xem xét, không mang nghĩa ứng viên bị loại hoặc không đủ năng lực.

## 5. Các thông tin phải được HR bổ sung trước khi công bố tuyển dụng thật

Đơn vị quản lý, người phụ trách chuyên môn, nhiệm vụ hệ thống thực tế, điều kiện làm việc, địa điểm/chế độ làm việc, hình thức hợp đồng, đãi ngộ, thời gian nhận hồ sơ và đầu mối liên hệ chưa được xác nhận. Những trường này không được AI tự điền bằng dữ kiện giả. Nhu cầu bổ sung năng lực hoặc ngôn ngữ nếu có phải sửa JD/rubric và được duyệt trước khi đánh giá ứng viên.

HR/IT xác nhận sáu yêu cầu có liên quan trực tiếp đến vị trí, mô tả anchor có thể áp dụng nhất quán và ngưỡng đề xuất có ý nghĩa trong đợt thực. Nếu chưa xác nhận, JD/rubric giữ `draft_seed` và chỉ được dùng ở sandbox.
