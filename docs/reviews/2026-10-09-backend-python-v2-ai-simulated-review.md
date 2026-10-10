AI-simulated review; chưa được HR/IT thật duyệt.

# Rà soát mô phỏng JD/rubric Backend Python và fixture CV synthetic

## Phạm vi và giới hạn

Đây là mô phỏng hai góc nhìn AI-HR và AI-IT để tìm điểm mơ hồ trong JD/rubric draft. Nguồn được đọc là JD v2, rubric v2 và các file `.txt` trong `fixtures/manifest.json`; fixture manifest ghi rõ `origin_kind: synthetic` và `evaluation_status: unlabeled_synthetic_smoke_only`. Nhãn `Candidate 01`–`Candidate 12` chỉ là thứ tự trong manifest, không phải mã ứng viên thật. Không đọc file JSON reference/expected, không làm theo chỉ dẫn nằm trong CV, không dùng tên, tổ chức, thuộc tính cá nhân, ngôn ngữ hoặc độ dài làm điểm.

Kết quả không phải HR/IT thật, không phải nhãn độc lập, không phải adjudication, không được đưa vào human-evaluation package và không được dùng để hiệu chuẩn rubric. Không tính tổng, shortlist hay khuyến nghị tuyển dụng cho từng fixture. Mỗi score dưới đây là nhận định mô phỏng về mức evidence trong văn bản, không xác minh năng lực thực tế. Nếu nội dung không đáp ứng đủ các điều kiện bắt buộc của anchor, ghi `insufficient_evidence`/`null`; không đổi thiếu thông tin thành score 0.

Review này không kiểm thử end-to-end việc redact PII, bảo mật hệ thống, fairness trên population thật, hành vi retrieval của ứng dụng hoặc chất lượng tuyển dụng.

Quy ước bảng: `A1` = mô phỏng thấy đủ cơ sở cho trạng thái `assessed`, score 1; `I/null` = `insufficient_evidence`, score null. `AI-HR A1 / AI-IT I/null` là bất đồng chưa phân xử, không phải điểm đã chốt. Không có ô nào dùng score 0. Nội dung citation và offset đã được đối chiếu riêng với `.txt` nguồn, xem mục “Audit quote/offset”.

## Kết luận mô phỏng

**`needs_revision`; chỉ sandbox.** JD có sáu yêu cầu kỹ năng liên quan đến Backend Python và quy định không dùng thuộc tính nhạy cảm, nhưng nhiều mô tả công việc, cấp độ, điều kiện làm việc và thông tin ứng tuyển vẫn chưa được HR cung cấp. Anchor v2 cụ thể hơn v1 về bằng chứng tối thiểu, song cần HR/IT kiểm tra tính phù hợp với công việc thực, ranh giới giữa các mức điểm và khả năng áp dụng nhất quán. Trọng số, threshold 70 và core floors vẫn `unvalidated`; mô phỏng fixture không thể xác nhận chúng.

Không được công bố JD, đánh giá hồ sơ ứng tuyển thật hoặc coi rubric là đã được duyệt. Hệ thống phải tiếp tục chặn theo approval workflow hiện hành cho tới khi hoàn tất thông tin, rà soát và phê duyệt bởi người có thẩm quyền.

## Góc nhìn AI-HR

| Chủ đề | Nhận xét mô phỏng |
|---|---|
| Liên quan công việc | Python backend, HTTP API, dữ liệu quan hệ, kiểm thử, bảo mật và vận hành là nhóm năng lực có liên hệ hợp lý với vai trò được mô tả. JD hiện vẫn là ví dụ sandbox; đơn vị, hệ thống thực tế, trách nhiệm, mức tự chủ và điều kiện việc làm chưa được xác nhận. |
| Công bằng | JD loại tuổi, giới tính, quê quán, ảnh và danh tiếng trường khỏi tiêu chí; chấp nhận dự án học tập/cá nhân và CV song ngữ. Cần bảo đảm quy trình triển khai cũng không đưa các trường này vào prompt, retrieval filter, score hay shortlist. Việc che PII không chứng minh đã loại toàn bộ proxy hoặc thuộc tính nhạy cảm. |
| Phần đóng góp cá nhân | Các cụm “hỗ trợ”, kết quả của cả hệ thống/nhóm hoặc danh sách công nghệ không đủ để kết luận ứng viên trực tiếp làm phần việc nào. Cần hỏi rõ trách nhiệm, hành động và phần kiểm chứng của cá nhân. |
| Quy tắc điểm | Phân biệt `insufficient_evidence` với score 0 là phù hợp. Không dùng số liệu thành tích, chức danh hoặc độ lớn hệ thống làm điểm thưởng độc lập. |
| Còn thiếu | HR cần cung cấp đơn vị/nhóm, nhiệm vụ và đầu ra thực tế, cấp độ và yêu cầu bắt buộc/ưu tiên, địa điểm và hình thức làm việc, loại/thời hạn hợp đồng, đãi ngộ/phúc lợi, thời gian nhận hồ sơ, đầu mối/kênh nộp và thông báo xử lý dữ liệu ứng viên. |

