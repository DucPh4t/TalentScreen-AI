# TalentScreen AI — Nhật Ký Triển Khai (Implementation Progress)

Theo dõi tiến độ theo dõi thực hiện các task B00–B26 và Stage Gates G1–G7 được quy định trong `talentscreen-mvp-plan/09-implementation-backlog.md`.

---

## Tổng quan tiến độ Tasks

| Task | Tên tác vụ | Ưu tiên | Trạng thái | Ghi chú & Lệnh kiểm thử |
|---|---|---|---|---|
| **B00** | Khởi tạo monorepo, doctor và cấu hình | P0 | **COMPLETED** | `make doctor`, `make test-backend`, Next.js build pass |
| **B01** | Data model, migration và domain enums | P0 | **COMPLETED** | 35 tables created, Alembic migrations pass, 6 integration tests on real PostgreSQL pass |
| **B02** | Authentication, session, CSRF và authorization | P0 | **COMPLETED** | Argon2id, HttpOnly session, CSRF check, RBAC & Requisition guards, 21 tests pass |
| **B03** | Requisition và JD version | P0 | **COMPLETED** | Lifecycle, optimistic locking (409), JD immutability & egress approval, 28 tests pass |
| **B04** | Rubric seed, editor, approval và policy | P0 | **COMPLETED** | Seed 6 criteria, sum=100, anchors 0..4, anti-bias policy, immutability, 32 tests pass |
| **B05** | Intake upload và private storage | P0 | **COMPLETED** | Storage manager, path traversal guards, MIME/magic checks, idempotency, 38 tests pass |
| **B06** | Parse PDF, normalization và provenance | P0 | **COMPLETED** | PDF/DOCX parser, NFC/LF normalization, Source Span Registry, 43 tests pass |
| **B07** | Durable PostgreSQL worker | P0 | *READY* | Sẵn sàng triển khai PostgreSQL Queue Worker & Fencing |
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

### B01 — Data model, migration và domain enums
* **Thời điểm hoàn thành:** 2026-09-26
* **Files đã tạo & cập nhật:**
  * `app/db/base.py`: DeclarativeBase, `PrimaryKeyMixin` (UUID v4), `TimestampMixin` (UTC `DateTime`), `RowVersionMixin` (optimistic locking).
  * `app/db/models/org_user.py`: `Organization`, `User`, `UserAccountRole`, `SessionRecord`, `OnboardingProgress`.
  * `app/db/models/requisition.py`: `Requisition`, `RequisitionMembership`, `JDVersion`, `RubricVersion`, `RubricCriterion`.
  * `app/db/models/candidate.py`: `Candidate`, `CandidateIdentity`, `Application`, `RawAccessGrant`.
  * `app/db/models/document.py`: `Document`, `SanitizedVersion`, `SourceSpan`, `RetrievalChunk` (tích hợp `pgvector.sqlalchemy.Vector(768)`).
  * `app/db/models/assessment.py`: `AssessmentRun`, `CriterionAssessment`, `CriterionEvidence`, `HRRevision`.
  * `app/db/models/decision.py`: `ReviewAttestation`, `Decision`.
  * `app/db/models/interview.py`: `InterviewQuestionBank`, `InterviewDraft`, `InterviewRevision`.
  * `app/db/models/ops.py`: `Job` (queue), `LLMInvocation`, `BudgetPeriod`, `BudgetReservation`, `IdempotencyRecord`, `AuditEvent`, `DeletionRequest`.
  * `app/db/models/__init__.py`: Export toàn bộ 35 models phục vụ Alembic autogenerate và queries.
  * `app/db/session.py`: Async engine, sessionmaker và FastAPI dependency `get_db`.
  * `alembic.ini` & `services/backend/alembic/`: Cấu hình async migrations, template `script.py.mako` tự động import `pgvector`, sinh migration `43bc71851f0e_initial_schema.py`.
  * `services/backend/tests/conftest.py`: Fixture `test_session_factory` với `NullPool` kiểm thử cô lập trên PostgreSQL.
  * `services/backend/tests/test_db_models.py`: Bộ kiểm thử tích hợp trên PostgreSQL thật với pgvector query.
