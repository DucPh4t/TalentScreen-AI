# TalentScreen AI — Nhật Ký Triển Khai (Implementation Progress)

Theo dõi mã đã triển khai của B00–B26 và các điều kiện nghiệm thu trong `talentscreen-mvp-plan/09-implementation-backlog.md`. Các mục “COMPLETED” ở nhật ký chi tiết bên dưới là ghi nhận lịch sử commit/test lúc viết, **không đồng nghĩa G1–G7 đã PASS**. Bảng sau là trạng thái hiện tại; xem `docs/runbooks/pilot_calibration_and_shadow.md` để biết bằng chứng còn thiếu.

---

## Tổng quan tiến độ Tasks

| Task | Tên tác vụ | Ưu tiên | Trạng thái | Ghi chú & Lệnh kiểm thử |
|---|---|---|---|---|
| **B00** | Khởi tạo monorepo, doctor và cấu hình | P0 | IMPLEMENTED; ACCEPTANCE PENDING | `make doctor`, `make test-backend`, Next.js build pass |
| **B01** | Data model, migration và domain enums | P0 | IMPLEMENTED; ACCEPTANCE PENDING | 35 tables created, Alembic migrations pass, 6 integration tests on real PostgreSQL pass |
| **B02** | Authentication, session, CSRF và authorization | P0 | IMPLEMENTED; ACCEPTANCE PENDING | Argon2id, HttpOnly session, CSRF check, RBAC & Requisition guards, 21 tests pass |
| **B03** | Requisition và JD version | P0 | IMPLEMENTED; ACCEPTANCE PENDING | Lifecycle, optimistic locking (409), JD immutability & egress approval, 28 tests pass |
| **B04** | Rubric seed, editor, approval và policy | P0 | IMPLEMENTED; ACCEPTANCE PENDING | Seed 6 criteria, sum=100, anchors 0..4, anti-bias policy, immutability, 32 tests pass |
| **B05** | Intake upload và private storage | P0 | IMPLEMENTED; ACCEPTANCE PENDING | Storage manager, path traversal guards, MIME/magic checks, idempotency, 38 tests pass |
| **B06** | Parse PDF, normalization và provenance | P0 | IMPLEMENTED; ACCEPTANCE PENDING | PDF/DOCX parser, NFC/LF normalization, Source Span Registry, 43 tests pass |
| **B07** | Durable PostgreSQL worker | P0 | IMPLEMENTED; ACCEPTANCE PENDING | Xem mã, test và gate tương ứng; chưa nghiệm thu pilot |
| **B08** | Sanitization, HR approval và source viewer | P0 | IMPLEMENTED; ACCEPTANCE PENDING | Xem mã, test và gate tương ứng; chưa nghiệm thu pilot |
| **B09** | DeepSeek adapter, capabilities và cost ledger | P0 | IMPLEMENTED; ACCEPTANCE PENDING | Xem mã, test và gate tương ứng; chưa nghiệm thu pilot |
| **B10** | Full-text assessment baseline & output validation | P0 | IMPLEMENTED; ACCEPTANCE PENDING | Xem mã, test và gate tương ứng; chưa nghiệm thu pilot |
| **B11** | Deterministic scoring/recommendation engine | P0 | IMPLEMENTED; ACCEPTANCE PENDING | Xem mã, test và gate tương ứng; chưa nghiệm thu pilot |
| **B12** | Review workspace và danh sách ứng viên | P0 | IMPLEMENTED; ACCEPTANCE PENDING | Xem mã, test và gate tương ứng; chưa nghiệm thu pilot |
| **B13** | HR revision, attestation, decision và audit | P0 | IMPLEMENTED; ACCEPTANCE PENDING | Xem mã, test và gate tương ứng; chưa nghiệm thu pilot |
| **B14** | Rubric Agent và Interview Agent | P0 | IMPLEMENTED; ACCEPTANCE PENDING | Xem mã, test và gate tương ứng; chưa nghiệm thu pilot |
| **B15** | Local OCR và DOCX rendering | P1 | PARTIAL: RENDER VALIDATION | Xem mã, test và gate tương ứng; chưa nghiệm thu pilot |
| **B16** | Local multilingual embeddings & hybrid retrieval | P1 | PROTOTYPE: BENCHMARK PENDING | Xem mã, test và gate tương ứng; chưa nghiệm thu pilot |
| **B17** | Deletion, retention và data inventory | P0 | IMPLEMENTED; ACCEPTANCE PENDING | Xem mã, test và gate tương ứng; chưa nghiệm thu pilot |
| **B18** | Dataset bootstrap và fixture factory | P0 | PARTIAL: 12 UNLABELED DEV | Xem mã, test và gate tương ứng; chưa nghiệm thu pilot |
| **B19** | Evaluation harness, metrics và HR annotation | P0 | PARTIAL: HR LABELS PENDING | Xem mã, test và gate tương ứng; chưa nghiệm thu pilot |
| **B20** | Prompt regression và release/rollback | P0 | PARTIAL: OUTPUT A/B PENDING | Xem mã, test và gate tương ứng; chưa nghiệm thu pilot |
| **B21** | Sandbox onboarding và help UI | P0 | IMPLEMENTED; HR UAT PENDING | Xem mã, test và gate tương ứng; chưa nghiệm thu pilot |
| **B22** | Security regression và privacy review kỹ thuật | P0 | IMPLEMENTED; CI PENDING | Xem mã, test và gate tương ứng; chưa nghiệm thu pilot |
| **B23** | Observability, load và budget operations | P0 | IMPLEMENTED; SLO MEASUREMENT PENDING | Xem mã, test và gate tương ứng; chưa nghiệm thu pilot |
| **B24** | Packaging, backup và restore | P0 | IMPLEMENTED; DRILL EVIDENCE PENDING | Xem mã, test và gate tương ứng; chưa nghiệm thu pilot |
| **B25** | HR calibration, shadow và pilot gate | P0 | PENDING: CALIBRATION & SHADOW | Xem mã, test và gate tương ứng; chưa nghiệm thu pilot |
| **B26** | Sửa lỗi còn lại và bàn giao vận hành | P0 | PENDING: PILOT SIGN-OFF | Xem mã, test và gate tương ứng; chưa nghiệm thu pilot |