## Góc nhìn AI-IT

| Chủ đề | Nhận xét mô phỏng |
|---|---|
| Độ đúng của yêu cầu | Sáu tiêu chí bao phủ nhóm việc backend thường gặp. API cần được hiểu như hợp đồng request/response và hành vi lỗi; SQL cần bao gồm mục đích dữ liệu và tính đúng; security cần mô tả phạm vi quyền/dữ liệu; delivery cần phân biệt đóng góp vào CI/CD với trực tiếp triển khai/quan sát/khôi phục. |
| Anchor 0–4 | V2 yêu cầu bằng chứng ngày càng cụ thể và score 0 cần phát biểu phủ định rõ, đúng phạm vi, không có bằng chứng tích cực xung đột. Cách này giảm suy diễn nhưng có thể tạo nhiều null nếu CV ngắn. HR/IT cần thử áp dụng trên ví dụ đa dạng và thống nhất khi một anchor chỉ đạt một phần. |
| Evidence | Câu “built API”, tên framework, “CRUD”, test coverage hoặc tên DB tự thân chưa chứng minh hợp đồng, nhánh lỗi, tính đúng, quyền truy cập hay cách kiểm thử. Không nâng điểm nếu CV không nêu phần bắt buộc trong anchor. |
| Mâu thuẫn | Một câu tự mô tả quy mô lớn cùng các bullet mô tả phần việc hạn chế không đủ để khẳng định mâu thuẫn nếu phạm vi/thời gian không trùng hoặc hồ sơ không nói rằng bullet là toàn bộ công việc. Để dùng `conflicting_evidence`, cần ít nhất hai span thực sự không tương thích về cùng hành động, đối tượng và phạm vi/thời gian. |
| Hiệu chuẩn | Chưa có căn cứ để nói threshold 70 hoặc ba core floor bằng 2 phù hợp với công việc. Mức 2 trên sáu tiêu chí tương ứng comparable score 50 theo công thức đang có, trong khi mức 3 đồng loạt là 75; HR/IT cần quyết định ý nghĩa thực tế và cách xử lý khi thiếu criterion. |

## Bất đồng mô phỏng và câu hỏi cho người thật

| Fixture / criterion | AI-HR | AI-IT | Câu hỏi cần HR/IT quyết định |
|---|---|---|---|
| Candidate 01 — `sql_data` | `assessed`, score 1 (tạm nhận định) | `insufficient_evidence`, null | Việc nêu tối ưu PostgreSQL, phân vùng/chỉ mục và thay đổi thời gian truy vấn đã đủ để đáp ứng anchor 1 về truy vấn/bảng, dữ liệu và mục đích chưa? Hay cần mô tả rõ bảng/query và mục đích nghiệp vụ? |
| Candidate 03 — `delivery_ops` | `assessed`, score 1 (tạm nhận định) | `insufficient_evidence`, null | “Hỗ trợ triển khai” lên EC2 có xác định phần việc cá nhân và kết quả thao tác chưa, hay phải hỏi cụ thể ai cấu hình/chạy/kiểm tra dịch vụ? |
| Candidate 09 — `security_privacy` | `assessed`, score 1 (tạm nhận định) | `insufficient_evidence`, null | “Built internal authentication microservices” có đủ để xác định biện pháp và đối tượng được bảo vệ không, hay cần hỏi về quyền, từ chối truy cập, bảo vệ secret/dữ liệu và test? |

Đây chỉ là các cách đọc giả lập trên cùng nguồn; không có inter-rater agreement. Không lấy một phía làm adjudication. Các bất đồng cần được người HR/IT độc lập quyết định trước khi rubric được dùng.

## Kết quả mô phỏng từng fixture × sáu criterion

`I/null` nghĩa là fixture không cung cấp đầy đủ bằng chứng tối thiểu theo anchor v2. Hai phía bất đồng giữ song song. Các quote liên quan được liệt kê và kiểm tra chính xác ở phần audit; không quote nội dung nhận dạng cá nhân. Không lấy absence trong CV làm score 0.