* **Invariants được đáp ứng:**
  * Toàn bộ 35 bảng nghiệp vụ được thiết lập đầy đủ khóa chính UUID, FK, indexes và ràng buộc unique.
  * `Candidate` và `CandidateIdentity` tách rời; danh tính cá nhân không đưa vào candidate hay tiêu chí chấm điểm.
  * Ràng buộc Unique `(requisition_id, candidate_id)` ngăn trùng lặp đơn ứng tuyển.
  * Ràng buộc Unique `(actor_id, method, route_scope, key)` cho bảng Idempotency.
  * Ràng buộc Unique `(requisition_id, version_no)` cho JD and Rubric versions.
  * Tích hợp cột vector 768 chiều cho `RetrievalChunk` và truy vấn khoảng cách cosine của `pgvector`.
* **Tests đã chạy & Kết quả:**
  * `alembic upgrade head`: Áp dụng thành công toàn bộ 35 bảng vào cơ sở dữ liệu PostgreSQL 16 + pgvector container.
  * `make test`: **14/14 tests PASS (100%)** trong 0.49s.
  * Next.js build: PASS.
* **Bước tiếp theo:** B02 — Authentication, session, CSRF và authorization (Argon2id, HttpOnly session cookie, RBAC + Requisition Membership, Raw CV grant guards).

### B02 — Authentication, session, CSRF và authorization
* **Thời điểm hoàn thành:** 2026-09-26
* **Files đã tạo & cập nhật:**
  * `app/domain/security.py`: Argon2id password hasher với constant-time verification, cryptographic token generation (32 bytes) và SHA-256 digest hashing.
  * `app/services/auth.py`: Nghiệp vụ xác thực người dùng, tạo phiên (session cookie + CSRF token), kiểm tra thời hạn idle (30m), thời hạn tuyệt đối (8h), kiểm tra `session_generation` ngăn chặn session cũ sau khi đổi mật khẩu/đăng xuất toàn cầu, thu hồi phiên đơn lẻ và thu hồi toàn bộ phiên của người dùng.
  * `app/domain/authorization.py`: Model `AuthenticatedContext`, dependency FastAPI `get_current_context` tự động phân giải session cookie và xác thực CSRF trên mutation methods (POST, PUT, PATCH, DELETE). Factory `require_role(role)` bảo vệ endpoint. Hàm `check_requisition_membership()` kiểm tra quyền trên Requisition (OWNER/REVIEWER). Hàm `check_raw_access_grant()` bắt buộc có `RawAccessGrant` còn hạn chưa bị thu hồi để đọc raw CV, áp dụng tuyệt đối cho cả Admin lẫn Recruiter.
  * `app/api/v1/auth.py`: Endpoints `/api/v1/auth/login`, `/api/v1/auth/logout`, `/api/v1/auth/me`. Cookie session thiết lập `HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age=8h`.
  * `app/cli.py`: CLI quản trị hệ thống (`create-admin`, `disable-user`, `list-users`) có guard bảo vệ không bao giờ được vô hiệu hóa admin duy nhất cuối cùng.
  * `services/backend/tests/test_auth.py`: 7 tests bao quát bảo mật: hashing Argon2id, luồng đăng nhập + HttpOnly cookie, thông báo lỗi generic chống dò quét tài khoản, bắt buộc CSRF trên mutation, thu hồi phiên và đăng xuất toàn cầu, bảo vệ Raw Access Grant, phân quyền Requisition Membership.
* **Invariants được đáp ứng:**
  * SEC-01: Mật khẩu lưu dưới dạng Argon2id, không lưu plain text.
  * SEC-02: Session ID sinh ngẫu nhiên 32 bytes cryptographically secure, chỉ lưu SHA-256 hash trong DB.
  * SEC-03: Cookie `HttpOnly` ngăn chặn XSS đánh cắp session.
  * SEC-04: CSRF token bắt buộc trên tất cả mutation requests (POST/PUT/PATCH/DELETE).
  * SEC-05: Raw CV Access Grant bắt buộc cho mọi vai trò (kể cả Admin) khi muốn truy cập tài liệu gốc chưa ẩn danh.
  * SEC-06: Bảo vệ tài khoản Admin cuối cùng khỏi bị disable hoặc xóa vai trò.
* **Tests đã chạy & Kết quả:**
  * `pytest services/backend/tests`: **21/21 tests PASS (100%)** trong 1.58s.
  * CLI bootstrap admin và list-users: Thành công.
* **Bước tiếp theo:** B03 — Requisition và JD version (Tạo & quản lý yêu cầu tuyển dụng, quản lý phiên bản JD Draft -> In Review -> Approved -> Archived, kiểm tra vai trò OWNER/REVIEWER).

