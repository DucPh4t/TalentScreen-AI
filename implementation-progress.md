# TalentScreen AI — Nhật Ký Triển Khai (Implementation Progress)

Theo dõi tiến độ theo dõi thực hiện các task B00–B26 và Stage Gates G1–G7 được quy định trong `talentscreen-mvp-plan/09-implementation-backlog.md`.

---

## Tổng quan tiến độ Tasks

| Task | Tên tác vụ | Ưu tiên | Trạng thái | Ghi chú & Lệnh kiểm thử |
|---|---|---|---|---|
| **B00** | Khởi tạo monorepo, doctor và cấu hình | P0 | **COMPLETED** | `make doctor`, `make test-backend`, Next.js build pass |
| **B01** | Data model, migration và domain enums | P0 | *READY* | Sẵn sàng triển khai SQLAlchemy 2 models + Alembic |
| **B02** | Authentication, session, CSRF và authorization | P0 | *PENDING* | Phụ thuộc B01 |
| **B03** | Requisition và JD version | P0 | *PENDING* | Phụ thuộc B02 |
| **B04** | Rubric seed, editor, approval và policy | P0 | *PENDING* | Phụ thuộc B03 |
| **B05** | Intake upload và private storage | P0 | *PENDING* | Phụ thuộc B02, B03 |
| **B06** | Parse PDF, normalization và provenance | P0 | *PENDING* | Phụ thuộc B05 |
| **B07** | Durable PostgreSQL worker | P0 | *PENDING* | Phụ thuộc B01, B05 |
| **B08** | Sanitization, HR approval và source viewer | P0 | *PENDING* | Phụ thuộc B06, B07 |
| **B09** | DeepSeek adapter, capabilities và cost ledger | P0 | *PENDING* | Phụ thuộc B07, B08 |
| **B10** | Full-text assessment baseline & output validation | P0 | *PENDING* | Phụ thuộc B04, B08, B09 |
| **B11** | Deterministic scoring/recommendation engine | P0 | *PENDING* | Phụ thuộc B04 |
| **B12** | Review workspace và danh sách ứng viên | P0 | *PENDING* | Phụ thuộc B10, B11 |
| **B13** | HR revision, attestation, decision và audit | P0 | *PENDING* | Phụ thuộc B12, B02 |
| **B14** | Rubric Agent và Interview Agent | P0 | *PENDING* | Phụ thuộc B09, B10, B13 |
| **B15** | Local OCR và DOCX rendering | P1 | *PENDING* | Phụ thuộc B06, B07 |
| **B16** | Local multilingual embeddings & hybrid retrieval | P1 | *PENDING* | Phụ thuộc B08, B10 |
| **B17** | Deletion, retention và data inventory | P0 | *PENDING* | Phụ thuộc B07, B08, B13 |
| **B18** | Dataset bootstrap và fixture factory | P0 | *PENDING* | Phụ thuộc B00, B04 |
| **B19** | Evaluation harness, metrics và HR annotation | P0 | *PENDING* | Phụ thuộc B10, B11, B18 |
| **B20** | Prompt regression và release/rollback | P0 | *PENDING* | Phụ thuộc B19 |
| **B21** | Sandbox onboarding và help UI | P0 | *PENDING* | Phụ thuộc B12, B13, B18 |
| **B22** | Security regression và privacy review kỹ thuật | P0 | *PENDING* | Phụ thuộc B02, B08, B13, B17 |
| **B23** | Observability, load và budget operations | P0 | *PENDING* | Phụ thuộc B07, B09, B19 |
| **B24** | Packaging, backup và restore | P0 | *PENDING* | Phụ thuộc B17, B22 |
| **B25** | HR calibration, shadow và pilot gate | P0 | *PENDING* | Phụ thuộc B19–B24 |
| **B26** | Sửa lỗi còn lại và bàn giao vận hành | P0 | *PENDING* | Phụ thuộc B25 |

---

## Chi tiết thực hiện từng Task

### B00 — Khởi tạo monorepo, doctor và cấu hình
* **Thời điểm hoàn thành:** 2026-09-26
* **Files đã tạo:**
  * `.gitignore`: Chặn rò rỉ `.env`, `private_storage/`, credentials, Python `.venv`, Next.js `node_modules` và `.next`.
  * `.env.example` & `.env`: Cấu hình typed đầy đủ các biến hệ thống theo `02-architecture` và `07-operations-deployment`.
  * `docker-compose.yml` & `docker/init-db.sql`: Khởi tạo PostgreSQL 16 + `pgvector` container bind cục bộ `127.0.0.1:5432` với extension `vector` và `uuid-ossp`.
  * `services/backend/`: Monolith backend với FastAPI, Pydantic v2 Settings, domain enums, routers `/api/v1/health` và `/api/v1/config/diagnostic`.
  * `apps/web/`: Frontend Next.js 15 + React 19 + TypeScript với reverse proxy `/api/*` về backend, thiết lập bảng màu dark mode và design tokens chuẩn.
  * `scripts/doctor.py`: Script chẩn đoán môi trường hệ điều hành, Python, Node, Docker daemon, Storage và Config (không rò rỉ secret).
  * `Makefile`: Các lệnh chuẩn (`make doctor`, `make bootstrap`, `make db-up`, `make dev-backend`, `make dev-web`, `make test`).
  * `README.md`: Hướng dẫn khởi chạy nhanh.
* **Invariants được đáp ứng:**
  * Không rò rỉ API key hoặc secret trong config dump (`safe_dict()` tự động mask mật khẩu DB, khóa API).
  * Chế độ `mock` mặc định không yêu cầu API key DeepSeek và không thực hiện bất kỳ cuộc gọi mạng trả phí nào.
  * Thư mục lưu trữ private nằm ngoài git và có kiểm tra quyền ghi.
* **Tests đã chạy & Kết quả:**
  * `make doctor`: Tất cả 6/6 prerequisite checks PASS (macOS arm64, Python 3.12, Node v25, Docker running, Storage writable, Config typed).
  * `make test-backend`: 8/8 unit tests PASS trong 0.17s (kiểm thử cấu hình, validation lỗi khi thiếu key ở deepseek mode, mask secrets, kiểm tra health endpoints).
  * `npm run build` (apps/web): Biên dịch tĩnh Next.js PASS trong 1.4s.
  * Khởi động Docker DB & verify extension: `uuid-ossp` và `vector` hoạt động chính xác.
* **Bước tiếp theo:** B01 — Xây dựng Data model (SQLAlchemy 2 models) và migration Alembic cho toàn bộ entities trong `03-data-api-state-machines.md`.