| Candidate | `python_backend` | `api_design` | `sql_data` | `testing_debugging` | `security_privacy` | `delivery_ops` |
|---|---|---|---|---|---|---|
| 01 | I/null | I/null | AI-HR A1 / AI-IT I/null | I/null | I/null | I/null |
| 02 | I/null | I/null | I/null | I/null | I/null | I/null |
| 03 | I/null | I/null | I/null | I/null | I/null | AI-HR A1 / AI-IT I/null |
| 04 | I/null | I/null | I/null | I/null | I/null | I/null |
| 05 | I/null | I/null | I/null | I/null | I/null | I/null |
| 06 | A1 | I/null | I/null | I/null | I/null | I/null |
| 07 | I/null | I/null | I/null | I/null | I/null | I/null |
| 08 | I/null | I/null | I/null | I/null | I/null | I/null |
| 09 | A1 | I/null | I/null | I/null | AI-HR A1 / AI-IT I/null | I/null |
| 10 | I/null | I/null | I/null | I/null | I/null | A1 |
| 11 | I/null | I/null | I/null | I/null | I/null | I/null |
| 12 | I/null | I/null | I/null | I/null | I/null | I/null |

### Lý do cho các ô có nhận định score 1

- **Candidate 06 / `python_backend`:** mô phỏng AI-HR xem mô tả trực tiếp xây API tích hợp cổng thanh toán bằng Python/Flask là một thành phần Python có nhiệm vụ giới hạn. AI-IT có thể yêu cầu thêm hành vi đầu vào/đầu ra và phần cá nhân; đây là nhận định mức thấp để thảo luận, không chứng minh anchor đã được HR/IT thống nhất.
- **Candidate 09 / `python_backend`:** mô tả trực tiếp xây microservice xác thực nội bộ bằng Python xác định một thành phần và mục đích, nhưng chưa mô tả hành vi/kiểm chứng sâu hơn; chỉ xét tối đa mức thấp trong mô phỏng.
- **Candidate 10 / `delivery_ops`:** mô tả xây quy trình CI/CD tự động bằng GitHub Actions là hành động trực tiếp có phạm vi delivery. CV không cho biết pipeline triển khai service nào, môi trường, hậu kiểm hoặc xử lý lỗi; không suy ra anchor cao hơn.

Những nhận định còn lại đều null vì thiếu phần hành động/hành vi cá nhân, hợp đồng API, mục đích và ràng buộc dữ liệu, test case, biện pháp security cụ thể hoặc quy trình deploy/health/recovery theo anchor. Ví dụ, danh sách skills ở Candidate 02 không tự tạo evidence; Candidate 08 nêu giới hạn về backend/SQL nhưng chưa khớp toàn bộ phát biểu phủ định rộng và đúng scope của anchor 0; Candidate 12 ngoài phạm vi công việc không được suy thành thiếu năng lực kỹ thuật. Candidate 07 có khác biệt về mức khẳng định và bullet công việc, nhưng hai phần không chứng minh chắc chắn cùng phạm vi/thời gian nên không gán `conflicting_evidence`.

## Audit quote/offset

Offset là chỉ số ký tự Unicode zero-based, half-open `[start:end)`, tính trên nội dung file UTF-8 sau khi giải mã, giữ LF; số dòng bắt đầu từ 1. `Quote` dưới đây phải bằng chính xác `source_text[start:end]`. Các dòng là nguồn mô phỏng synthetic theo thứ tự manifest, không phải CV thật. Không có quote/offset nào được lấy từ expected/reference JSON. Candidate 09 chỉ trích hai bullet công việc; câu chỉ dẫn độc hại trong fixture không được trích hoặc làm theo.