### B03 — Requisition và JD version
* **Thời điểm hoàn thành:** 2026-09-26
* **Files đã tạo & cập nhật:**
  * `app/services/audit.py`: Helper `record_audit_event()` lưu vết bất biến mọi hành động nghiệp vụ vào `audit_events` (action, entity_id, actor, version, safe_metadata).
  * `app/schemas/requisition.py`: Pydantic DTOs cho Requisition, Membership, JD Version, Egress Approval với type safety và validation.
  * `app/services/requisition.py`:
    * Nghiệp vụ Requisition: Tạo mới (mặc định DRAFT, recruiter tự thành OWNER), xem chi tiết kèm các số liệu đếm (counts: applications, jd_versions, rubric_versions, members), phân quyền truy cập Requisition (cô lập giữa các recruiter/reviewer, admin có quyền xem tổng thể).
    * Phân quyền & Thành viên Requisition: Thêm/cập nhật vai trò (OWNER/REVIEWER), xóa thành viên, thu hồi toàn bộ raw grants liên quan khi xóa thành viên, bảo vệ không cho phép xóa OWNER duy nhất cuối cùng (`CANNOT_REMOVE_LAST_OWNER`).
    * State machine Requisition (Section 5.1):
      * `DRAFT -> OPEN`: Bắt buộc có JD và Rubric phiên bản hiện hành đã APPROVED và khớp với JD hiện tại; ghi nhận `opened_at`.
      * `OPEN -> PAUSED`: Bắt buộc cung cấp lý do (`reason`).
      * `PAUSED -> OPEN`: Kiểm tra rubric hiện hành hợp lệ.
      * `OPEN|PAUSED -> CLOSED`: Bắt buộc lý do; ghi nhận `closed_at`.
      * `CLOSED -> PAUSED`: Bắt buộc lý do mở lại; chặn nhảy trực tiếp từ `CLOSED -> OPEN`.
    * Optimistic Locking: Kiểm tra `row_version` qua body `expected_version` hoặc HTTP header `If-Match`; trả mã HTTP 409 Conflict (`VERSION_CONFLICT`) khi có tranh chấp sửa đổi đồng thời.
    * Quản lý JD Version bất biến (Immutable): Chuẩn hóa Unicode NFC, tính mã SHA-256 `text_hash`, tự động bóc tách requirement citations (`JD-PY-01`, `JD-API-01`,...) vào `source_refs`, tăng số phiên bản `version_no`, cập nhật con trỏ `current_jd_version_id`. Chỉ OWNER mới có quyền cập nhật JD.
    * Kiểm duyệt JD trước khi gửi LLM (`approve-egress`): OWNER phê duyệt kiểm tra nội dung JD với xác nhận `acknowledged=True` và đối soát mã hash `expected_text_hash == jd.text_hash`.
  * `app/api/v1/requisitions.py`: REST API endpoints đầy đủ (`GET/POST /requisitions`, `GET/PATCH /requisitions/{id}`, `GET/PUT/DELETE /requisitions/{id}/members`, `POST/GET /requisitions/{id}/jd-versions`, `GET /jd-versions/{id}`, `POST /jd-versions/{id}/approve-egress`).
  * `services/backend/tests/test_requisitions.py`: 7 test cases tích hợp trên PostgreSQL thật kiểm tra cô lập phân quyền, guard không cho xóa last owner, trích xuất requirements từ markdown tiếng Việt, kiểm tra optimistic locking trả 409 Conflict, state machine chuyển trạng thái và luồng approve egress.
* **Invariants được đáp ứng:**
  * Chỉ OWNER mới có quyền thay đổi JD hoặc duyệt approve-egress.
  * Lịch sử các phiên bản JD được lưu bất biến, các lần chạy đánh giá cũ vẫn giữ nguyên liên kết tham chiếu tới JD version tương ứng.
  * Phản hồi lỗi 409 Conflict khi phát hiện sửa đổi đồng thời.
  * Luôn duy trì ít nhất một OWNER cho mỗi Requisition.
* **Tests đã chạy & Kết quả:**
  * `pytest services/backend/tests`: **28/28 tests PASS (100%)** trong 3.55s.
  * Next.js build: Static pages generated thành công (4/4) trong 462ms.