### Điều chỉnh sau rà soát

- B18: 12 family ban đầu thuộc dev, trong đó 10 family là smoke subset. Chưa có holdout. Các trường điểm synthetic không dùng rubric thật và PDF chỉ chứa 200 ký tự đầu đã được bỏ; fixture hiện chưa có nhãn HR.
- B19/B20: Evaluation yêu cầu file dự đoán thực và nhãn độc lập; prompt có hash và bộ so sánh A/B cùng sample IDs. Chưa có báo cáo chất lượng DeepSeek/HR.
- B15/B16: DOCX đếm trang từ bản render LibreOffice; thiếu renderer bị từ chối. Lexical retrieval dùng PostgreSQL full-text `simple`; benchmark hybrid so với full-text baseline còn chờ.
- B25/B26: G1–G7 đều cần bằng chứng theo giai đoạn và HR/IT sign-off. Không dùng nhãn PASS trong runbook cũ làm chứng cứ nghiệm thu.

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

### B12 UI — Candidate Listing, Review Workspace, and Decision Flow
* **Thời điểm hoàn thành:** 2026-09-26
* **Files đã tạo & cập nhật:**
  * `apps/web/src/lib/api.ts`: Typed client tương tác đầy đủ với FastAPI backend:
    * Quản lý phiên cookie HttpOnly & tự động đính kèm `X-CSRF-Token` cho toàn bộ các phương thức thay đổi dữ liệu (`POST`, `PUT`, `PATCH`, `DELETE`).
    * Endpoints: Requisitions (listing, creation, optimistic concurrency patch với `If-Match`), Applications (FIFO listing theo `received_at`, detail, CV upload FormData), Sanitization (detail, approve, revoke quarantine), Assessment (trigger run, fetch criteria & evidence), HR Revision (draft, update, finalize), Attested Hiring Decisions (ReviewAttestation checklist, immutable decision creation), Interview Guide (question bank, draft generation, follow-up revisions), Deletion Request (immediate tombstone, physical unlinking).
  * `apps/web/src/app/globals.css`: Toàn bộ design system hiện đại theo chuẩn web: bảng màu dark mode chuyên nghiệp (accent glow `#6366f1`, emerald `#10b981`, amber `#f59e0b`, rose `#ef4444`), typography sắc nét, responsive tables, cards, tabs, badges, quote drawer modal, redaction span tokens.
  * `apps/web/src/app/layout.tsx`: Layout gốc tích hợp environment banner, thanh điều hướng chính (Tổng quan, Đợt tuyển dụng, Hồ sơ ứng viên, Chính sách & Bảo mật).
  * `apps/web/src/app/page.tsx`: Màn hình đăng nhập Argon2id, thống kê trực quan (đợt tuyển dụng, hồ sơ, bằng chứng đối chiếu, bảo vệ PII).
  * `apps/web/src/app/requisitions/page.tsx`: Danh sách đợt tuyển dụng với bộ lọc trạng thái, modal tạo đợt tuyển dụng kèm JD và phân bổ phòng ban.
  * `apps/web/src/app/requisitions/[id]/page.tsx`: Không gian quản lý đợt tuyển dụng:
    * Tab 1: Danh sách hồ sơ ứng viên sắp xếp theo thời gian nộp tăng dần (FIFO per Spec 01) nhằm đảm bảo tính công bằng và không thiên vị điểm số. Modal tiếp nhận hồ sơ CV hỗ trợ PDF/DOCX tối đa 10MB kèm kiểm tra nhanh client-side.
    * Tab 2: Hiển thị văn bản Job Description chuẩn hóa và bảng 6 tiêu chí Rubric chuẩn (trọng số, ngưỡng sàn 2.0, anchors 0..4). Nút khởi tạo Rubric mẫu và phê duyệt chính thức dành cho Owner.
  * `apps/web/src/app/applications/[id]/page.tsx`: Không gian xét duyệt hồ sơ ứng viên (Candidate Review Workspace) tuân thủ nghiêm ngặt Spec 01:
    * Không có banner điểm số lớn (No Hero Score).
    * Tab 1: Khử định danh PII (Sanitization Viewer hiển thị các token `[REDACTED_...]`, xác nhận cam kết và nút phê duyệt/thu hồi của Owner).
    * Tab 2: Đánh giá & Bằng chứng thực tế (Evidence-First Assessment, bảng 6 tiêu chí chuẩn, rationale chi tiết, trích dẫn nguyên văn kèm mã span và codepoint offsets; bấm vào trích dẫn mở Quote Drawer đối chiếu). Bảng tổng hợp tính toán điểm quan sát/so sánh có thể thu gọn.
    * Tab 3: Hiệu chỉnh HR & Quyết định tuyển dụng chính thức (HR Revision form cho phép override điểm và ghi rõ lý do; Attested Hiring Decision form yêu cầu Owner cam kết đủ 3 điều khoản ký duyệt trước khi ban hành).
    * Tab 4: Kế hoạch phỏng vấn & Đào sâu (Bộ câu hỏi chuẩn từ Ngân hàng Rubric + tối đa 3 câu hỏi đào sâu do AI gợi ý hướng tới các lỗ hổng bằng chứng).
    * Modal yêu cầu xóa dữ liệu vĩnh viễn (Data Deletion B17) thực thi tombstone tức thì và hủy tệp an toàn.
  * `.gitignore`: Điều chỉnh `/lib/` và `!apps/web/src/lib/` để không bỏ sót thư viện TypeScript của frontend.
