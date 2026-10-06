# Bộ JD và rubric benchmark đa vị trí

Ngày lập: 2026-10-05. Đây là bộ kiểm thử kỹ thuật do trợ lý role-play HR/IT soạn. Các JD được tổng hợp lại từ yêu cầu công khai của tin tuyển thực tập trên TopCV, không sao chép nguyên văn và không đại diện cho vị trí tuyển dụng của Trường đại học X. Kết quả không được dùng làm quyết định tuyển dụng thật.

## Phạm vi và phân loại đầu vào

Đợt rà soát cục bộ tìm thấy 8 PDF được tải cùng đợt. Kiểm tra nội dung cho thấy 7 tệp là CV ứng viên và 1 tệp là mô tả công việc Product Owner Intern. Tệp JD được giữ làm ca kiểm tra phân loại tài liệu, không đưa vào scoring ứng viên. Bảy CV được định tuyến sơ bộ theo nội dung kỹ thuật và mục tiêu công việc, không theo tên, trường, tuổi, giới tính, địa chỉ hay thời lượng nghỉ việc:

| Rubric | Hồ sơ benchmark | Căn cứ định tuyến |
|---|---:|---|
| Backend Node/NestJS Intern | 2 | CV nêu mục tiêu Backend/Node và dự án NestJS, Node/TypeScript hoặc API backend. |
| AI/ML Intern | 2 | CV nêu hướng AI, Python/ML; một hồ sơ chỉ có bằng chứng nền tảng, hồ sơ còn lại có dự án model/RAG triển khai. |
| .NET Full-stack Intern | 1 | CV có dự án C#/.NET cùng cơ sở dữ liệu và giao diện web/desktop. |
| Android Intern | 1 | CV nêu dự án ứng dụng Android với Kotlin/Java và lưu trữ dữ liệu di động. |
| Java/Spring Backend Intern | 1 | CV có dự án web backend Java/Spring Boot và SQL. |
| Product Owner Intern | 0 | PDF Product Owner là JD, không phải CV. |

Việc chọn đúng requisition trong tuyển dụng thật phải dựa trên vị trí ứng viên đã nộp hoặc HR xác nhận. Bộ phân loại chỉ gợi ý; không tự chuyển hoặc loại ứng viên.

## JD mẫu và rubric

Rubric dùng chung: anchor 0–4, giải thích bằng evidence spans, thuộc tính định danh bị loại khỏi đánh giá. `insufficient_evidence` là `null`, không phải 0. Điểm 0 chỉ dùng khi CV có bằng chứng rõ ràng về một tác vụ đã được thực hiện nhưng không đạt yêu cầu anchor. Danh sách công nghệ đơn lẻ không chứng minh năng lực. Chỉ dùng kinh nghiệm trả phí, dự án cá nhân, đồ án và đóng góp cộng đồng theo cùng chuẩn bằng chứng.

Anchor nền cho mọi rubric:

- **0:** Bằng chứng trực tiếp cho thấy một tác vụ liên quan được thực hiện nhưng kết quả/phương pháp không đạt anchor tối thiểu. Không dùng khi CV không nói đến năng lực.
- **1:** Bằng chứng cá nhân cho một thao tác nhỏ, có hướng dẫn; nêu được việc đã làm nhưng phạm vi hẹp.
- **2:** Tự hoàn thành một tác vụ/dự án nhỏ từ đầu đến cuối; giải thích được cách làm cơ bản.
- **3:** Tích hợp nhiều thành phần, xử lý trường hợp thực tế và kiểm tra kết quả; phạm vi cá nhân rõ.
- **4:** Có trade-off kỹ thuật/sản phẩm được nêu rõ, kiểm chứng bằng kết quả và có vòng lặp cải tiến. Đây là anchor mở, không phải điều kiện bắt buộc cho thực tập.

### A. Backend Node.js/NestJS Intern

**Mô tả mẫu:** Tham gia xây dựng và bảo trì service backend bằng Node.js/TypeScript hoặc NestJS dưới hướng dẫn; triển khai API cho một tính năng; kết nối cơ sở dữ liệu; xử lý lỗi và kiểm thử thay đổi; dùng Git và quy trình review nhóm. Dự án học tập/cá nhân được chấp nhận như bằng chứng tương đương.