* **Bước tiếp theo:** B04 — Rubric seed, editor, approval và policy (Import seed 6 criterion chuẩn, kiểm tra weights=100, anchors 0..4, policy threshold 70, core floor 2, kiểm tra cấm tiêu chí phân biệt đối xử).

### B04 — Rubric seed, editor, approval và policy
* **Thời điểm hoàn thành:** 2026-09-26
* **Files đã tạo & cập nhật:**
  * `app/domain/rubric_policy.py`: Validator nghiệp vụ cho Rubric: kiểm tra danh sách 6 tiêu chí hợp lệ (`python_backend`, `api_design`, `sql_data`, `testing_debugging`, `security_privacy`, `delivery_ops`), kiểm tra tổng trọng số bắt buộc đúng 100%, kiểm tra anchors 0..4, và thuật toán quét cấm tiêu chí phân biệt đối xử (`FORBIDDEN_CRITERION_DETECTED` phát hiện tuổi, giới tính, hôn nhân, tôn giáo, quê quán, ảnh, danh tiếng trường top, năm tốt nghiệp).
  * `app/schemas/rubric.py`: DTOs Pydantic typed cho Rubric, Criteria, Scoring Anchors 0..4, Source Requirement Citations, Recommendation Policy và payload Approve Rubric.
  * `app/services/rubric.py`:
    * Import seed draft từ `talentscreen-mvp-plan/examples/rubric-backend-python.v1.json`, tạo Rubric version ở trạng thái DRAFT (bảo đảm invariant: seed/AI draft không bao giờ tự động được coi là approved).
    * Hỗ trợ tạo rubric qua 3 cơ chế: `seed`, `clone` từ bản rubric cũ, hoặc `manual`.
    * Tính toán mã hash nội dung `content_hash` (SHA-256) chuẩn hóa để phát hiện thay đổi.
    * Editor chỉnh sửa Rubric DRAFT: Validate toàn vẹn cấu trúc và chống phân biệt đối xử trước khi ghi nhận.
    * Invariant bất biến: Rubric sau khi đã APPROVED hoặc SUPERSEDED tuyệt đối không thể chỉnh sửa (`RUBRIC_IMMUTABLE`). Muốn sửa phải clone hoặc tạo version mới.
    * Phê duyệt Rubric (`approve`): Kiểm tra con trỏ JD version hiện tại của Requisition khớp với Rubric, kiểm tra `expected_requisition_version` (optimistic locking), bắt buộc HR xác nhận ngưỡng điểm (`acknowledge_thresholds=True` cho threshold 70 và core floor 2). Tự động chuyển rubric đã duyệt trước đó sang `SUPERSEDED`, chuyển rubric này sang `APPROVED`, trỏ `current_rubric_version_id` của Requisition và tăng `row_version`.
  * `app/api/v1/rubrics.py`: REST endpoints (`POST /requisitions/{id}/rubrics`, `GET /rubrics/{id}`, `PUT /rubrics/{id}`, `POST /rubrics/{id}/approve`).
  * `services/backend/tests/test_rubrics.py`: 4 test cases kiểm thử import seed 6 tiêu chí chuẩn, phân quyền chặn Reviewer duyệt/sửa rubric, kiểm tra các lỗi validation (thiếu tiêu chí, trùng lặp, tổng trọng số != 100%, phát hiện tiêu chí phân biệt đối xử), và luồng approve rubric kèm tính bất biến sau khi duyệt.
* **Invariants được đáp ứng:**
  * AI/Seed draft không bao giờ được coi là approved tự động; phải có HR Owner duyệt.
  * Đúng 6 criterion IDs cố định; tổng trọng số đúng 100%; đủ anchor 0..4.
  * Cấm tuyệt đối các tiêu chí và anchor chứa yếu tố thiên vị, nhân khẩu học hoặc phân biệt đối xử.
  * Rubric đã APPROVED là bất biến (immutable).
* **Tests đã chạy & Kết quả:**
  * `pytest services/backend/tests`: **32/32 tests PASS (100%)** trong 4.86s.
  * Next.js build: PASS.
* **Bước tiếp theo:** B05 — Intake upload và private storage (Tiếp nhận hồ sơ ứng viên, lưu trữ an toàn trong private storage, MIME/magic byte checks, quarantine, hạn chế dung lượng, idempotency).