* **Invariants được đáp ứng:**
  * Thứ tự hiển thị hồ sơ mặc định là FIFO (thời gian tiếp nhận), không bao giờ sắp xếp theo điểm AI để tránh định kiến ban đầu.
  * Giao diện hoàn toàn không có Hero Score hay điểm AI hiển thị áp đảo; bảng bằng chứng và trích dẫn nguyên văn luôn được đặt ở vị trí trọng tâm.
  * Phê duyệt Rubric, phê duyệt Khử định danh và Ký ban hành quyết định tuyển dụng bắt buộc phải có vai trò Owner và bản cam kết ReviewAttestation được ký.
* **Tests đã chạy & Kết quả:**
  * `npm run build` (Next.js 15.5): **Compiled successfully in 1.2s**, 5/5 static & dynamic pages sinh ra thành công không có bất kỳ lỗi TypeScript hay đóng gói nào.
  * `pytest services/backend/tests`: **86/86 tests PASS (100%)** trong 23.95s.
* **Bước tiếp theo:** B15 & B16 — Local OCR fallbacks và Local multilingual embeddings & hybrid retrieval.

### B15 — Local OCR và DOCX rendering fallbacks
* **Thời điểm hoàn thành:** 2026-09-26
* **Files đã tạo & cập nhật:**
  * `app/services/parser.py`: Bổ sung cơ chế OCR cục bộ và nâng cấp phân tích cấu trúc DOCX:
    * Tích hợp Tesseract OCR đa ngôn ngữ (`vie+eng`) qua PIL và `pytesseract` với khả năng tự động dò tìm đường dẫn thực thi của tesseract.
    * Khi bóc tách PDF, nếu trang không có text hoặc text dưới 25 ký tự nhưng có hình ảnh nhúng (`page.images`), hệ thống tự động chạy OCR trên ảnh, chuẩn hóa kết quả qua `normalize_to_nfc_lf`, xây dựng `SourceSpan` với tọa độ codepoints nguyên bản và gắn cờ `ocr_applied = True`, `quality_status = "ok_ocr_recovered"`.
    * Nâng cấp bóc tách DOCX: bảo toàn cấu trúc bảng/nhiều cột thông qua ký tự phân cách ` | `, khử trùng lặp các ô gộp (merged cells), ước tính số trang thực tế (~2000 ký tự/trang) và phát hiện vi phạm giới hạn độ dài CV (`excessive_page_count` vượt quá 10 trang theo Spec 05).
    * Quản lý lỗi kỹ thuật an toàn: Bắt lỗi tệp hỏng (`MALFORMED_PDF`, `MALFORMED_DOCX`), mã hóa có mật khẩu (`ENCRYPTED_PDF`), MIME không hỗ trợ (`UNSUPPORTED_MIME`). Văn bản scan hoàn toàn rỗng hoặc lỗi kỹ thuật không bao giờ bị biến thành "thiếu bằng chứng năng lực" (insufficient evidence), mà được ghi nhận lỗi kỹ thuật rõ ràng để HR xử lý thủ công hoặc yêu cầu thông tin lại.
  * `services/backend/pyproject.toml`: Bổ sung dependencies `pillow>=10.0.0` và `pytesseract>=0.3.10`.
  * `services/backend/tests/test_ocr_parser.py`: 6 test cases bao quát: phục hồi text từ PDF scan qua OCR và kiểm tra tính toàn vẹn của span offsets, phát hiện cảnh báo PDF rỗng/scan, bóc tách bảng và cột trong DOCX, xử lý DOCX rỗng, từ chối MIME không hỗ trợ, và chạy OCR an toàn trên dữ liệu nhị phân không hợp lệ mà không crash.
