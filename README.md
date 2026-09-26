# TalentScreen AI — MVP Implementation

Hệ thống AI hỗ trợ HR đối chiếu CV với tiêu chí tuyển dụng (JD) đã được phê duyệt, trên cơ sở bằng chứng rõ ràng (evidence-based) và HR là người đưa ra quyết định cuối cùng (Human-in-the-Loop).

**Trạng thái:** mã MVP dùng để kiểm thử sandbox. Chưa được phê duyệt cho assisted pilot trên CV thật: cần nhãn HR chấm độc lập, holdout đủ mẫu, real-shadow, kiểm thử vận hành và ký các gate G1–G7. Xem `docs/runbooks/pilot_calibration_and_shadow.md` và `docs/evaluation-data-contract.md`.

Dự án được xây dựng theo bộ đặc tả chi tiết tại thư mục [talentscreen-mvp-plan/](talentscreen-mvp-plan/README.md).

---

## 1. Công nghệ & Kiến trúc (Tech Stack)

* **Backend:** FastAPI (Modular Monolith, Python 3.12), SQLAlchemy 2 (asyncpg), Pydantic v2.
* **Frontend:** Next.js (App Router, TypeScript, Vanilla CSS).
* **Database & Queue:** PostgreSQL 16 + `pgvector` (vector embedding), ACID job queue trên PostgreSQL (lease/heartbeat fencing).
* **AI Provider Adapter:** DeepSeek Chat Completions API qua HTTP adapter; mặc định chạy chế độ `mock` an toàn khi phát triển cục bộ.
* **Hardware & Runtime:** Tối ưu hóa cho macOS Apple Silicon M4 (khai thác PyTorch MPS cho local embedding) cùng profile Docker CPU chuẩn bị deploy.

---

## 2. Các nguyên tắc cốt lõi (Core Invariants)

1. **Không phân biệt đối xử:** Tuyệt đối không sử dụng tuổi, giới tính, quê quán, tên trường đại học, tình trạng hôn nhân để chấm điểm hoặc xếp hạng.
2. **Bảo mật dữ liệu CV:** CV gốc (`raw_cv`) không bao giờ được gửi trực tiếp cho LLM bên ngoài. CV thật bắt buộc phải qua khâu lọc thông tin định danh (Sanitization) và được HR kiểm tra, ấn duyệt bản text trước khi gọi API.
3. **Bằng chứng xác thực:** Mọi tiêu chí được chấm (`assessed`) bắt buộc phải trích dẫn nguyên văn đoạn văn bản (`source_spans`) thuộc đúng phiên bản hồ sơ.
4. **Toán học điểm số độc lập:** Thiếu thông tin (`insufficient_evidence`) có điểm `null` và không bị coi là 0 điểm. Toàn bộ điểm tổng và xếp loại do code backend tính toán theo công thức cố định, **không để LLM tự quyết định đậu/rớt**.
5. **Quyết định thuộc về con người:** AI chỉ đóng vai trò trợ lý tổng hợp bằng chứng. Quyết định tuyển dụng (`advance`, `request_information`, `not_advance`) hoàn toàn do HR phê duyệt và có lưu vết kiểm toán (Audit Log).

---

## 3. Hướng dẫn khởi chạy nhanh (Quick Start)

### Yêu cầu hệ thống
* macOS (khuyến nghị Apple Silicon M-series)
* Python >= 3.12 (khuyên dùng `uv`)
* Node.js >= 20 và npm
* Docker Desktop đang chạy
* LibreOffice (`soffice`) nếu tiếp nhận DOCX. Thiếu renderer, API từ chối DOCX với lỗi kỹ thuật rõ ràng; PDF vẫn dùng được.

### Các bước khởi chạy

1. **Kiểm tra môi trường hệ thống:**
   ```bash
   make doctor
   ```

2. **Cài đặt thư viện (nếu chưa cài):**
   ```bash
   make bootstrap
   ```

3. **Khởi động Cơ sở dữ liệu (PostgreSQL + pgvector):**
   ```bash
   make db-up
   ```

4. **Khởi chạy Backend (Terminal 1):**
   ```bash
   make dev-backend
   ```
   * Backend API chạy tại: `http://127.0.0.1:8000`
   * API Documentation (Swagger): `http://127.0.0.1:8000/docs` (chỉ mở ở chế độ sandbox)

5. **Khởi chạy Frontend (Terminal 2):**
   ```bash
   make dev-web
   ```
   * Truy cập giao diện tại: `http://localhost:3000`

6. **Chạy kiểm thử tự động:** `make test` tạo PostgreSQL/pgvector tạm thời trên một cổng riêng, chạy migration và pytest, rồi xóa container. Không dùng database ứng dụng trong `.env` để chạy test.
   ```bash
   make test
   ```

---

## 4. Tiến độ dự án (Implementation Progress)

Theo dõi chi tiết các task từ B00 đến B26 và trạng thái các Stage Gates tại [implementation-progress.md](implementation-progress.md).