### B05 — Intake upload và private storage
* **Thời điểm hoàn thành:** 2026-09-26
* **Files đã tạo & cập nhật:**
  * `app/services/storage.py`: Trình quản lý lưu trữ blob riêng tư an toàn (`get_storage_base_dir`, `resolve_blob_path`, `detect_and_validate_file_type`, `sanitize_filename`, `save_private_blob`, `read_private_blob`, `delete_private_blob`).
    * Chống tấn công Path Traversal: Khử `..`, `\`, `/`, ký tự điều khiển và null bytes; ép buộc mọi đường dẫn phải nằm bên trong `PRIVATE_STORAGE_ROOT`.
    * Kiểm tra định dạng theo Magic Bytes và phần mở rộng: Chỉ chấp nhận PDF (`%PDF-` và `.pdf`) hoặc DOCX (`PK\x03\x04` và `.docx`). Chặn đứng tập tin giả mạo phần mở rộng (fake extension).
    * Giới hạn kích thước tập tin: Chặn tập tin rỗng 0 bytes (`EMPTY_FILE` 422) và tập tin vượt quá 10MB (`FILE_TOO_LARGE` 413).
  * `app/services/idempotency.py`: Cơ chế idempotency an toàn (`get_or_start_idempotency`, `complete_idempotency`). Sử dụng bảng `idempotency_records` với unique key `(actor_id, method, route_scope, key)` và hash SHA-256 nội dung request. Khi resubmit cùng Idempotency-Key, hệ thống trả lại kết quả đã cache mà không tạo bản ghi trùng lặp hoặc tăng generation.
  * `app/schemas/intake.py`: DTOs Pydantic cho tạo Application, danh sách hồ sơ (chỉ lộ `public_label` như `CAND-XXXXXX`), upload document và chi tiết Application.
  * `app/services/intake.py`:
    * Nghiệp vụ tiếp nhận hồ sơ: Tạo Candidate mới với nhãn ẩn danh tự sinh (`public_label`), gắn Application vào Requisition, chặn tạo đơn trùng cho cùng Candidate trên Requisition (`APPLICATION_ALREADY_EXISTS`), chặn tạo đơn khi Requisition đã đóng.
    * Tải lên tài liệu ứng viên: Lưu trữ vào `private_storage/documents/{application_id}/{doc_id}.bin`, tính mã hash SHA-256 chống trùng lặp trong cùng hồ sơ (`DOCUMENT_ALREADY_CURRENT`), tăng `generation` và `row_version` của Application, xóa con trỏ `current_sanitized_version_id` (buộc phải kiểm duyệt ẩn danh lại tài liệu mới), đưa Job vào hàng đợi bền vững `Job(type=JobType.INGEST_DOCUMENT, status=JobStatus.QUEUED)`.
    * Quyền riêng tư: Tên tập tin gốc (`original_filename`) chỉ được trả về khi người dùng có `RawAccessGrant` còn hiệu lực mang scope `raw_cv`.
  * `app/api/v1/intake.py`: REST API endpoints (`GET /requisitions/{id}/applications`, `POST /requisitions/{id}/applications`, `GET /applications/{id}`, `GET /applications/{id}/documents`, `POST /applications/{id}/documents` trả HTTP 202 Accepted).
  * `services/backend/tests/test_intake.py`: 6 integration test cases kiểm thử tạo Application với public label, upload PDF & DOCX thành công và sinh Job hàng đợi, từ chối file rỗng, quá cỡ và fake extension, kiểm tra Idempotency-Key không tạo đơn lặp, bảo vệ che giấu tên file gốc khi thiếu RawAccessGrant, và path traversal guards.
* **Invariants được đáp ứng:**
  * File CV gốc được lưu trữ trong thư mục private riêng biệt, không có URL công khai, không serialize blob_key ra API response thông thường.
  * Tên và thông tin cá nhân ứng viên hoàn toàn tách biệt khỏi luồng đánh giá thông qua nhãn ẩn danh `public_label`.
  * Cơ chế Idempotency đảm bảo tính một lần (exactly-once) khi mạng bị chập chờn.
  * Job xử lý ingestion được ghi bền vững vào cơ sở dữ liệu trước khi trả về HTTP 202 cho client.
* **Tests đã chạy & Kết quả:**
  * `pytest services/backend/tests`: **38/38 tests PASS (100%)** trong 6.45s.
  * Next.js build: PASS.
* **Bước tiếp theo:** B06 — Parse PDF, normalization và provenance (Bộ bóc tách text chuẩn hóa Unicode NFC/LF, trích xuất metadata trang, đăng ký Source Span Registry và kiểm tra chất lượng trích xuất).

### B06 — Parse PDF, normalization và provenance
* **Thời điểm hoàn thành:** 2026-09-26
* **Files đã tạo & cập nhật:**
  * `app/services/parser.py`: Bộ bóc tách đa định dạng (`parse_pdf_bytes` bằng `pypdf`, `parse_docx_bytes` bằng `python-docx`, `parse_document_content`).
    * Chuẩn hóa văn bản `normalize_to_nfc_lf`: Khử ký tự điều khiển lạ, thống nhất xuống dòng LF (`\n`), chuyển đổi triệt để dạng phân tách (NFD) sang dạng tổ hợp chuẩn Unicode NFC.
    * Bóc tách Source Spans (`build_spans_from_pages`): Chia văn bản thành các khối đoạn văn/câu có ý nghĩa, lưu lại số trang gốc (`page_number`), tự động nhận diện tiêu đề mục tiếng Việt (`section_label` như "Kinh nghiệm làm việc", "Dự án", "Kỹ năng chuyên môn", "Học vấn"), tính toán mã hash SHA-256 (`full_hash`) và sinh ID định dạng `spn_{24hex}`.
    * Invariant bất biến tuyệt đối: Tọa độ codepoint `[start_cp:end_cp]` trong hệ trục `unicode_codepoints_nfc_lf` đối chiếu trực tiếp `canonical_text[start_cp:end_cp] == span.text` đạt 100% khớp, không phụ thuộc LLM để tái dựng trích dẫn.
    * Chẩn đoán chất lượng văn bản `compute_quality_report`: Phát hiện PDF scan/ảnh (`suspected_scanned`), đếm trang trống, tính số ký tự trung bình/trang.
    * Xử lý lỗi an toàn: Bắt lỗi PDF có mật khẩu (`ENCRYPTED_PDF`), PDF hỏng (`MALFORMED_PDF`) mà không gây crash tiến trình.
  * `app/services/provenance.py`: Dịch vụ điều phối bóc tách và lưu trữ provenance (`ingest_and_parse_document`, `get_source_span`).
    * Tạo `SanitizedVersion` ở trạng thái DRAFT từ nội dung bóc tách ban đầu.
    * Lưu toàn bộ các spans vào bảng `source_spans`.
    * Cập nhật `Document.ingestion_status = "parsed"`, `safety_status = DocumentSafetyStatus.PASSED`, và gán `Application.current_sanitized_version_id`.
    * Truy vấn Source Span có bảo vệ phân quyền: Kiểm tra người dùng thuộc Requisition, nếu phiên bản bị REVOKED thì chỉ người có `RawAccessGrant` mới được xem.
  * `app/schemas/intake.py`: Thêm `SourceSpanResponse` DTO phục vụ endpoint tra cứu evidence provenance.
  * `app/api/v1/intake.py`: Thêm endpoint `GET /api/v1/source-spans/{span_id}`.
  * `services/backend/pyproject.toml`: Bổ sung `pypdf>=5.0.0` và `python-docx>=1.1.0`.
  * `services/backend/tests/test_parser.py`: 5 test cases bao quát: chuẩn hóa NFD sang NFC và đổi CRLF thành LF, bảo toàn chính xác tọa độ codepoints với tiếng Việt có dấu và emoji, phát hiện PDF có mật khẩu bảo vệ (`ENCRYPTED_PDF`), bóc tách DOCX, và luồng end-to-end lưu trữ + tra cứu Source Span qua REST API kèm phân quyền.
* **Invariants được đáp ứng:**
  * Toàn bộ tọa độ codepoint offsets trong `source_spans` đối chiếu khớp 100% với văn bản chuẩn hóa.
  * Trích dẫn nguồn minh chứng không dựa vào việc LLM tự sinh offset hoặc tự nhớ lại.
  * PDF được mã hóa không thể giải mã sẽ bị từ chối với mã lỗi an toàn, không rò rỉ dữ liệu hoặc crash worker.
* **Tests đã chạy & Kết quả:**
  * `pytest services/backend/tests`: **43/43 tests PASS (100%)** trong 6.70s.
  * Next.js build: PASS.
* **Bước tiếp theo:** B07 — Durable PostgreSQL worker (Hàng đợi tác vụ bất đồng bộ trên PostgreSQL, cơ chế claim/heartbeat/lease/fencing chống tranh chấp, retry schedule, cancellation và sweeper phục hồi).