* **Invariants được đáp ứng:**
  * Toàn bộ trích dẫn phục hồi từ OCR đều tuân thủ 100% đẳng thức codepoints `canonical_text[start_cp:end_cp] == span.text`.
  * Lỗi bóc tách tài liệu không bao giờ tự động chuyển hóa thành điểm đánh giá năng lực của ứng viên.
  * Bộ nhớ đệm xử lý ảnh được giải phóng trong bộ nhớ mà không để lại tệp tạm trên đĩa.
* **Tests đã chạy & Kết quả:**
  * `pytest services/backend/tests/test_ocr_parser.py`: **6/6 tests PASS (100%)** trong 0.64s.

### B16 — Local multilingual embeddings và hybrid retrieval
* **Thời điểm hoàn thành:** 2026-09-26
* **Files đã tạo & cập nhật:**
  * `app/services/embedding.py`: Dịch vụ sinh vector embeddings cục bộ và phân mảnh (chunking) tài liệu:
    * Mô hình chuẩn hóa: Multilingual E5-base (768 chiều), chuẩn hóa L2 norm=1.0, hỗ trợ tiền tố E5 (`query: ` cho truy vấn và `passage: ` cho đoạn văn).
    * Phân mảnh ngữ nghĩa `build_chunks_from_spans`: Gom các spans lân cận trong cùng một mục (section) thành các khối ~250–350 tokens, giới hạn cứng 480 tokens, bảo toàn trọn vẹn danh sách `span_ids` để duy trì chuỗi kiểm chứng.
    * Đánh chỉ mục bền vững vào `RetrievalChunk` trong PostgreSQL thông qua `pgvector`, xóa bản ghi cũ trước khi nạp để bảo đảm tính idempotent.
  * `app/services/retrieval.py`: Dịch vụ truy vấn lai ghép (Hybrid Retrieval) kết hợp Dense + Lexical + RRF:
    * Phân lập dữ liệu nghiêm ngặt: Mọi câu truy vấn bắt buộc phải lọc theo `sanitized_version_id` và `embedding_config_id`. Nghiêm cấm đọc chéo giữa các ứng viên.
    * Dense Search: Tìm kiếm ngữ nghĩa chính xác qua toán tử khoảng cách cosine của pgvector (`cosine_distance`), lấy top 10 cho mỗi tiêu chí.
    * Lexical Search: Tìm kiếm từ khóa kỹ thuật theo `ilike` trên các chunk văn bản, lấy top 10 cho mỗi tiêu chí.
    * Hợp nhất thứ hạng RRF (Reciprocal Rank Fusion): Áp dụng công thức chuẩn $RRF(c) = \sum \frac{1}{60 + rank}$, giải quyết xung đột thứ hạng một cách xác định (deterministic tie-breaking: RRF giảm dần, sau đó theo `chunk_index` tăng dần).
    * Đóng gói bằng chứng có giới hạn: Lấy tối đa 4 chunk/tiêu chí, deterministic packing tối đa 8.000 tokens, tự động chuyển về chiến lược `fulltext_fallback` khi tài liệu không có vector hoặc không tìm thấy bằng chứng phù hợp.
  * `services/backend/tests/test_hybrid_retrieval.py`: 4 integration test cases kiểm thử: vector properties (độ dài 768, unit norm, phân biệt ngữ nghĩa), thuật toán phân mảnh spans theo section, nạp và lưu trữ `RetrievalChunk` trong pgvector, truy vấn lai ghép Dense + Lexical + RRF cho tiêu chí kỹ thuật, và cơ chế phát hiện fallback tự động.
