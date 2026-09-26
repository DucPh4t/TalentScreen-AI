# TalentScreen AI — Bộ đặc tả triển khai MVP

**Bản lập ngày 2026-09-26.** Dành cho một người/AI implement trong 4–8 tuần, local MacBook Air M4 trước, hỗ trợ HR tuyển Backend Python trong trường đại học. DeepSeek được người dùng xác nhận có quyền sử dụng theo chính sách trường; có thể mời HR và chuyên môn IT tham gia.

**Bắt đầu bằng [START_HERE.md](START_HERE.md).** File đó chứa prompt bàn giao có thể dùng trực tiếp cho AI khác. Bộ này là plan/specification, chưa triển khai ứng dụng hoặc gọi API để đánh giá CV.

## Cấu hình đã chọn

- FastAPI modular monolith + một worker PostgreSQL queue; Next.js; PostgreSQL/pgvector; private file storage.
- Native Python CPU/MPS trên Mac để local embedding; Docker PostgreSQL; portable Docker CPU profile cho bước deploy sau.
- Ba task LLM có giới hạn: rubric draft, evidence assessment, interview draft. Backend tính điểm và kiểm soát quyền.
- Một JD Backend Python và sáu tiêu chí mẫu; ngưỡng đề xuất là draft để HR hiệu chuẩn, không phải tiêu chuẩn validated.
- CV thật phải qua sanitized review; nhận định có nguồn, unknown không bằng0, HR quyết định cuối.
- Full-text baseline cho CV ngắn; hybrid retrieval chỉ bật sau benchmark. Chưa có portal ứng viên, ATS, SSO, email tự động hoặc fine-tuning.

## Mục lục

| File | Nội dung |
|---|---|
| [00 — Scope/decisions](00-scope-decisions.md) | Yêu cầu đã xác nhận, default và ranh giới MVP |
| [01 — Product/UX](01-product-and-ux.md) | User stories, màn hình, validation, HR flow, onboarding |
| [02 — Architecture](02-architecture.md) | Modules, local/deploy topology, queue và transaction |
| [03 — Data/API/state machines](03-data-api-state-machines.md) | Tables/constraints, endpoint contracts, permissions, state transitions |
| [04 — AI/RAG/prompts](04-ai-rag-prompts.md) | Prompt templates, provider adapter, scoring, retrieval, multilingual |
| [05 — Security/privacy](05-security-privacy.md) | Threat model, auth, egress, upload, sanitization, audit, deletion |
| [06 — Evaluation/testing](06-evaluation-and-testing.md) | Test suites, HR labels, metrics, prompt regression, release criteria |
| [07 — Operations/deployment](07-operations-deployment.md) | Doctor, config, model probe, budget, SLO, backup/restore, deploy preparation |
| [08 — Data sourcing](08-data-sourcing.md) | Dataset đã tìm, nguồn quyền sử dụng, importer và synthetic fixture flow |
| [09 — Implementation backlog](09-implementation-backlog.md) | B00–B26, dependency, estimate, output, acceptance, test và milestones |
| [10 — Review/traceability](10-audit-traceability.md) | Các lỗi brainstorm đã sửa, mapping yêu cầu và giới hạn chưa kiểm chứng |
| [11 — Sources](11-sources.md) | Nguồn chính thức, ngày kiểm tra và phạm vi xác minh |

## Hợp đồng và ví dụ máy đọc

- [Assessment JSON Schema](contracts/assessment-output.schema.json).
- [Ví dụ assessment hợp lệ](contracts/assessment-output.valid-example.json), [input/nguồn tái dựng](contracts/assessment-input.example.json) và [kết quả tính điểm kỳ vọng](contracts/assessment-derived.expected.json).
- [Interview output schema](contracts/interview-output.schema.json), [ví dụ output](contracts/interview-output.valid-example.json) và [ngân hàng sáu câu hỏi mẫu](examples/interview-question-bank.v1.json).
- [JD Backend Python tự soạn](examples/jd-backend-python.vi.md).
- [Rubric seed draft](examples/rubric-backend-python.v1.json).
- [Dataset source registry — chưa import](examples/dataset-source-registry.json).

Các ID/version/nội dung synthetic trong examples phục vụ đặc tả. Không phải CV thật, không phải nhãn HR đã xác nhận, không có API key. Dataset registry cố ý chưa pin revision và tắt import: AI implement phải inspect nguồn trước khi nhập, không thay `null` bằng SHA bịa.

## Kết quả tự review

Đã sửa các khoảng trống quan trọng: thang điểm trộn bằng chứng/năng lực; ranking hồ sơ thiếu thông tin; candidate/application/version; quyền final decision; source contract; xóa khi job đang chạy; API alias/JSON mode; native MPS so với Docker; quality/SLO/budget; nguồn dataset và independent HR labels. Chi tiết từng vấn đề ở10.

## Nghiệm thu theo giai đoạn

Tuần1–4: local vertical slice với synthetic và mock/provider đã probe. Tuần5–6: hardening, labels và benchmark. Tuần7–8: shadow batch thật rồi assisted pilot nếu đạt G1–G7 trong09. Bốn tuần không đồng nghĩa mọi điều kiện dùng dữ liệu thật đã hoàn tất.

Các bất định còn lại là công việc có task rõ: actual model alias/rate card, RAM/throughput, retention cụ thể, lịch HR và chất lượng dữ liệu thực. Không cần thêm lựa chọn thư viện từ user để bắt đầu xây bản local; không được dùng việc đó làm lý do bỏ các kiểm soát bắt buộc.

## Xác minh artifact

Trạng thái kiểm tra cuối được ghi trong [artifact-validation.json](artifact-validation.json) sau khi chạy [validator](scripts/validate_plan.py). Báo cáo đó chỉ kiểm tra tài liệu/JSON/schema/liên kết và tính nhất quán mẫu, **không phải kết quả test ứng dụng TalentScreen**. Xem trường `scope` và `checks` trước khi trích dẫn trong báo cáo.


Chạy lại kiểm tra artifact bằng Python trong virtual environment riêng:

```sh
python -m pip install -r scripts/requirements-validation.txt
python scripts/validate_plan.py
```

Chạy từ thư mục bộ tài liệu. Validator không gọi DeepSeek, tải CV hoặc chạy application. Nó kiểm schema/negative cases, nguồn và công thức của fixture synthetic, JD/rubric/bank, links và dependency task. Semantic correctness của AI và bảo mật runtime vẫn cần các test được quy định ở06.
