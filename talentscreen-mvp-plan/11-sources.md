# 11 — Nguồn kỹ thuật và dữ liệu đã kiểm tra

Ngày rà soát: **2026-09-26**. Các nguồn bên dưới hỗ trợ những lựa chọn cụ thể; không phải chứng nhận chất lượng hoặc tuân thủ cho TalentScreen AI. Khi implement, kiểm tra lại các API/model/pricing/dependency có thể thay đổi. Các con số thiết kế như trọng số JD, threshold70, capUSD10 và timeline là đề xuất của plan, không lấy làm "chuẩn ngành" từ các nguồn này.

| ID | Nguồn chính | Dùng cho | Giới hạn cần giữ |
|---|---|---|---|
| SRC-01 | [DeepSeek API](https://api-docs.deepseek.com/) | Base URL/model naming/capability probe | Tài liệu hiện có tên model khác `deepseek-chat`; chưa kiểm tài khoản user. Không tự thay model. |
| SRC-02 | [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/) | JSON mode, hướng dẫn output, xử lý empty/truncated | JSON hợp lệ không chứng minh schema nghiệp vụ và evidence đúng. |
| SRC-03 | [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/) | Request/response adapter, stop reasons và usage | Endpoint/capabilities có thể thay đổi; actual synthetic probe là bằng chứng cần có. |
| SRC-04 | [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/) | Rate-card registry và cost reservation | Không áp giá model khác cho `deepseek-chat`; không hardcode giá vĩnh viễn. |
| SRC-05 | [Apple PyTorch/Metal](https://developer.apple.com/metal/pytorch/) | Native Python MPS trên Apple Silicon | Không có benchmark MacAirM4 cụ thể của user trong nhiệm vụ này. |
| SRC-06 | [Docker Desktop GPU](https://docs.docker.com/desktop/features/gpu/) | Tách native MPS và CPU Docker profile | Không giả định Apple GPU passthrough vào Linux container. |
| SRC-07 | [Multilingual E5 base model card](https://huggingface.co/intfloat/multilingual-e5-base) | Local multilingual dense embeddings, input prefix/token limits | Hỗ trợ ngôn ngữ không đồng nghĩa retrieval CV Việt–Anh đã đạt. |
| SRC-08 | [BGE-M3 model card](https://huggingface.co/BAAI/bge-m3) | Challenger benchmark | Không thêm nhiều retrieval modes/model serving vào MVP khi chưa cần. |
| SRC-09 | [pgvector](https://github.com/pgvector/pgvector) | Exact search, filter, hybrid/RRF | Perfect vector nearest-neighbor recall không đồng nghĩa tìm đủ evidence nghiệp vụ. |
| SRC-10 | [PostgreSQL row security](https://www.postgresql.org/docs/17/ddl-rowsecurity.html) | Giới hạn RLS/roles nếu sử dụng | Single-org MVP dùng backend scope checks; RLS nếu thêm không miễn kiểm quyền app. |
| SRC-11 | [Promptfoo configuration](https://www.promptfoo.dev/docs/configuration/guide/) | So prompt trên cùng input, assertions | Chạy local harness không có nghĩa provider call cũng local; phải quản lý egress/budget. |
| SRC-12 | [Promptfoo assertions](https://www.promptfoo.dev/docs/configuration/expected-outputs/) | JSON/custom assertion + compare runner | LLM judge chỉ hỗ trợ, không thay HR nhãn độc lập. |
| SRC-13 | [OWASP prompt injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) | Trust boundary, least privilege, output validation | Không có một prompt có thể bảo đảm loại bỏ mọi injection. |
| SRC-14 | [NIST managing AI bias](https://www.nist.gov/artificial-intelligence/ai-fundamental-research-managing-ai-bias) | Kiểm soát bias ở model, rubric và quy trình người dùng | Bộ counterfactual nhỏ không phải chứng nhận công bằng dân số. |
| SRC-15 | [Google SRE: implementing SLOs](https://sre.google/workbook/implementing-slos/) | SLI/SLO/error budget và hành động khi vi phạm | SLO trong plan chưa được đo trên hệ thống. |
| SRC-16 | [OPM structured interviews](https://www.opm.gov/policy-data-oversight/assessment-and-selection/structured-interviews) | Câu hỏi cốt lõi/thang chấm chung, bổ sung làm rõ có kiểm soát | Không dùng câu hỏi cá nhân hóa để tạo yêu cầu khác nhau theo ứng viên. |
| SRC-17 | [scikit-learn Cohen's kappa](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.cohen_kappa_score.html) | Agreement cho mức đánh giá | Báo phân bố nhãn và N/A khi metric không xác định; không chỉ một scalar. |
| SRC-18 | [scikit-learn MAE](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.mean_absolute_error.html) | Sai lệch mức điểm | Báo coverage/missingness riêng, không tự map unknown thành0. |
| SRC-19 | [candidate-matching-synthetic](https://huggingface.co/datasets/michaelozon/candidate-matching-synthetic) | Nguồn synthetic IT bootstrap | Nhãn nguồn dựa matching heuristic; không phải nhãn HR của JD này. |
| SRC-20 | [datasetmaster/resumes](https://huggingface.co/datasets/datasetmaster/resumes) | Nguồn tham khảo dự phòng | Trộn real/synthetic, chưa được chọn auto-import. |
| SRC-21 | [opensporks/resumes card](https://huggingface.co/datasets/opensporks/resumes/blob/main/README.md) | Rà nguồn public có categoryIT và layout | Mirror ghi nguồn scrape; không được coi là CV đã có đầy đủ quyền xử lý chỉ vì public. |
| SRC-22 | [Kaggle Resume Dataset](https://www.kaggle.com/datasets/snehaanbhawal/resume-dataset) | Upstream được mirror khai báo | Trang render không cung cấp toàn bộ nội dung qua công cụ ở lần rà; nhận xét provenance dựa card mirror, không tuyên bố đã tải/kiểm dữ liệu gốc. |

## Các việc đã và chưa xác minh

- Đã kiểm tra: nguồn/card chính thức, các lựa chọn kiến trúc, source-license labels hiển thị, giới hạn model được card công bố, ràng buộc user và tính nhất quán tài liệu theo vòng review.
- Chưa kiểm tra bằng thực thi: API key/tài khoản DeepSeek, hỗ trợ actual alias, giá bill của user, RAM/thông lượng Mac, nội dung toàn bộ dataset, license snapshot tại commit pin, CV thật, nhãn HR, latency/cost/accuracy thực tế của TalentScreen.
- Việc thiếu các kết quả thực thi không được che bằng nhãn "production-ready". Backlog và gate quy định khi nào phải có chúng.

## Quy tắc trích dẫn trong báo cáo đồ án

Phân biệt rõ (1) tài liệu nguồn công bố, (2) lựa chọn thiết kế của nhóm, (3) kết quả nhóm tự đo. Với nguồn dataset giữ attribution/license/revision. Với benchmark ghi split/family/source và kích thước mẫu. Không dùng số benchmark từ model card làm thành số đo dự án.