Nguồn để tổng hợp: [Backend Intern (NestJS / FastAPI) trên TopCV](https://www.topcv.vn/viec-lam/backend-intern-nestjs-fastapi/1742673.html) và [Backend Intern Python trên TopCV](https://www.topcv.vn/viec-lam/backend-intern-python/1633322.html). JD mẫu giữ các nhiệm vụ API, dữ liệu, test, Git; bỏ điều kiện giới tính, trường học và vị trí địa lý.

| ID | Trọng số | Năng lực |
|---|---:|---|
| `backend_implementation` | 30 | Tác vụ backend cá nhân trong Node/Nest hoặc framework tương đương ở cùng cấp độ. |
| `api_design` | 25 | Endpoint, CRUD, xác thực/ủy quyền và contract request/response có bằng chứng. |
| `data_management` | 20 | Truy vấn, schema, quan hệ hoặc cache được dùng trong một dự án cụ thể. |
| `security` | 15 | Xử lý xác thực, phân quyền, hash/validation hoặc rủi ro API có bằng chứng. |
| `testing_delivery` | 10 | Test, debug, Git/CI, triển khai hoặc quy trình bàn giao thể hiện qua tác vụ. |

### B. Java/Spring Backend Intern

**Mô tả mẫu:** Hỗ trợ phát triển backend Java/Spring Boot; xây dựng tính năng web và API; dùng SQL để lưu/truy xuất dữ liệu; áp dụng phân quyền cơ bản; viết test hoặc tái hiện/sửa lỗi; làm việc theo Git và nhận review.

Nguồn để tổng hợp: [Java Intern (Spring, Java Core, Back-End, SQL) trên TopCV](https://www.topcv.vn/viec-lam/java-intern-spring-java-core-back-end-sql/1595585.html) và [Backend Intern (NestJS / FastAPI) trên TopCV](https://www.topcv.vn/viec-lam/backend-intern-nestjs-fastapi/1742673.html) cho các nhiệm vụ backend chung. JD mẫu không yêu cầu bằng cấp/trường cụ thể.

| ID | Trọng số | Năng lực |
|---|---:|---|
| `java_spring` | 30 | Java/Spring được dùng để xây dựng thành phần ứng dụng cụ thể. |
| `api_design` | 25 | Endpoint, HTTP/JSON, xử lý request và vai trò người dùng có evidence. |
| `database_sql` | 20 | Truy vấn, mô hình dữ liệu hoặc tích hợp SQL được mô tả. |
| `security` | 15 | Cơ chế auth/authorization/input validation được thể hiện qua tác vụ. |
| `testing_quality` | 10 | Test, debug, review hoặc sửa lỗi có bằng chứng. |

### C. AI/ML Intern

**Mô tả mẫu:** Hỗ trợ chuẩn bị dữ liệu và thử nghiệm một mô hình AI/ML bằng Python/framework phù hợp; ghi lại cấu hình/thí nghiệm; chọn metric đúng bài toán và so sánh baseline; tích hợp prototype vào ứng dụng hoặc pipeline; báo cáo giới hạn và kết quả để mentor review.

Nguồn để tổng hợp: [AI Intern tại IDT trên TopCV](https://www.topcv.vn/viec-lam/thuc-tap-sinh-ai-intern-ai/1625628.html), [AI Intern tại Concentrix trên TopCV](https://www.topcv.vn/brand/concentrixservices/tuyen-dung/thuc-tap-sinh-tri-tue-nhan-tao-j1988558.html) và [AI Intern tại XTech trên TopCV](https://www.topcv.vn/viec-lam/fullstack-ai-intern/2007044.html). Mẫu nhấn mạnh Python, model, evaluation và prototype; không biến tool list hoặc bằng cấp thành điểm.

| ID | Trọng số | Năng lực |
|---|---:|---|
| `python_data` | 20 | Python/data processing được gắn với tác vụ hoặc dự án. |
| `ml_foundations` | 20 | Lựa chọn/phân biệt phương pháp ML/DL theo bài toán có evidence. |
| `model_implementation` | 25 | Huấn luyện, fine-tune, inference hoặc tích hợp model được mô tả. |
| `evaluation` | 20 | Baseline, metric, so sánh hoặc kiểm thử chất lượng model. |
| `reproducibility_delivery` | 15 | Ghi cấu hình, quản lý thí nghiệm, đóng gói hoặc triển khai. |

### D. .NET Full-stack Intern

**Mô tả mẫu:** Thực hiện thay đổi có hướng dẫn trong ứng dụng C#/.NET; xây dựng hoặc sửa API và logic nghiệp vụ; thao tác SQL; kết nối giao diện web/desktop với dịch vụ; kiểm thử thủ công/tự động và dùng Git để bàn giao.

Nguồn để tổng hợp: [Fullstack Intern React/Next.js & .NET Core trên TopCV](https://www.topcv.vn/viec-lam/fullstack-intern-react-next-js-net-core-fulltime/2021330.html), [.NET Intern trên TopCV](https://www.topcv.vn/viec-lam/net-intern/705974.html) và [Software Engineer C#/.NET Intern/Fresher trên TopCV](https://www.topcv.vn/viec-lam/software-engineer-c-net-intern-fresher-junior-tai-ha-noi/2219098.html). Không dùng yêu cầu giới tính, trường hoặc địa điểm của tin nguồn.

| ID | Trọng số | Năng lực |
|---|---:|---|
| `dotnet_implementation` | 30 | C#/.NET/WinForms/ASP.NET được dùng trong chức năng cụ thể. |
| `database_sql` | 20 | SQL, truy vấn hoặc data access qua EF/Dapper được thể hiện. |
| `api_integration` | 20 | API, server/client integration hoặc luồng dữ liệu có evidence. |
| `frontend_delivery` | 15 | Giao diện, component/state hoặc luồng người dùng được triển khai. |
| `testing_git` | 15 | Test, debug, Git, CI hoặc deploy có bằng chứng cụ thể. |

### E. Android Intern

**Mô tả mẫu:** Hỗ trợ phát triển màn hình và tính năng Android bằng Kotlin/Java; xử lý lifecycle/navigation và tổ chức mã theo kiến trúc cơ bản; kết nối API hoặc local/cloud storage; kiểm thử, sửa lỗi và bàn giao qua Git dưới hướng dẫn.

Nguồn để tổng hợp: [Mobile Android (Intern & Fresher) trên TopCV](https://www.topcv.vn/viec-lam/mobile-android-intern-fresher/783919.html). Framework cụ thể như Jetpack/Room là bằng chứng tương đương, không bắt buộc nếu JD không yêu cầu.

| ID | Trọng số | Năng lực |
|---|---:|---|
| `android_kotlin` | 30 | Kotlin/Java được sử dụng trong ứng dụng Android cụ thể. |
| `mobile_features` | 25 | Tính năng/app flow được cá nhân triển khai và mô tả. |
| `architecture_lifecycle` | 15 | OOP/MVC/MVVM, lifecycle hoặc state management có evidence sử dụng. |
| `data_integration` | 15 | API, Firebase, Room/SQLite hoặc luồng đồng bộ dữ liệu có evidence. |
| `testing_delivery` | 15 | Test/debug, Git hoặc bản build/deploy được thể hiện. |

### F. Product Owner Intern (ca JD, không có CV)

**Mô tả mẫu:** Hỗ trợ nghiên cứu nhu cầu người dùng/thị trường; ghi yêu cầu thành user story và acceptance criteria; sắp xếp backlog cùng PO; phối hợp kỹ sư/QA làm rõ tính năng; hỗ trợ UAT và theo dõi phản hồi/chỉ số sau phát hành.

Nguồn để tổng hợp: [Product Owner Intern trên TopCV](https://www.topcv.vn/viec-lam/product-owner-intern/1958339.html) và [Product Owner Intern tại NextGen Việt Nam trên TopCV](https://www.topcv.vn/viec-lam/product-owner-intern/914320.html). File PDF Product Owner trong bộ tải về là mô tả công việc tương tự và được dùng làm ca test loại tài liệu, không phải CV.

| ID | Trọng số | Năng lực |
|---|---:|---|
| `user_research` | 25 | Thu thập/tổng hợp nhu cầu người dùng hoặc market evidence. |
| `requirements` | 25 | User story, acceptance criteria hoặc tài liệu hóa yêu cầu. |
| `prioritization` | 20 | Trade-off, ưu tiên backlog/roadmap có căn cứ. |
| `delivery_collaboration` | 15 | Làm rõ yêu cầu với engineering/QA, hỗ trợ UAT. |
| `product_metrics` | 15 | Phản hồi, funnel/retention hoặc chỉ số dùng để đề xuất cải tiến. |

## Expected output contract

Tạo 7 expected records riêng tư cho 7 CV, mỗi record khóa `sample_id`, `rubric_id`, `role_family`, `criterion_scores` động và `recommendation=review_required`. Đây là nhãn thiết kế của một AI đang role-play; không dùng nhãn `hr_blind`, không tính là nghiệm thu G5. Evidence quote/rationale được lưu cùng file private, không vào Git.

PDF Product Owner được người rà soát phân loại là JD và **không có assessment record**. Bộ phân loại tự động cũ trả `unknown/low`, nên đây là ca false negative quan trọng. Bản sửa mới bổ sung mẫu ngôn ngữ Product Owner; dù vậy, mọi tài liệu có loại `unknown` hoặc `job_description` đều phải được HR đối chiếu và xác nhận là CV trước khi cho phép AI xử lý. Không dựa riêng vào confidence của bộ phân loại để gửi dữ liệu ra provider.

JD/rubric machine-readable để seed hoặc chạy regression nằm tại [`multi-role-jd-and-rubrics-v1.json`](multi-role-jd-and-rubrics-v1.json). Fixture có 6 vị trí, mỗi rubric 5 tiêu chí, tổng trọng số 100%, anchor 0–4 và nguồn tham khảo.

## Kết quả artifact nội bộ

Đã tạo 7 nhãn `design_expected` trong `private_storage/eval/multi_role_design_expected_labels.jsonl` và manifest nối bằng SHA-256 trong `private_storage/eval/multi_role_source_manifest.json`. Manifest không lưu tên file hay raw text; các artifact chỉ đọc được bởi user hiện tại. Mỗi rubric có một case, ngoại trừ Backend Node/NestJS và AI/ML có hai case. PDF Product Owner bị loại khỏi scoring. Một hồ sơ AI/IT chỉ có bằng chứng định tuyến yếu được đánh dấu cần HR xác nhận vị trí trước assessment.

Các nhãn này do trợ lý role-play HR/IT tự lập từ CV đã khử định danh, chỉ phục vụ kiểm tra pipeline/prompt. Chúng không phải đánh giá độc lập của HR, không đủ cỡ mẫu để tính độ tương đồng có ý nghĩa, và không thể ký nghiệm thu hoặc quyết định ai đi tiếp.

Đã gửi một CV đã khử định danh sang DeepSeek Flash hai lần để smoke test; cả hai phản hồi đều bị cắt tại giới hạn 1.600 và 2.800 token. Không có prediction nào vượt validator, và không gửi tiếp 6 CV còn lại. Hai lượt có trần chi phí rate-card ước tính tổng cộng 0,008104 USD; provider adapter hiện không trả usage khi ném lỗi truncated nên chi phí thanh toán thực cần đối chiếu dashboard provider. Jev không được gọi. Prompt được tăng lên v1.4.0 với giới hạn độ dài rationale/câu hỏi và evidence span để giảm nguy cơ cắt; cần kiểm thử lại theo luồng có ledger trước khi dùng thật.

## Quy trình chạy benchmark

1. Freeze bản JD/rubric này, version/hash prompt và expected labels trước khi gọi provider.
2. Xác nhận mapping 7 CV với role family; hồ sơ định tuyến yếu phải dừng ở `route_to_human`. Chỉ dùng sanitized text đã được HR rà soát. Không dùng PDF loại JD làm input candidate.
3. Chạy mỗi CV đúng một rubric tương ứng qua luồng assessment, lưu output JSON, span validation, model/prompt version, token, latency và cost. Jev vẫn tắt cho CV thật vì chưa có phê duyệt riêng cho nhà cung cấp này.
4. So từng criterion score/status với expected labels, đồng thời ghi quote mismatch/unsupported evidence và `null` coverage. Không so sánh tổng điểm giữa các rubric khác nhau.
5. Dán nhãn kết quả là prompt/regression smoke set, không phải holdout thống kê. HR và người chuyên môn IT độc lập cần chấm blind một bộ mới trước khi dùng score để đề xuất vòng tiếp theo.


## Cập nhật lượt chạy provider ngày 05/10/2026

Lượt chạy mới dùng prompt `assessment-v1.4.0` và `deepseek-flash`, gọi một lần cho mỗi 7 CV sau khử định danh. 6/7 output vượt validator citation/schema; một output bị validator từ chối và không được dùng điểm. Không retry. Điểm từng tiêu chí và trạng thái được lưu trong artifact riêng `private_storage/eval/multi_role_provider_smoke_20261005.json` (quyền tệp 0600, không lưu tên tệp gốc hay raw CV). Đối chiếu với 17 nhãn `design_expected` còn so sánh được: 4/17 điểm trùng tuyệt đối (23,5%), MAE 0,82/4. Đây chỉ là sanity check vì nhãn do AI role-play tạo, không phải HR ground truth. Rate-card estimate cho lượt mới là 0,02498530 USD; cộng upper-bound hai request cũ và Jev synthetic smoke vẫn dưới cap đã đặt 0,05 USD.

Jev API `typesafe/jev-1.13` được gọi thành công với 497 input tokens trên dữ liệu hoàn toàn tổng hợp (model trả score 1,66, confidence 0,71). Jev không nhận bất kỳ CV thật nào: `.env` vẫn để `JEV_MODE=off` và `JEV_DATA_PROCESSING_APPROVED=false`; override tạm chỉ tồn tại trong tiến trình chạy synthetic smoke. Vì vậy chưa có so sánh Jev–DeepSeek trên ứng viên.


## Cập nhật lượt chạy Jev trên CV đã khử định danh ngày 05/10/2026

Sau khi người dùng xác nhận Jev được phép cho mục đích kiểm thử, Jev 1.13 đã chấm 7/7 CV đã khử định danh theo JD/rubric tương ứng. So với 6 assessment DeepSeek vượt validator (case AI/ML thứ hai không có điểm DeepSeek được chấp nhận), có 24 cặp tiêu chí không-null: điểm Jev liên tục có MAE 0,503 so với điểm nguyên DeepSeek; dùng anchor có xác suất cao nhất của Jev, 4/24 cặp trùng anchor và 22/24 lệch không quá một anchor. Đây là mô tả chênh lệch giữa hai model, không phải độ đúng hay đồng thuận HR.

Lượt Jev tốn khoảng 0,000963 USD theo rate card; tổng ước tính gồm các lượt DeepSeek/Jev trước đó khoảng 0,034073 USD. Chi tiết score, xác suất, confidence, token và hash nguồn nằm trong `private_storage/eval/multi_role_jev_comparison_20261005.json` (mode 0600; không lưu CV thô/tên file). Đây vẫn là direct provider smoke, chưa qua workflow/audit ledger end-to-end của ứng dụng. Cờ Jev trong `.env` vẫn tắt; chỉ tiến trình kiểm thử được override tạm.


### So sánh điểm quan sát sau chuẩn hóa cùng tiêu chí

Để so sánh điểm tổng hợp, chỉ lấy các tiêu chí DeepSeek đã trả điểm hợp lệ, áp trọng số rubric và chuẩn hóa trên các tiêu chí đó. Trên 6 hồ sơ có kết quả hợp lệ ở cả hai model, Jev thấp hơn DeepSeek ở cả 6; chênh lệch tuyệt đối trung bình là 12,1 điểm phần trăm. Theo anchor có xác suất cao nhất của Jev, 14/24 tiêu chí trùng điểm DeepSeek và cả 24/24 lệch không quá một anchor. Đây là thống kê tổng hợp để kiểm tra calibration; tài liệu công khai không lưu điểm theo từng hồ sơ. Các điểm quan sát có coverage dưới 100% không dùng để xếp hạng. Case không có điểm DeepSeek hợp lệ không nằm trong so sánh.