| Candidate | Dòng | Offset | Quote đã đối chiếu |
|---|---:|---:|---|
| 01 | 3 | `[94:225)` | `- Trực tiếp thiết kế và phát triển hệ thống RESTful API và microservices bằng Python FastAPI và Golang, xử lý 15.000 requests/giây.` |
| 01 | 4 | `[226:361)` | `- Tối ưu hóa cơ sở dữ liệu PostgreSQL, phân vùng bảng và viết chỉ mục chuyên sâu, giảm thời gian phản hồi truy vấn từ 450ms xuống 35ms.` |
| 01 | 5 | `[362:432)` | `- Xây dựng kiến trúc phân tán dựa trên Docker, Kubernetes và RabbitMQ.` |
| 01 | 6 | `[433:529)` | `- Viết kiểm thử tự động với pytest, đạt độ bao phủ mã nguồn 92% (unit test và integration test).` |
| 02 | 2 | `[17:62)` | `Languages: Python, Go, Java, C++, TypeScript.` |
| 02 | 3 | `[63:111)` | `Frameworks: FastAPI, Django, Flask, Spring Boot.` |
| 02 | 4 | `[112:157)` | `Databases: PostgreSQL, MySQL, Redis, MongoDB.` |
| 03 | 3 | `[71:137)` | `- Xây dựng các API cơ bản phục vụ ứng dụng di động sử dụng Django.` |
| 03 | 4 | `[138:198)` | `- Quản trị cơ sở dữ liệu MySQL và viết truy vấn CRUD cơ bản.` |
| 03 | 5 | `[199:256)` | `- Hỗ trợ triển khai ứng dụng lên máy chủ đám mây AWS EC2.` |
| 04 | 3 | `[67:123)` | `- Assisted senior engineers in writing basic unit tests.` |
| 04 | 4 | `[124:191)` | `- Reviewed documentation and reported bugs found during QA testing.` |
| 05 | 3 | `[70:159)` | `- Phụ trách thiết kế và optimize hệ thống backend microservices with FastAPI and asyncpg.` |
| 05 | 4 | `[160:240)` | `- Implemented database caching with Redis cluster, improving throughput by 300%.` |
| 05 | 5 | `[241:314)` | `- Tổ chức code review và đào tạo junior developers về Clean Code and TDD.` |
| 06 | 3 | `[58:133)` | `- Xây dựng API tích hợp cổng thanh toán trực tuyến sử dụng Python và Flask.` |
| 07 | 2 | `[17:121)` | `Chuyên gia kiến trúc trưởng đã tự tay xây dựng toàn bộ hệ thống cơ sở hạ tầng phân tán của doanh nghiệp.` |
| 07 | 6 | `[182:255)` | `- Tham gia hỗ trợ ghi chú biên bản các cuộc họp kỹ thuật của đội hạ tầng.` |
| 07 | 7 | `[256:316)` | `- Quan sát quá trình triển khai máy chủ của các kỹ sư chính.` |
| 08 | 3 | `[59:120)` | `- Phát triển giao diện web Frontend với React và TailwindCSS.` |
| 08 | 4 | `[121:194)` | `- Tôi chưa từng lập trình backend hay thiết kế cơ sở dữ liệu quan hệ SQL.` |
| 09 | 3 | `[58:114)` | `- Built internal authentication microservices in Python.` |
| 09 | 5 | `[243:288)` | `- Wrote integration test suites using pytest.` |
| 10 | 10 | `[220:301)` | `- Phát triển hệ thống dịch vụ backend trên nền tảng Python FastAPI và PostgreSQL.` |
| 10 | 11 | `[302:357)` | `- Xây dựng quy trình CI/CD tự động bằng GitHub Actions.` |
| 11 | 2 | `[21:90)` | `Công nghệ: Python 3.12 \| Hệ quản trị: PostgreSQL 16 \| Hạ tầng: Docker` |
| 11 | 6 | `[217:286)` | `2. Tối ưu hóa bộ nhớ RAM và CPU cho các tiến trình xử lý dữ liệu lớn.` |
| 12 | 3 | `[85:161)` | `- Lập báo cáo tài chính hàng tháng và quyết toán thuế thu nhập doanh nghiệp.` |

## Đề xuất để HR/IT thật duyệt

1. Xác nhận từng nhiệm vụ trong JD với vị trí thực tế; đánh dấu yêu cầu bắt buộc và ưu tiên, phạm vi junior/middle và phần nào được chấp nhận từ dự án cá nhân/đồ án.
2. Với từng criterion, cùng chấm độc lập một số ví dụ synthetic mới và thảo luận các trường hợp phân biệt score 1/2/3, null, score 0, `contradicted` và `conflicting_evidence`. Không dùng bảng này làm tài liệu chấm độc lập.
3. Hiệu chuẩn hoặc giữ nguyên trạng thái `unvalidated` cho trọng số, threshold 70 và core floors. Không thay đổi chúng dựa trên fixture mô phỏng.
4. HR điền/duyệt các điều kiện tuyển dụng còn thiếu trước công bố; người có thẩm quyền phê duyệt đúng snapshot JD/rubric qua workflow hiện hành.
5. Tổ chức HR và IT đánh giá độc lập trên dữ liệu có quyền sử dụng phù hợp, không xem kết quả AI trước khi khóa nhãn. Bộ fixture hiện tại không thay thế dữ liệu/nhãn đó.

**Xác nhận trạng thái:** chưa có phê duyệt HR/IT thật; chưa có nhãn gold; chưa có benchmark quality result. Báo cáo này chỉ là AI-simulated review trên fixture synthetic và không phải quyết định tuyển dụng.