* **Invariants được đáp ứng:**
  * Truy vấn embedding được cô lập 100% trong phạm vi hồ sơ ứng viên; không có hiện tượng rò rỉ hoặc truy vấn chéo giữa các ứng viên khác nhau.
  * Điểm tương đồng cosine và điểm RRF chỉ đóng vai trò độ phù hợp trích xuất, tuyệt đối không được coi là điểm năng lực của ứng viên.
  * Toàn bộ mã định danh `span_ids` được lưu trữ đầy đủ trong mỗi retrieval chunk.
* **Tests đã chạy & Kết quả:**
  * `pytest services/backend/tests`: **96/96 tests PASS (100%)** trong 23.97s.
  * Next.js build: **Compiled successfully in 0.5s**.
* **Bước tiếp theo:** B18, B19, B20 — Dataset bootstrap & fixture factory, Evaluation harness & metrics, Prompt regression runner.

### B18 — Dataset bootstrap và fixture factory
* **Thời điểm hoàn thành:** 2026-09-26
* **Files đã tạo & cập nhật:**
  * `scripts/fixture_factory.py`: Công cụ khởi tạo và sinh bộ fixtures tổng hợp (synthetic fixtures) độc lập:
    * 12 họ dữ liệu (families) kiểm thử tiêu biểu: đủ bằng chứng (`family_01_strong_backend_vi`), chỉ liệt kê kỹ năng (`family_02_skills_only_en`), thiếu một phần bằng chứng (`family_03_partial_evidence_vi`), phạm vi công việc hạn chế (`family_04_limited_scope_en`), song ngữ đan xen (`family_05_code_switch_mixed`), trùng lặp dự án song ngữ (`family_06_bilingual_dup`), mâu thuẫn giữa tóm tắt và kinh nghiệm (`family_07_contradiction`), tự xác nhận tiêu cực (`family_08_negative_explicit`), phòng chống tấn công prompt injection (`family_09_prompt_injection`), kiểm tra rò rỉ PII proxy (`family_10_proxy_pii`), thử thách bóc tách Unicode (`family_11_parse_stress`), và hồ sơ trái ngành (`family_12_out_of_domain`).
    * Phân chia tập kiểm thử (splits): `smoke` (10 families), `dev` (1 family), `holdout` (1 family).
    * Xuất bản tự động: định dạng JSON canonical facts, văn bản thuần `.txt`, tài liệu PDF render `.pdf`, và tệp kê khai nguồn gốc `fixtures/manifest.json` ghi nhận mã băm SHA-256 cho từng tệp.
* **Invariants được đáp ứng:**
  * Không có dữ liệu PII thật hoặc CV chưa rõ nguồn gốc được lưu trữ trong Git.
  * Mỗi family được phân chia vào duy nhất một tập split (không rò rỉ giữa dev và holdout).

### B19 — Evaluation harness, metrics và HR annotation
* **Thời điểm hoàn thành:** 2026-09-26
* **Files đã tạo & cập nhật:**
  * `scripts/eval_harness.py`: Bộ công cụ đo lường và đánh giá hiệu năng mô hình so với nhãn thiết kế/nhãn HR:
    * Mean Absolute Error (MAE): Tính sai số tuyệt đối trung bình trên các cặp điểm có thể so sánh (0..4).
    * Cohen's Kappa ($\kappa$): Đo lường độ đồng thuận phân loại trên khuyến nghị (`consider_next_round`, `needs_clarification`, `review_required`) có xử lý an toàn trường hợp đơn lớp (single class N/A).
    * Phân tích tách biệt theo ngôn ngữ (Disaggregated metrics): Đo lường độ chính xác và sai số riêng cho tiếng Việt (`vi`), tiếng Anh (`en`), và song ngữ (`mixed`).
    * Theo dõi chi phí và số lượng token: Ước tính tổng số tokens tiêu thụ và chi phí tài chính (USD).

### B20 — Prompt regression và release/rollback
* **Thời điểm hoàn thành:** 2026-09-26
* **Files đã tạo & cập nhật:**
  * `scripts/prompt_regression.py`: Công cụ kiểm thử hồi quy prompt và quản lý phát hành/rollback:
    * Quét vi phạm nhân khẩu học (Anti-discrimination scan) trên toàn bộ prompt hệ thống: Nghiêm cấm mọi đặc tính nhạy cảm ngoài ngữ cảnh phủ định/chỉ dẫn loại trừ.
    * Kiểm tra hợp đồng JSON: Bảo đảm prompt luôn yêu cầu định dạng JSON theo đúng schema.
    * Tạo bản kê khai phát hành bất biến (Release Manifest): Lưu trữ tại `releases/manifest_v1.0.0-mvp.json` kèm hướng dẫn rollback an toàn về `LLM_PROVIDER=mock`.
  * `services/backend/tests/test_eval_pipeline.py`: 5 test cases bao quát: sinh fixtures vào thư mục tạm, tính toán toán học chính xác cho MAE và Cohen's Kappa, luồng chạy evaluation harness toàn diện, kiểm thử hồi quy prompt chuẩn hóa PASS, và phát hiện kịp thời các prompt bị chèn thuộc tính nhân khẩu học nhạy cảm.
* **Invariants được đáp ứng:**
  * Toàn bộ prompt sản xuất đều tuân thủ hợp đồng AI có trách nhiệm và định dạng JSON nghiêm ngặt.
  * Bản kê khai phát hành có hướng dẫn rollback độc lập, không ghi đè lịch sử đánh giá trong quá khứ.
* **Tests đã chạy & Kết quả:**
  * `pytest services/backend/tests`: **101/101 tests PASS (100%)** trong 24.37s.
  * Next.js build: **Compiled successfully in 0.5s**.
