# 03 — Dữ liệu, state machine và hợp đồng REST

Áp dụng [00-scope-decisions.md](00-scope-decisions.md). Đây là đặc tả để triển khai, không phải OpenAPI đang chạy. AI implement phải sinh OpenAPI từ Pydantic/FastAPI, sinh TS client từ OpenAPI, rồi chạy contract tests; không duy trì ba bộ DTO viết tay. Trạng thái dưới đây là giá trị máy đọc chính thức, nhãn tiếng Việt do UI ánh xạ.

## 1. Quy ước chung

- REST prefix `/api/v1`, JSON dùng `snake_case`; UUID v4 cho khóa chính trừ các mã/hash được chỉ rõ. Không dùng tên/email làm identifier trong URL.
- DB dùng `timestamptz` UTC; API ISO-8601 UTC kết thúc `Z`. Giao diện hiển thị Asia/Ho_Chi_Minh. Thời gian lease/budget dùng DB clock.
- Mọi bảng nghiệp vụ có `id uuid PK`, `created_at`, `updated_at` trừ bảng liên kết/immutable event. Bảng mutable có `row_version bigint NOT NULL DEFAULT 1`, tăng mỗi mutation; bảng immutable không UPDATE payload.
- Money USD lưu `numeric(18,8)`, JSON serialize thành chuỗi decimal; token/count dùng bigint không âm. Điểm tính Decimal, API score serialize hai số lẻ còn UI hiển thị tối đa một số lẻ (half-up); điều kiện threshold so trên giá trị chưa làm tròn.
- `organization_id` là FK tới singleton organization. Tất cả FK xuyên tài liệu/application/requisition phải cùng organization và cùng context phù hợp, kiểm tra bằng service + integration tests. Không nhận `organization_id` từ browser.
- Nội dung tự do là plain text, không HTML. Tối đa title 5–200, note/reason tối đa2.000 ký tự (final decision/revision reason tối thiểu20); JD100–50.000 codepoints; mọi trường dài hơn có giới hạn riêng. `null` khác thiếu trường; PATCH thiếu trường nghĩa là giữ nguyên, trường nullable nhận null nghĩa là xóa giá trị.
- Nội dung AI không được tin như metadata do backend cung cấp. Backend tự gắn actor, run ID, source IDs đã xác minh, scores, recommendation, timestamp và version.
- `CASCADE` chỉ cho quan hệ không cần audit; purge thực hiện có inventory, không xóa lan tất cả nghiệp vụ bằng một cascade không quan sát được.

## 2. Entity map

```text
organization ─ users ─ account_roles
  └ requisition ─ memberships ─ raw_grants (bổ sung, scope application)
       ├ JD versions ─ rubric versions ─ criteria
       └ application ─ candidate ─ candidate_identity (private)
            ├ document versions ─ sanitized versions ─ source spans/chunks/vectors
            ├ assessment runs ─ criteria outcomes/evidence
            ├ HR revisions ─ review attestations ─ decisions
            └ interview drafts
jobs / invocation ledger / budget / idempotency / audit / deletion
```

Không tự merge candidate theo tên/email; người dùng chọn candidate đã biết hoặc tạo candidate mới. Một candidate có nhiều application, nhưng mỗi application thuộc đúng một requisition. Candidate bị xóa toàn bộ phải xử lý mọi application liên quan; xóa một application không mặc nhiên xóa candidate còn application khác.

## 3. Schema dữ liệu cần triển khai

Các field dưới đây thêm vào quy ước ID/time ở phần 1. Dùng enum hoặc CHECK constraint cho mọi tập giá trị hữu hạn. JSONB chỉ dùng cho cấu trúc có schema/Pydantic và version, không làm nơi chứa dữ liệu tùy ý.

### 3.1. Tài khoản, tổ chức và quyền

| Bảng | Fields / constraints quan trọng |
|---|---|
| `organizations` | `name text`, `environment sandbox\|pilot`, `pilot_stage shadow\|assisted nullable` (null khi sandbox), `stage_gate_report_refs jsonb`, `policy_config jsonb`, `policy_version text`; một row cấu hình hợp lệ mỗi deployment |
| `users` | `login_name text`, `display_name text`, `password_hash text`, `status active\|disabled`, `must_change_password bool`, `session_generation bigint`; UNIQUE normalized login; không dùng display name làm quyền |
| `user_account_roles` | PK `(user_id, role)`; role `admin\|recruiter\|reviewer`; nhiều role chỉ khi cấp rõ, có audit |
| `sessions` | `token_hash bytea UNIQUE`, `user_id FK`, `csrf_hash bytea`, `user_session_generation`, `expires_at`, `last_seen_at`, `revoked_at`; không lưu cookie plaintext |
| `requisition_memberships` | PK `(requisition_id,user_id)`, `membership_role owner\|reviewer`, `active bool`; owner yêu cầu user có recruiter role; reviewer yêu cầu recruiter hoặc reviewer role; admin không suy ra membership |
| `raw_access_grants` | `application_id`, `grantee_user_id`, `scopes text[]` subset `{raw_cv,identity}`, `granted_by`, `reason`, `expires_at`, `revoked_at`; index app/user/expiry; grant không thay membership |
| `onboarding_progress` | PK `(user_id, walkthrough_version)`; `completed_steps jsonb`, `completed_at`, `sandbox_exercise_result jsonb`; không chứa CV thật |

Một user có thể đồng thời có admin và recruiter role, nhưng owner membership và raw grant vẫn cấp riêng. Không cho xóa/disable admin hoạt động cuối cùng. Requisition đang mở phải có ít nhất một owner active; thay owner phải thực hiện atomically.

### 3.2. Tuyển dụng, candidate và tài liệu

| Bảng | Fields / constraints quan trọng |
|---|---|
| `requisitions` | `title`, `status draft\|open\|paused\|closed`, `current_jd_version_id nullable`, `current_rubric_version_id nullable`, `opened_at`, `closed_at`; index status/created_at |
| `jd_versions` | `requisition_id`, `version_no int`, `source_text text` max 50.000 codepoints, `text_hash char(64)`, `source_refs jsonb`, `egress_reviewed_by/at nullable`, `created_by`; UNIQUE `(requisition_id,version_no)`; text immutable |
| `rubric_versions` | `requisition_id`, `jd_version_id`, `version_no`, `status draft\|approved\|superseded`, `threshold_config jsonb`, `schema_version`, `content_hash`, `approved_by/at nullable`; UNIQUE req/version; approved content immutable |
| `rubric_criteria` | PK `(rubric_version_id,criterion_id)`; `label_vi`, `description_vi`, `weight smallint`, `anchors jsonb` đúng 5 mức 0..4, `jd_evidence_refs jsonb`, `bilingual_terms jsonb`; weight >0; approval kiểm tổng 100 |
| `candidates` | `organization_id`, `public_label text UNIQUE`, `status active\|deletion_pending\|deleted`; không chứa tên/email/tuổi |
| `candidate_identities` | `candidate_id PK/FK`, `name nullable`, `email nullable`, `phone nullable`, `provided_by`, `source_document_id nullable`; chỉ những trường cần liên hệ; không lưu gender/DOB/hometown riêng cho scoring |
| `applications` | `requisition_id`, `candidate_id`, `status active\|deletion_pending\|deleted`, `generation bigint`, `current_document_id nullable`, `current_sanitized_version_id nullable`, `current_assessment_run_id nullable`, `current_decision_id nullable`, `received_at`; UNIQUE `(requisition_id,candidate_id)` cho MVP; index `(req,received_at,id)` |
| `documents` | `application_id`, `version_no`, `kind=cv`, `original_name_private`, `mime_verified`, `byte_size`, `sha256`, `blob_key`, `ingestion_status`, `page_count nullable`, `rendered_pdf_blob_key nullable`, `safety_status pending\|passed\|rejected`, `parser_manifest jsonb`, `quality_report jsonb`, `raw_text_blob_key nullable`, `created_by`; UNIQUE `(app,version_no)`; checksum index không dùng để dedup xuyên quyền |
| `sanitized_versions` | `application_id`, `document_id`, `version_no`, `status draft\|approved\|superseded\|revoked`, `canonical_text text`, `sha256`, `normalizer_version`, `sanitizer_version`, `renderer_version`, `mapping_blob_key`, `quality_flags jsonb`, `approved_by/at nullable`; UNIQUE `(document,version_no)`; content immutable ngay khi tạo |
| `source_spans` | `span_id text PK` dạng `spn_` + 24 hex; `full_hash char(64)`, `sanitized_version_id`, `start_cp int`, `end_cp int`, `page_number nullable`, `section_label nullable`, `language vi\|en\|mixed\|unknown`, `text text`; UNIQUE `(sanitized_version,start_cp,end_cp)`; CHECK end>start, span dài ≤1.200 codepoints |
| `retrieval_chunks` | `sanitized_version_id`, `chunk_index`, `span_ids jsonb`, `text`, `search_document tsvector`, `embedding vector(768) nullable`, `embedding_config_id text nullable`; UNIQUE `(sanitized_version,chunk_index,embedding_config_id)` khi có embedding; GIN search index; filter version trước retrieval |

MVP giữ sáu criterion IDs trong seed ở 00; owner sửa wording/anchors/weight/threshold nhưng không thêm/xóa ID hoặc thay kiểu thang điểm. Thêm rubric topology khác cần schema/release mới. `threshold_config` có `consider_next_round_min=70`, `core_min=2`, `core_criterion_ids=[python_backend,api_design,sql_data]`; approval xác nhận chúng là cấu hình nghiệp vụ chưa được validation thực nghiệm.

DOCX không dựa vào metadata “page count” có sẵn. Chuyển sang PDF bằng local renderer được ghim version và có timeout, sau đó xác định trang/giới hạn 10 trang. Nếu renderer không sẵn sàng, trả lỗi cụ thể và đường xử lý thủ công; không giả vờ đã kiểm giới hạn trang. Raw DOCX và PDF derivative cùng chịu raw access/retention. Không lấy rendered content từ URL ngoài.

### 3.3. Assessment, HR và quyết định

| Bảng | Fields / constraints quan trọng |
|---|---|
| `release_manifests` | `version text UNIQUE`, `app_commit`, `payload jsonb`, `sha256`, `status candidate\|active\|retired`; manifest đã được run tham chiếu bất biến |
| `assessment_runs` | `application_id`, `job_id UNIQUE`, `run_no`, `status`, `snapshot jsonb`, `snapshot_hash`, `application_generation`, `document_id`, `sanitized_version_id`, `rubric_version_id`, `release_manifest_id`, `strategy fulltext\|hybrid`, `output_schema_version`, `observed_score numeric nullable`, `coverage numeric`, `comparable_score numeric nullable`, `recommendation nullable`, `started_at`, `completed_at`, `failure_code nullable`, `result_hash nullable`; UNIQUE app/run_no; partial UNIQUE app khi status non-terminal |
| `criterion_assessments` | PK `(run_id,criterion_id)`; `status assessed\|insufficient_evidence\|conflicting_evidence`, `score smallint nullable`, `rationale text`, `missing_information jsonb` array theo04; assessed bắt buộc score 0..4; hai trạng thái khác bắt buộc null |
| `criterion_evidence` | PK `(run_id,criterion_id,span_id)`; FK criterion assessment và source span; `quote text`, `resolved_start_cp`, `resolved_end_cp`; validate span thuộc sanitized version trong run và quote==span.text |
| `hr_revisions` | `application_id`, `base_run_id nullable`, `document_id`, `sanitized_version_id`, `rubric_version_id`, `application_generation`, `revision_no`, `status draft\|finalized`, `criteria_payload jsonb`, `change_reasons jsonb`, `proposed_decision nullable`, `summary_reason`, `created_by`, `finalized_by/at nullable`, `content_hash nullable`, derived scores/recommendation; finalized payload immutable; mỗi author một draft active/app |
| `review_attestations` | `application_id`, `actor_id`, `decision_basis assessment_review\|manual_document_review\|technical_information_request`, `run_id nullable`, `hr_revision_id nullable`, `document_id`, `document_sha256`, `rubric_version_id nullable`, `snapshot_hash`, `application_generation`, `reviewed_criterion_ids jsonb`, `manual_evidence_refs jsonb nullable`, `technical_failure_code nullable`, `failure_ref jsonb nullable` (document/job/run/processing_event), `raw_view_event_id nullable`, `acknowledged_at`; immutable; CHECK theo discriminated basis bên dưới |
| `decisions` | `application_id`, `decision_basis` cùng enum attestation, `document_id`, `rubric_version_id nullable`, `outcome advance\|request_information\|not_advance`, `reason`, `override_reason nullable`, `attestation_id`, `run_id nullable`, `hr_revision_id nullable`, `source_snapshot jsonb`, `source_hash`, `decided_by`, `supersedes_decision_id nullable`, `sequence_no`; UNIQUE `(app,sequence_no)`; immutable |
| `interview_question_banks` | `rubric_version_id`, `version_no`, `status draft\|approved\|superseded`, `questions_payload jsonb`, `content_hash`, `approved_by/at nullable`, `created_by`; UNIQUE rubric/version; sáu question IDs/criterion IDs; approved immutable |
| `interview_drafts` | `application_id`, `job_id UNIQUE`, `source_snapshot jsonb`, `source_hash`, `question_bank_id`, `status queued\|running\|succeeded\|failed\|cancelled\|stale`, `questions_payload jsonb nullable`, `current_revision_id nullable`, `created_by`; AI followups immutable sau success; core snapshot do code ghép từ approved bank, không email/send action |
| `interview_revisions` | `interview_draft_id`, `revision_no`, `followups_payload jsonb`, `change_reason`, `created_by`, `source_hash`; UNIQUE draft/revision; immutable saved revision; chỉ followups0..3 được sửa, core questions theo bank snapshot |

`base_run_id=null` cho phép HR đánh giá thủ công khi AI lỗi/budget hết, nhưng vẫn phải có current approved sanitized source + approved rubric và complete criterion payload. Đây là đường đánh giá thủ công có cấu trúc, không phải AI success. Nếu OCR/parse không tạo được sanitized text đáng tin, dùng `manual_document_review` hoặc `technical_information_request` theo5.4; không dựng sanitized text/điểm giả để vượt guard. Revision thêm nguồn ngoài CV không được phép trong MVP: thông tin mới phải upload CV version mới, duyệt sanitized và tạo assessment/revision theo snapshot mới. HR có thể giữ `insufficient_evidence` rồi quyết định `request_information`.

### 3.4. Queue, budget, audit, deletion

| Bảng | Fields / constraints quan trọng |
|---|---|
| `jobs` | `type ingest_document\|embed_sanitized\|draft_rubric\|assess_application\|draft_interview\|purge_data`, `status queued\|running\|retry_wait\|succeeded\|failed\|cancelled\|stale`, `target_type/id`, `input_snapshot_hash`, `payload_ref jsonb`, `priority int`, `available_at`, `lease_owner nullable`, `lease_epoch bigint`, `lease_expires_at nullable`, `claim_count int`, `cancel_requested_at nullable`, `last_error_code nullable`; partial index `(priority,available_at,created_at)` cho claimable jobs |
| `llm_invocations` | `job_id`, `logical_step`, `attempt_no`, `status reserved\|admitted\|succeeded\|failed\|outcome_unknown`, `provider`, `model_resolved`, `request_hash`, `request_blob_key nullable`, `response_blob_key nullable`, `provider_request_id nullable`, `input_tokens/output_tokens nullable`, `cost_reserved`, `cost_actual nullable`, `rate_card_version`, `admitted_at`, `finished_at`; UNIQUE `(job_id,logical_step,attempt_no)` |
| `budget_periods` | `scope development\|pilot` (development gồm dev+eval), `period_start/end`, `limit_usd`, `reserved_usd`, `spent_usd`, `rate_card_version`; unique scope/window; CHECK sums không âm; reservation transaction khóa row |
| `budget_reservations` | `budget_period_id`, `job_id`, `amount_usd`, `settled_usd`, `status reserved\|partially_settled\|settled\|released\|uncertain`; ledger không chứa CV |
| `idempotency_records` | `actor_id`, `method`, `route_scope`, `key`, `request_hash`, `status processing\|completed`, `http_status`, `resource_ref jsonb`, `expires_at`; UNIQUE `(actor,method,route_scope,key)`; không cache response raw/secret |
| `audit_events` | `occurred_at`, `actor_type user\|worker\|system`, `actor_id nullable`, `action`, `entity_type/id`, `requisition_id nullable`, `request_id`, `before_version/after_version nullable`, `outcome`, `safe_metadata jsonb`; append-only qua app; không payload CV/prompt/tên liên hệ |
| `deletion_requests` | `scope application\|candidate`, `target_id`, `status requested\|purging\|awaiting_external\|completed\|failed`, `local_purge_complete bool`, `local_purge_completed_at nullable`, `backup_status pending_expiry\|expired\|not_applicable`, `backup_expiry_at nullable`, `external_retention_status unknown\|policy_retention_pending\|deletion_requested\|confirmed_deleted\|not_applicable`, `reason_category`, `requested_by`, `requested_at`, `completed_at nullable`, `inventory jsonb`, `verification_report jsonb`, `job_id`; một request non-terminal/target |

Không lưu giá secret/token rõ trong JSONB. Model request/response payload nếu cần tái dựng nằm trong private blob storage, gắn application để purge; chỉ lưu sau sanitizer approval. `rate_card_version` trỏ cấu hình có nguồn/ngày xác minh ở07, không lấy giá phỏng đoán.

### 3.5 Ngân hàng câu hỏi và sửa nháp phỏng vấn

Seed ở `examples/interview-question-bank.v1.json` là draft do người lập plan soạn. Mỗi approved rubric có một approved bank hiện hành (partial unique rubric/status=approved). Owner tạo/sửa draft bank, duyệt sáu câu hỏi cốt lõi cùng mục đích/answer indicators trước gọi Interview task. Reviewer góp ý qua HR, không tự thay bank chung. Mỗi câu hỏi core gắn đúng một trong sáu criterion; IDs, text, indicators, version và hash được lưu, không model tự viết lại core. Indicators không phải đáp án duy nhất hoặc phép chấm phỏng vấn tự động.

Owner muốn sửa bank approved phải clone draft version mới rồi approve; bank cũ superseded. Chỉ interview drafts gắn bank cũ stale, không làm assessment scores/HR hiring decision stale vì bank không là input assessment. Tạo run mới dùng bank mới; output cũ vẫn lịch sử theo quyền. Reviewer/owner có thể sửa/loại/thêm followups trong giới hạn0..3 bằng revision mới, giữ criterion/source refs hợp lệ và lý do; không sửa core theo từng ứng viên. Không có điểm phỏng vấn hoặc thông báo ứng viên trong MVP.

## 4. Provenance và exact snapshot

### 4.1. Hệ tọa độ nguồn

Canonical sanitized text được normalize một lần: Unicode NFC, newline LF; phiên bản normalization được lưu. Offsets là **Unicode codepoints theo Python**, zero-based, half-open `[start_cp,end_cp)`, không phải UTF-8 byte hoặc JS UTF-16 index. Backend giải resolve/substring; frontend nhận excerpt cùng highlight spans đã resolve hoặc chuyển qua `Array.from(text)`, không dùng `string.slice` trực tiếp với codepoint offset.

`source_span.text == canonical_text[start_cp:end_cp]`. `span_id = 'spn_' + sha256(sanitized_version_uuid + ':' + start_cp + ':' + end_cp)[0:24]`; lưu full hash để detect collision và fail rõ nếu collision, không overwrite. Một span tối đa1.200 codepoints và đủ nhỏ cho một passage tối đa480 token E5 gồm prefix/special tokens; span builder dùng tokenizer đã pin theo04 trước đóng băng registry. Nếu chỉ chạy mock/fulltext chưa có tokenizer thì registry chỉ có giới hạn ký tự và chưa eligible cho hybrid; khi cần chia nhỏ thêm phải tạo version registry/source mới và review lại, không mutate span đã dùng. Chunk là nhóm span; overlap retrieval không tạo bằng chứng mới.

Model trả `span_id` và `quote` bằng **toàn bộ text của span** theo04. Backend xác minh equality tuyệt đối; không fuzzy-match để “sửa” citation, không tự chế page. Page nếu có là mapping do parser/renderer xác định; văn bản nối qua trang có thể tách span tại boundary. Sanitized viewer hiển thị nguồn sanitized, bản raw là link riêng có quyền.

Sửa redaction tạo sanitized version mới và registry mới. Không mutate nguồn mà run cũ đang tham chiếu. Mapping raw→sanitized chứa thông tin có thể nhận diện, nên thuộc private vault và raw grant, không trả trong assessment API.

### 4.2. Snapshot tối thiểu cho run

```json
{
  "snapshot_schema_version": "1.0",
  "application_id": "uuid",
  "application_generation": 3,
  "document_id": "uuid",
  "document_sha256": "64hex",
  "sanitized_version_id": "uuid",
  "sanitized_sha256": "64hex",
  "sanitized_approval_id": "uuid",
  "jd_version_id": "uuid",
  "rubric_version_id": "uuid",
  "rubric_sha256": "64hex",
  "release_manifest_id": "uuid",
  "strategy": "fulltext",
  "parser_version": "p1",
  "normalizer_version": "n1",
  "sanitizer_version": "s1",
  "renderer_version": "r1",
  "retriever_config_hash": "64hex",
  "embedding_config_id": null,
  "prompt_bundle_version": "assessment-v1",
  "provider": "mock",
  "model_requested": "deepseek-chat",
  "model_resolved": null,
  "generation_parameters": {"temperature": 0, "max_output_tokens": 4096},
  "output_schema_version": "1.0.0",
  "evaluation_mode": false
}
```

`sanitized_approval_id` là stable ID của approval event (audit event id), không tự dùng timestamp làm ID. `model_resolved`/token usage do worker bổ sung vào invocation record khi provider response có dữ liệu; không sửa snapshot đầu vào. Actual ordered source span IDs, retrieval query/config/ranked candidates, final context text hash và exact serialized messages lưu thành immutable `execution_artifact` blob được invocation/run tham chiếu. Không lưu chain-of-thought; explanation output là ngắn gọn theo tiêu chí.

Snapshot hash dùng canonical JSON serializer version được ghim (keys sorted, UTF-8, stable decimal encoding) và SHA-256. Hash kiểm tính toàn vẹn, không thay việc giữ source/manifest khi dữ liệu vẫn trong retention. Sau quyền xóa, khả năng tái dựng nguồn kết thúc; audit chỉ giữ metadata tối thiểu hợp lệ.

## 5. State machines và invariants

### 5.1. Requisition/rubric

| From → To | Actor / guard | Side effect |
|---|---|---|
| requisition `draft → open` | Owner; approved current rubric + JD | Set opened_at, audit |
| `open → paused` | Owner; reason | Chặn admission mới; job đã nhận có thể hoàn tất, không tự cancel |
| `paused → open` | Owner; current rubric hợp lệ | Tiếp tục admission |
| `open\|paused → closed` | Owner; reason | Chặn upload/assessment/decision mới; lịch sử vẫn xem được |
| `closed → paused` | Owner; explicit reopen reason | Không âm thầm mở admission |
| rubric `draft → approved` | Owner; If-Match; six IDs; weights100; anchors0..4; JD refs hợp lệ | Set current pointer; previous approved → superseded; staleness derived |
| rubric `approved\|superseded → draft` | Không cho phép | Tạo version mới/clone thay thế |

### 5.2. Document và sanitization

| From → To | Guard / actor |
|---|---|
| document `uploaded → processing` | Worker ingest có lease |
| `processing → ready_for_sanitization` | Parse/render/quality passed; sanitized draft đã lưu |
| `uploaded\|processing → rejected` | MIME/size/page/malware/unsupported; stable failure_code |
| `processing → failed` | Parser/OCR/system failure; không coi ứng viên thiếu năng lực |
| `uploaded\|processing → cancelled` | Cancel/delete; commit có fence |
| sanitized `draft → approved` | Owner + raw_cv grant; content hash/version khớp; all flagged spans addressed/acknowledged |
| sanitized `approved → superseded` | Bản khác được approve; old content giữ cho lịch sử nếu chưa purge |
| sanitized `approved → revoked` | Owner có raw grant phát hiện lộ thông tin; reason; block egress ngay |
| edit bất kỳ source → new `draft` | Tạo immutable content version mới; tăng app generation, clear current sanitized pointer, supersede bản cũ, cancel queued jobs cũ; không sửa approved text |

Upload CV mới đặt làm current document ngay sau admission thành công, tăng application generation, clear current sanitized pointer. Vì vậy run/attestation/decision cũ hiển thị stale ngay cả trước khi CV mới parse xong. Không âm thầm quay về CV cũ nếu file mới lỗi; owner có thể explicit chọn lại document hợp lệ qua API với lý do và một generation mới.

### 5.3. Technical job/run

| From → To | Điều kiện |
|---|---|
| `queued → running` | Worker claim lease; admissibility còn hợp lệ |
| `running → retry_wait` | Transient known failure; còn attempt/call/budget; có retry time |
| `retry_wait → running` | Tới available_at; claim epoch mới |
| `running → succeeded` | Validated output, fence hợp lệ, nguồn còn current, không tombstone |
| `running → stale` | Output hoàn tất nhưng snapshot khác current; giữ lịch sử, không làm current |
| `queued\|retry_wait → cancelled` | Cancel trước claim hoặc deletion |
| `running → cancelled` | Cooperative cancellation; tuyệt đối không commit payload sau deletion |
| `queued\|running\|retry_wait → failed` | Non-retryable, exhausted limits, unresolved provider outcome hoặc budget/policy block |

`assessment_runs.status` dùng cùng enum terminal/processing; không nhận `ready_for_hr` như hiring state. Chỉ `succeeded` là bản AI hiện hành đủ điều kiện hiển thị recommendation; `is_stale` vẫn phải tính động vì source có thể đổi sau khi job success. Terminal status không được sửa lại thành running; resource retry tạo run/job mới với `supersedes_run_id` trong metadata. Check UNIQUE một active assessment/app áp cho queued/running/retry_wait.

`cancel_requested` là flag, không phải bảo đảm request ngoài đã dừng. Worker count/lease retries không reset LLM call count. Tối đa hai attempt cho một logical step, tổng assessment tối đa bốn external calls theo00. `outcome_unknown` không auto-retry để tránh gọi trùng mất kiểm soát.

### 5.4. HR revision, attestation và hiring decision

| Hành động | Guard bắt buộc |
|---|---|
| Tạo/sửa revision draft | Assigned owner/reviewer; current snapshot; If-Match cho sửa; đủ sáu tiêu chí, status/score valid |
| Finalize revision | Author hoặc owner; no stale; các thay đổi có lý do; sources valid; freeze hash |
| Attest `assessment_review` | Owner/reviewer; effective result = successful current run hoặc finalized current HR revision; reviewed IDs đúng đủ sáu; acknowledgement explicit |
| Attest `manual_document_review` | Chỉ owner + raw_cv grant; current file qua safety checks, người dùng đã mở file và xác nhận đọc được; approved current JD/rubric; sáu criterion được review, không buộc chấm điểm |
| Attest `technical_information_request` | Chỉ owner; current document hoặc job/run gắn đúng current document có lỗi kỹ thuật đã ghi nhận; acknowledgement mã lỗi và yêu cầu nộp lại/bổ sung; không cần đọc raw hoặc có sanitized source |
| Final decision | Owner có recruiter role; app active, requisition open/paused, current snapshot, không pending analysis chưa cancel; attestation của chính owner cho đúng basis; reason không rỗng; guard riêng theo bảng dưới |
| Replace decision | Điều kiện final decision + expected previous decision ID + reason thay đổi; append event, không UPDATE quyết định cũ |

Revision thủ công có thể finalize với null statuses; owner vẫn quyết định bằng lý do. `override_reason` bắt buộc nếu quyết định khác gợi ý, khi còn null/conflict, hoặc dùng manual path. Không biến AI recommendation thành một HR decision mặc định có sẵn trên form.

Stale luôn khi application generation/current document khác hoặc app deleting/deleted. Với `assessment_review`, còn kiểm sanitized version/approval, current JD/rubric, pending newer assessment và effective revision. Với `manual_document_review`, kiểm current JD/rubric, document safety/hash và raw grant còn hiệu lực của actor; không phụ thuộc kết quả OCR/AI hoặc sanitized approval. Với `technical_information_request`, kiểm document/hash/error state còn khớp; rubric có thể null và không được dùng để quyết định năng lực. Server trả `stale_reasons[]`; UI khóa đúng đường bị ảnh hưởng, không khóa mọi manual action chỉ vì AI thất bại. Decision cũ không tự bị đảo ngược; nguồn thay đổi hiển thị `requires_reconfirmation=true` theo basis đã lưu.

| Basis | Căn cứ bắt buộc | Outcome cho phép | DB/service constraints |
|---|---|---|---|
| `assessment_review` | Successful AI run hoặc finalized HR revision; approved sanitized source + current approved rubric | Cả ba | Đúng một run/revision; sáu reviewed IDs; refs thuộc cùng snapshot; run nullable khi dùng HR-only revision |
| `manual_document_review` | Current safe raw document, hash và sáu reviewed IDs; `manual_evidence_refs` ít nhất một `{criterion_id,document_id,page_number?,section_label?,note}`; note nêu căn cứ năng lực, không tên/trường/tuổi | Cả ba | run/revision null; rubric bắt buộc; raw grant bắt buộc; attestation ghi raw-view event của actor trên đúng document; không tạo observed/comparable score hoặc recommendation AI |
| `technical_information_request` | Document ID/hash + `failure_ref:{kind:document\|job\|assessment_run\|processing_event,id}` + stable failure code đã được backend ghi (OCR/parse/context/provider/budget/unsupported); acknowledgement rõ | Chỉ `request_information` | run/revision null; reviewed IDs=[]; manual refs null; rubric nullable; reason chỉ mô tả yêu cầu xử lý hồ sơ, không kết luận ứng viên yếu |

Raw-view event chỉ chứng minh đã mở file; HR vẫn phải xác nhận đã đọc, hệ thống không tuyên bố đo được sự chú ý. File `safety_status=rejected|pending` không được mở qua manual path; owner chỉ yêu cầu bản khác. Lỗi parse/OCR phải tách với safety checks để một PDF an toàn nhưng không OCR được vẫn có thể đọc bằng người. Upload bị từ chối trước khi tạo document chưa có application basis để quyết định; UI báo re-upload, không ghi một decision không có hồ sơ.

Mọi decision chặn analysis job còn queued/running/retry_wait và chưa có cancel request. Owner dùng endpoint cancel hiện có trước khi chuyển đường manual; queued được cancel, running gắn `cancel_requested_at` ngay. Write guard không cho job đã cancel publish nguồn/result mới dù HTTP call ngoài còn kết thúc và vẫn cần settle cost. Attestation/decision đọc lại current snapshot sau cancel; không tự restart analysis. HR-only/manual decisions không tính vào AI success hoặc agreement denominator có AI score; vẫn hiện trong operational/decision counts.


## 6. RBAC theo hành động

`M` = active member của requisition; `O` = owner + recruiter role; `R` = reviewer membership; `G` = grant đang hiệu lực đúng scope. Disabled user/session hết hạn luôn deny. Resource không thuộc quyền trả404, tránh lộ tồn tại; đã có quyền xem nhưng thiếu quyền hành động trả403.

| Hành động | Admin đơn thuần | O | R |
|---|---|---|---|
| Quản lý account/config vận hành | Có | Không, trừ thêm admin | Không |
| Tạo requisition | Có thể tạo skeleton, không đọc CV | Có qua recruiter role; tự owner | Không |
| Đọc sanitized approved/assessment | Không nếu không M | Có | Có |
| Đọc raw/identity/unapproved sanitized | Không implicit | Cần G | Cần G |
| Cấp/revoke raw grant | Không implicit | Có, có audit/reason/expiry | Không |
| Upload CV | Không nếu không M | Có | Có |
| Duyệt sanitized | Không nếu không M+G | Cần G raw_cv | Không; chỉ sửa draft/đánh dấu vấn đề khi có G |
| Sửa JD/rubric, approve rubric | Không implicit | Có | Đọc/comment qua note; không approve |
| Trigger assessment/interview | Không nếu không M | Có | Có |
| HR revision / assessment attestation | Không nếu không M | Có | Có |
| Manual-document / technical-request attestation | Không implicit | Có; manual-document cần G raw_cv | Không |
| Final hiring decision | Không implicit | Có | Không |
| Xóa application | Không implicit | Có, cần reason | Không |
| Xóa candidate toàn tổ chức | Admin data-ops qua request cụ thể | Không tự xóa application thuộc req khác | Không |
| Audit | Metadata toàn tổ chức; không payload | Theo requisition | Theo application được phân công; không user admin events |

**Quarantine sau revoke:** sanitized version `revoked` có thể chứa PII. Thành viên không có raw_cv grant chỉ nhận metadata/status; không được đọc text, quote, rationale, HR revision, manual notes có tham chiếu nguồn đó, interview payload hoặc execution artifact dẫn xuất qua bất kỳ endpoint/history/cache nào. Thành viên có raw grant còn hiệu lực được mở payload bị quarantine qua hành động raw-review có audit, không dùng nó làm current assessment hoặc gửi ngoài. Bản history vẫn immutable nhưng quyền đọc thay đổi tức thì; quyết định cũ giữ actor/outcome/time và badge nguồn thu hồi, không tự đảo. Revocation đánh dấu source lineage và mọi derived artifact; tải/GET/replay kiểm lineage tại thời điểm request, không chỉ rely cached DTO.

Audit raw view/download, cấp quyền, source approval/revocation, run invocation, override, decision, deletion và session/admin changes. Security details ở05. Service phải dùng một authorization helper chuẩn; không copy conditions khác nhau ở mỗi route.

## 7. REST conventions, concurrency và lỗi

### 7.1. Request/response chung

- Auth bằng server session cookie; mutation cần `X-CSRF-Token` và allowed `Origin`. Không dùng localStorage bearer token.
- Entity mutable trả `ETag: "<row_version>"`; PUT/PATCH và action dựa trên state yêu cầu `If-Match`. Thiếu trả428; không khớp412. Input `expected_*` dùng khi action khóa nhiều entity.
- Thứ tự xử lý mutation: authenticate → current authorization/scope/tombstone/quarantine → kiểm idempotency completed → nếu chưa có kết quả thì If-Match + domain guards + mutation. Cùng key/body đã thành công được replay reference/result an toàn dù If-Match cũ do lần gọi đó đã đổi version. Reauthorize resource khi replay; không trả payload đã bị revoke/deleted. Key cùng nhưng request hash khác vẫn409; response chỉ metadata khi policy hiện tại cấm payload.
- POST có side effect yêu cầu `Idempotency-Key` theo02. DELETE revoke session/grant có tính idempotent và không cần tạo job mới nếu lặp.
- Create201 + `Location`; asynchronous202 + `job_id`; read200; mutation no body204; list dùng cursor keyset. Không trả200 với `{success:false}`.
- Lists: `?limit=20&cursor=opaque`; limit1..100; cursor base64url encoded filter/sort/last-key có integrity protection, không có PII. Default app order `(received_at,id) ASC`. Response `{items:[],next_cursor:null}`.
- Sort comparable score là opt-in `sort=comparable_score_desc&completeness=complete`; incomplete được tab/list riêng, không fallback sang observed_score. Null score không convert0.
- File requests luôn validate bằng bytes thực, không tin Content-Type/extension. Không dùng original filename làm path, shell argument hoặc log value.

### 7.2. Error envelope

```json
{
  "error": {
    "code": "STALE_SNAPSHOT",
    "message": "Nguồn đánh giá đã thay đổi; cần tải lại trước khi phê duyệt.",
    "request_id": "uuid",
    "details": {"stale_reasons": ["rubric_changed"], "current_row_version": 8}
  }
}
```

| HTTP | Codes tối thiểu |
|---|---|
| 400 | `INVALID_CURSOR`, `INVALID_IDEMPOTENCY_KEY`, `INVALID_MULTIPART` |
| 401 | `AUTH_REQUIRED`, `INVALID_CREDENTIALS`, `SESSION_EXPIRED` |
| 403 | `ACTION_FORBIDDEN`, `RAW_ACCESS_REQUIRED`, `CSRF_FAILED`, `PILOT_GATE_BLOCKED` |
| 404 | `RESOURCE_NOT_FOUND` gồm resource ngoài membership |
| 409 | `IDEMPOTENCY_CONFLICT`, `ACTIVE_RUN_EXISTS`, `STALE_SNAPSHOT`, `INVALID_TRANSITION`, `BUDGET_BLOCKED`, `SOURCE_NOT_APPROVED`, `RUBRIC_NOT_APPROVED`, `APPLICATION_DELETING`, `PROVIDER_OUTCOME_UNKNOWN`, `DECISION_BASIS_INVALID`, `DOCUMENT_NOT_SAFE`, `ACTIVE_ANALYSIS_EXISTS`, `JD_RUBRIC_MISMATCH` |
| 410 | `RESOURCE_DELETED` chỉ caller có quyền thấy tombstone/deletion request |
| 412 / 428 | `VERSION_CONFLICT` / `PRECONDITION_REQUIRED` |
| 413 / 415 | `FILE_TOO_LARGE` / `UNSUPPORTED_FILE_TYPE` |
| 422 | `VALIDATION_ERROR`, `EVIDENCE_INVALID`, `RUBRIC_INVALID`, `PAGE_LIMIT_EXCEEDED` (nếu phát hiện đồng bộ) |
| 429 | `RATE_LIMITED`, `QUEUE_CAPACITY_REACHED`; `Retry-After` |
| 503 | `DEPENDENCY_UNAVAILABLE`, `DOCUMENT_RENDER_UNAVAILABLE`; không lộ connection strings |

Async lỗi trả trên job/resource, không giả thay status code của upload202 đã trả. Error detail không chứa stacktrace, prompt, raw đoạn CV hoặc secret.

## 8. REST — authentication, users, memberships

Ký hiệu response `User`, `Application`, `Rubric`... là projection của bảng/schema trong tài liệu, không trả mọi DB column. Tuyệt đối không serialize password hash, session hash, blob key, mapping raw hoặc provider secret. Mọi endpoint đọc/list dưới đây áp RBAC trước truy vấn nội dung.

| Method/path | Actor; request | Response / semantics |
|---|---|---|
| `GET /auth/csrf` | Anonymous hoặc session | 200 `{csrf_token}`; token gắn pre-auth/session; no-store |
| `POST /auth/login` | Origin+CSRF; `{login_name,password}` | 200 `{user:{id,display_name,roles,must_change_password}}` + session cookie; lỗi chung401, rate limit429 |
| `GET /auth/me` | Session | 200 user + allowed account actions; không trả mọi candidate membership trong bootstrap |
| `POST /auth/logout` | Session+CSRF | 204 revoke session + clear cookie; gọi lại không tạo lỗi nghiệp vụ |
| `POST /auth/change-password` | Session; `{current_password,new_password}` | 204; revoke các session khác; clear must_change_password |
| `GET /admin/users` | Admin; pagination/status filter | 200 user list; không trả hash/password |
| `POST /admin/users` | Admin; `{login_name,display_name,roles,initial_password}` | 201 User; must_change_password=true; initial_password write-only, không idempotency response cache |
| `PATCH /admin/users/{id}` | Admin, If-Match; `{display_name?,roles?,status?}` | 200 User; disable/role removal tăng session_generation, không orphan last admin/owner |
| `POST /admin/users/{id}/reset-password` | Admin; `{temporary_password}` | 204; revoke sessions; must_change_password=true; audit không password |
| `GET /requisitions/{id}/members` | O hoặc R; admin quản lý metadata được phép | 200 membership list |
| `PUT /requisitions/{id}/members/{user_id}` | O hoặc admin; If-Match requisition; `{membership_role,expected_requisition_version}` | 200 membership; explicit recruiter role cho owner |
| `DELETE /requisitions/{id}/members/{user_id}` | O hoặc admin; If-Match requisition | 204; revoke raw grants trong req; không remove last owner |
| `POST /applications/{id}/raw-grants` | O; `{grantee_user_id,scopes,expires_at,reason}` | 201 grant metadata; grantee phải là M; expiry bắt buộc và trong policy |
| `DELETE /applications/{id}/raw-grants/{grant_id}` | O | 204; revoke tức thì cho request tiếp theo; không trả nội dung raw |

Login/password routes không dùng idempotency request-body cache; áp Origin/CSRF/rate limit và write-only password DTO. Seed admin đầu tiên qua CLI local có kiểm tra chưa tồn tại, không public bootstrap endpoint. Không cho gọi các endpoint nghiệp vụ trước khi đổi temporary password.

## 9. REST — requisition, JD, rubric

| Method/path | Actor; request | Response / semantics |
|---|---|---|
| `GET /requisitions` | Recruiter/reviewer; admin metadata list | 200 list theo membership; admin-only projection không có applicant data |
| `POST /requisitions` | Recruiter hoặc admin; `{title,owner_user_id?}` | 201 Requisition draft; recruiter mặc định tự owner; admin phải chọn recruiter owner |
| `GET /requisitions/{id}` | M hoặc admin metadata | 200 title/status/current version IDs/row_version; M thêm counts |
| `PATCH /requisitions/{id}` | O; If-Match; `{title?,status?,reason?}` | 200; transition theo phần5; status changes cần reason |
| `POST /requisitions/{id}/jd-versions` | O; If-Match req; `{source_text,change_reason}` | 201 JDVersion; new version làm current JD; rubric hiện hành có JD khác trở thành stale cho admission cho tới duyệt rubric mới |
| `GET /jd-versions/{id}` | M | 200 source_text/hash/version/egress state |
| `POST /jd-versions/{id}/approve-egress` | O; If-Match; `{expected_text_hash,acknowledged:true}` | 200 metadata; workflow kiểm nội dung JD, không hỏi lại quyền dùng DeepSeek đã được trường cho phép |
| `POST /jd-versions/{id}/rubric-drafts` | O; `{mode:"llm"}` | 202 `{job_id,jd_version_id}`; JD egress-reviewed; budget/provider gate; khi xong tạo Rubric draft |
| `POST /requisitions/{id}/rubrics` | O; `{jd_version_id,source:"seed"\|"clone"\|"manual",clone_from_id?,rubric?}` | 201 draft; seed/clone không gọi LLM; manual nhận schema dưới đây |
| `GET /rubrics/{id}` | M | 200 canonical rubric + state/version/hash/approval |
| `PUT /rubrics/{id}` | O; If-Match; toàn bộ `{rubric}` | 200 draft; chỉ draft editable; không patch vài anchor làm thiếu cấu trúc |
| `POST /rubrics/{id}/approve` | O; If-Match rubric; `{expected_requisition_version,expected_jd_version_id,acknowledge_thresholds:true}` | 200 `{rubric,requisition_row_version}`; chuyển pointer atomically; 409 nếu current JD khác |

Canonical rubric payload giữ cùng shape file seed do01 cung cấp: `criteria[].id`, `weight`, `source_requirements[]`, `scoring_anchors[]`, và `recommendation_policy`. DB mapping rõ: `id → criterion_id`, `source_requirements → jd_evidence_refs`, `scoring_anchors → anchors`, `recommendation_policy → threshold_config` qua typed adapter duy nhất, có round-trip test. Không để adapter đánh rơi thông tin `not_sufficient`.

Ví dụ khung rubric (chỉ minh họa một criterion; request thực phải đủ sáu):

```json
{
  "version": 1,
  "status": "draft",
  "criteria": [{
    "id": "python_backend",
    "weight": 20,
    "source_requirements": [{"requirement_id":"JD-PY-01","quote":"Đoạn yêu cầu đầy đủ lấy nguyên văn từ JD hiện hành"}],
    "scoring_anchors": [
      {"score": 0, "description": "Có bằng chứng rõ theo anchor đã duyệt", "qualifying_evidence": [], "not_sufficient": []}
    ]
  }],
  "recommendation_policy": {
    "threshold": 70,
    "core_minimum_scores": {"python_backend": 2,"api_design": 2,"sql_data": 2},
    "require_full_coverage": true
  }
}
```

Đây không phải payload valid đầy đủ và không được dùng làm fixture pass. Seed thực là nguồn anchor đầy đủ. JD `source_refs` ánh xạ `JD-PY-01`, `JD-API-01` và các requirement IDs thật khác đến đoạn có thật; owner manual edit phải cập nhật references. Nếu JD mới chưa có rubric approved tương ứng, `open` state vẫn có thể giữ nhưng mọi assessment admission và decision basis `assessment_review|manual_document_review` hiển thị blocked reason `JD_RUBRIC_MISMATCH`; technical_information_request vẫn có thể ghi yêu cầu nộp lại vì lỗi mà không có rubric; không dùng rubric cũ âm thầm.

## 10. REST — application, upload và provenance

| Method/path | Actor; request | Response / semantics |
|---|---|---|
| `GET /requisitions/{id}/applications` | M; pagination, technical_status?, decision?, completeness?, sort? | 200 rows: public label, received_at, safe statuses, score/coverage/current decision, is_stale; không tên/raw filename |
| `POST /requisitions/{id}/applications` | M; `{candidate_id?:uuid}` | 201 Application; nếu bỏ candidate_id tạo candidate random public_label; no implicit identity matching |
| `GET /applications/{id}` | M | 200 safe metadata/current IDs/stale reasons/allowed_actions/row_version; identity tách endpoint |
| `GET /applications/{id}/identity` | M+G identity | 200 `{name,email,phone}`; no-store; audit view |
| `PUT /applications/{id}/identity` | O+G identity; If-Match candidate identity; `{name?,email?,phone?}` | 200 safe identity projection; không tác động scoring; audit field names only |
| `POST /applications/{id}/documents` | M; If-Match application; multipart `file` + `metadata` | 202 document+ingest job+new app version; binary không base64 JSON |
| `GET /applications/{id}/documents` | M | 200 version metadata; original filename chỉ khi raw grant; lỗi parse dùng mã an toàn |
| `POST /documents/{id}/reprocess` | M; If-Match application; `{reason}` | 202 job mới; chỉ failed/rejected có lỗi có thể sửa bằng parser/config và current document; unsupported malicious file không cho retry mù |
| `PUT /applications/{id}/current-document` | O; If-Match app; `{document_id,reason}` | 200 app; doc phải thuộc app; tăng generation, clear current sanitized, tạo draft copy cần duyệt lại |
| `GET /documents/{id}/raw` | M+G raw_cv | 200 binary attachment chỉ khi safety_status=passed; Content-Type verified, generated safe filename, no-store; audit download |
| `GET /documents/{id}/sanitized-versions` | M+G raw_cv với draft; M chỉ approved/superseded nonrevoked | 200 version metadata được phép |
| `GET /sanitized-versions/{id}` | M khi approved; M+G raw_cv nếu draft/revoked | 200 canonical_text, hash, version, safe quality_flags; mapping raw không nằm response |
| `POST /documents/{id}/sanitized-versions` | M+G raw_cv; If-Match app; `{base_version_id,canonical_text,edit_reason}` | 201 new draft + new app generation/version; backend normalize/hash/span generation; current approval bị clear, old source không bị edit |
| `POST /sanitized-versions/{id}/approve` | O+G raw_cv; If-Match source; `{expected_application_version,expected_sha256,acknowledged:true}` | 200 source+app generation/version; current document phải khớp; malformed offsets/detectors flags phải xử lý |
| `POST /sanitized-versions/{id}/revoke` | O+G raw_cv; If-Match; `{reason,expected_application_version}` | 200 source/app versions; revoke egress, stale results, cancel pending related work |
| `GET /source-spans/{span_id}` | M; span phải thuộc accessible approved/nonrevoked historical source; revoked chỉ qua raw-review có G và audit | 200 evidence DTO dưới đây; không cho enumerate sources ngoài quyền |

Upload multipart contract:

```text
POST /api/v1/applications/<uuid>/documents
Content-Type: multipart/form-data; boundary=...
Idempotency-Key: <uuid>
If-Match: "4"
X-CSRF-Token: ...
file: binary PDF hoặc DOCX
metadata: {"document_kind":"cv"}
```

```json
{
  "document": {"id":"uuid","version_no":2,"ingestion_status":"uploaded","byte_size":245000},
  "job_id":"uuid",
  "application_row_version":5,
  "application_generation":2
}
```

Server stream vào temp riêng, kiểm total bytes thật, validate signature/MIME trước admission nếu khả thi. Virus/type/archive/page/quality checks phát hiện sau upload phải thể hiện trạng thái rejected/failed có lý do; HTTP202 chỉ là đã nhận công việc. Batch UI giới hạn20 file, gọi per-file upload endpoint và có progress/error riêng; không gửi một zip CV. File name dùng cho hiển thị riêng, không dùng làm parser shell command. Dedupe chỉ scope application: cùng checksum+same current version có thể trả409 `DOCUMENT_ALREADY_CURRENT` kèm resource hiện có; không tiết lộ checksum trùng ở candidate khác.

Evidence response:

```json
{
  "span_id":"spn_0123456789abcdef01234567",
  "sanitized_version_id":"uuid",
  "source_hash":"64hex",
  "coordinate_system":"unicode_codepoints_nfc_lf",
  "start_cp":120,
  "end_cp":152,
  "page_number":2,
  "section_label":"Kinh nghiệm",
  "text":"Đoạn nguồn thực tế lấy từ server.",
  "renderer_version":"r1"
}
```

Độ dài/offset ví dụ chỉ minh họa field, fixture thật phải tính từ đúng text. API không nhận offset/page từ model/client làm nguồn tin cậy. Annotation frontend gửi span_id đã tồn tại; backend xác minh ownership/version trước lưu vào revision.

## 11. REST — assessment, HR review và decision

| Method/path | Actor; request | Response / semantics |
|---|---|---|
| `POST /applications/{id}/assessments` | M; If-Match app; `{sanitized_version_id,rubric_version_id}` | 202 run/job; source IDs phải đúng current, không cho chọn nguồn lịch sử để bypass stale |
| `POST /applications/{id}/reassess` | M; If-Match app; `{supersedes_run_id,sanitized_version_id,rubric_version_id,reason}` | 202 new run/job; không active run; history giữ nguyên; admission làm old recommendation pending/stale |
| `GET /applications/{id}/assessments` | M; pagination | 200 run summaries theo run_no desc; include historical stale status |
| `GET /assessments/{run_id}` | M | 200 metadata, full criterion results/evidence nếu có, derived scores, is_stale/stale_reasons, safe usage totals |
| `POST /applications/{id}/hr-revisions` | M; If-Match app; `{base_run_id?:uuid,source_snapshot_ref,criteria,change_reasons,summary_reason,proposed_decision?}` | 201 draft revision; manual path base null; current sources only |
| `GET /hr-revisions/{id}` | M | 200 draft/finalized payload+derived scores+staleness; draft author/owner sửa được |
| `PUT /hr-revisions/{id}` | Author hoặc O; If-Match revision; full `{criteria,change_reasons,summary_reason,proposed_decision?}` | 200 draft; every changed score/status has nonempty reason; recompute scores server-side |
| `POST /hr-revisions/{id}/finalize` | Author hoặc O; If-Match revision; `{expected_application_version,expected_rubric_version_id}` | 200 immutable revision hash; 409 stale; không phải hiring decision |
| `POST /applications/{id}/review-attestations` | M; If-Match app; `{decision_basis,...basis_fields,acknowledged:true}` theo5.4 và ví dụ bên dưới | 201 attestation bound actor+basis+snapshot hash; backend tự resolve/check refs, không tự tick bằng code |
| `POST /applications/{id}/decisions` | O; If-Match app; request bên dưới | 201 immutable Decision+app row_version; pending analysis chưa cancel hoặc stale theo basis trả409 |
| `GET /applications/{id}/decisions` | M; pagination | 200 history, actor/time/reason/outcome/source refs; current pointer rõ |

Assessment admission response:

```json
{
  "run_id":"uuid",
  "job_id":"uuid",
  "status":"queued",
  "snapshot_hash":"64hex",
  "application_row_version":7,
  "links":{"run":"/api/v1/assessments/uuid","job":"/api/v1/jobs/uuid"}
}
```

Summary khi cả sáu tiêu chí đều score3:

```json
{
  "run_id":"uuid",
  "status":"succeeded",
  "is_stale":false,
  "stale_reasons":[],
  "scores":{"observed_score":"75.00","coverage":"1.0000","comparable_score":"75.00"},
  "recommendation":"consider_next_round",
  "rubric_version_id":"uuid",
  "source_sanitized_version_id":"uuid",
  "requires_hr_decision":true
}
```

Full GET assessment bổ sung `criteria` theo schema04 đã được backend enrich evidence metadata. Public DTO không có unvalidated model response. Một criterion response có `criterion_id,status,score,rationale,missing_information,evidence[{span_id,quote,source_sanitized_version_id,start_cp,end_cp,page_number}]`; model không trả evidence_strength ngoài schema đã chốt. HR revision dùng cùng criterion core shape nhưng `change_reasons` tách khỏi explanation nguồn. Server tính weight từ approved rubric, không tin weight gửi bởi client.

`source_snapshot_ref` cho manual revision:

```json
{"document_id":"uuid","sanitized_version_id":"uuid","rubric_version_id":"uuid","application_generation":3}
```

Nếu base_run_id có, source_snapshot_ref phải khớp run và current; backend không cho trộn criterion từ hai run. `proposed_decision` là `advance|request_information|not_advance|null`, chỉ lời đề xuất của reviewer, không cập nhật application current_decision.

Attestation requests là discriminated union, không cho gửi fields thuộc nhánh khác. Ví dụ dưới đây có ID placeholder; fixture triển khai phải dùng UUID/document hash thật:

```json
{"decision_basis":"assessment_review","effective_result":{"kind":"assessment_run","id":"uuid"},"reviewed_criterion_ids":["python_backend","api_design","sql_data","testing_debugging","security_privacy","delivery_ops"],"acknowledged":true}
```

`effective_result.kind` chỉ `assessment_run|hr_revision`. Manual document:

```json
{"decision_basis":"manual_document_review","document_id":"uuid","expected_document_sha256":"64hex","expected_rubric_version_id":"uuid","reviewed_criterion_ids":["python_backend","api_design","sql_data","testing_debugging","security_privacy","delivery_ops"],"manual_evidence_refs":[{"criterion_id":"api_design","document_id":"uuid","page_number":2,"section_label":"Dự án","note":"Đã đọc phần mô tả thiết kế API và sẽ kiểm tra vai trò khi phỏng vấn."}],"acknowledged":true}
```

Technical request, không gửi raw hoặc nguồn do model bịa:

```json
{"decision_basis":"technical_information_request","document_id":"uuid","expected_document_sha256":"64hex","failure_ref":{"kind":"document","id":"uuid"},"technical_failure_code":"OCR_QUALITY_FAILED","reviewed_criterion_ids":[],"acknowledged":true}
```

`failure_ref` bắt buộc cho technical basis: lỗi parse/OCR/unsupported có thể tham chiếu document; lỗi context/provider/budget tham chiếu job/run hoặc document processing event đã lưu. Admission bị chặn trước tạo job phải ghi một safe processing-failure record gắn app/document và trả reference (có thể dùng audit event với kind `processing_event`, thêm vào union), không tạo mã lỗi tự khai từ browser. Backend kiểm ref thuộc cùng app/current document, error code còn hiện hành và không bị lần xử lý thành công mới thay thế. Mã lỗi ví dụ phải thuộc error catalog do backend sinh, không chỉ nhận chuỗi lỗi client khai. Snapshot hash backend tự dựng từ refs hợp lệ. `POST /decisions` gửi cùng `decision_basis` với attestation, backend không tin client đổi basis để bỏ guard.

Decision request:

```json
{
  "decision_basis":"assessment_review",
  "outcome":"advance",
  "reason":"Đã đối chiếu sáu tiêu chí và xem nguồn; mời phỏng vấn để xác minh phạm vi trách nhiệm API.",
  "override_reason":null,
  "attestation_id":"uuid",
  "expected_previous_decision_id":null,
  "expected_rubric_version_id":"uuid"
}
```

Với technical request, `expected_rubric_version_id` có thể null; với hai basis còn lại bắt buộc khớp current rubric. `override_reason` cần với manual document hoặc HR-only revision; technical request cần reason cụ thể nhưng không buộc viết override một AI suggestion không tồn tại. Không chấp nhận outcome advance/not_advance ở technical basis.

Owner phải có attestation của chính mình, không mượn review của reviewer. `reason` luôn bắt buộc. `override_reason` bắt buộc nếu manual document/HR-only revision, còn null/conflict trong assessment basis, hoặc chọn khác hướng `consider_next_round→advance`/`needs_clarification→request_information`. `review_required` không ánh xạ mặc định tới not_advance. Nếu replace decision, expected_previous_decision_id phải đúng current; unique sequence + lock ngăn hai owner ghi đè.

Không có endpoint `PATCH decision`, `auto-reject`, `hire`, `bulk-approve` hoặc `send-email` trong MVP.

## 12. REST — interview, job, deletion, audit và operations

| Method/path | Actor; request | Response / semantics |
|---|---|---|
| `GET /rubrics/{id}/interview-question-banks` | M | 200 allowed bank versions/current approved ID |
| `POST /rubrics/{id}/interview-question-banks` | O; `{source:"seed"\|"clone",clone_from_id?}` | 201 draft; seed không gọi LLM hoặc auto-approve |
| `PUT /interview-question-banks/{id}` | O; If-Match bank; `{questions,change_reason}` | 200 updated draft; đủ sáu core criteria, plain text/policy validation; approved không edit |
| `POST /interview-question-banks/{id}/approve` | O; If-Match bank; `{expected_rubric_version_id,acknowledged:true}` | 200 approved immutable bank; atomically supersede previous bank cùng rubric |
| `POST /applications/{id}/interview-drafts` | M; If-Match app; `{effective_result:{kind,id},expected_question_bank_id}` | 202 draft_id/job_id; current finalized/AI result, approved rubric/source/bank; on-demand budget admission |
| `GET /interview-drafts/{id}` | M, lineage restrictions | 200 core bank snapshot + AI followups + latest HR revision + source refs/is_stale; no auto send |
| `POST /interview-drafts/{id}/revisions` | M; If-Match interview; `{expected_previous_revision_id,followups,change_reason}` | 201 immutable HR edit; current nonstale draft/source/bank required; validate followups theo interview schema, update pointer atomically; conflict409 |
| `GET /interview-drafts/{id}/revisions` | M, lineage restrictions | 200 scoped revision history; không lộ revoked source text |
| `GET /jobs/{id}` | M theo target; admin chỉ safe ops projection | 200 status/stage/attempt counts/timestamps/error_code/cancel_requested/result_ref; không payload |
| `POST /jobs/{id}/cancel` | M theo target, owner với rubric job; `{reason}` | 202 cancellation requested hoặc200 already terminal; purge job không cho HR cancel |
| `POST /applications/{id}/deletion-requests` | O; If-Match app; `{reason_category,reason}` | 202 deletion_request/job IDs; tombstone/revoke/read block ngay |
| `POST /candidates/{id}/deletion-requests` | Admin data-ops; `{reason_category,reason,confirmed_scope:"all_applications"}` | 202 toàn candidate; chỉ khi đã xác minh đúng target; không cần raw read grant |
| `GET /deletion-requests/{id}` | Requestor/O phù hợp; admin data-ops | 200 inventory progress/no raw data; completed chỉ sau verification |
| `GET /audit-events` | Theo RBAC; `requisition_id?,application_id?,action?,from?,to?,cursor?` | 200 immutable event projections; time window max31 ngày/query; export chưa MVP |
| `GET /admin/operations` | Admin | 200 queue age/count, worker heartbeat, dependency readiness, error budget, budget totals, unresolved invocation counts; no PII |
| `GET /admin/budgets` | Admin | 200 scope/window/limit/reserved/spent/rate_card_version |
| `PATCH /admin/budgets/{id}` | Admin; If-Match; `{limit_usd,reason}` | 200 updated cap; no credit purchase; existing spend không bị xóa; audit |
| `POST /admin/llm-invocations/{id}/reconcile` | Admin; `{outcome:"charged"\|"not_charged"\|"unknown",actual_cost_usd?,evidence_note}` | 200 ledger update; no provider replay; unknown giữ conservative reservation |
| `GET /onboarding` | Session | 200 current walkthrough steps/progress/environment; no real sample data |
| `PUT /onboarding/progress` | Session; `{walkthrough_version,completed_steps,sandbox_result?}` | 200 progress; chỉ sandbox exercise result được server xác minh, không để client tự bật pilot gate |
| `GET /health/live` | Internal hoặc public minimal | 200 `{status:"ok"}` nếu process alive; không credentials/version details |
| `GET /health/ready` | Internal/admin | 200 hoặc503 khi DB/migrations/storage/config chưa ready; không gọi provider trả phí |
| `GET /metrics` | Internal network/admin service auth | Metrics text cho monitoring; không public internet; labels không PII |

`GET /jobs` không có listing toàn tổ chức cho reviewer. Client polling một job mỗi2 giây trong30 giây đầu, sau đó5 giây, có jitter và dừng khi terminal/tab hidden; không cần WebSocket/SSE trong MVP. App list refresh nhẹ khi job hoàn tất. Người dùng có thể đóng trang, job vẫn chạy.

Không có generic retry endpoint cho terminal assessment. UI “Thử lại” gọi `reassess` để tạo run mới sau khi nguyên nhân giải quyết; ingest dùng reprocess; rubric/interview tạo draft mới. Purge retry là admin/worker operation, không thay tombstone. Provider outcome unknown không biến thành not_charged do timeout đơn thuần.

Deletion response ví dụ:

```json
{
  "deletion_request_id":"uuid",
  "status":"requested",
  "access_revoked":true,
  "job_id":"uuid",
  "scope":"application",
  "local_purge_complete":false,
  "backup_status":"pending_expiry",
  "external_retention_status":"policy_retention_pending"
}
```

`access_revoked=true` nói về hệ thống này, không khẳng định vendor đã xóa ngay. Verification inventory phải gồm raw/derived files, raw text, sanitized, spans/chunks/vectors, model payloads, result/revision/citation PII, temp/cache và backup deletion marker. Decision/audit giữ phần tối thiểu theo policy; không giữ nguyên quote dưới lý do “audit”. Candidate còn application khác chỉ giữ những dữ liệu cần thiết thuộc application chưa xóa; không giữ nguồn đã xóa làm evidence cho application khác.

## 13. Hợp đồng score, current/stale và derived fields

Hàm domain nhận approved rubric + đủ sáu criterion outcomes. Validate trước tính:

1. ID set đúng sáu, không trùng/thiếu; status trong enum.
2. `assessed` có score integer0..4 và ít nhất một evidence span thuộc đúng source; các null statuses score=null; conflicting phải có nguồn giải thích mâu thuẫn theo04.
3. Weight lấy từ rubric; sum100; chưa enough evidence không tự biến thành0.
4. `coverage=sum(weights assessed)/100`.
5. `observed_score=100*sum(weight*score/4)/sum(weights assessed)` hoặcnull khi mẫu số0.
6. `comparable_score=observed_score` chỉ khi coverage=1, không conflict, output valid, technical succeeded/current; historical scalar có thể lưu nhưng API chỉ cho sort current complete.
7. `needs_clarification` nếu có criterion null; còn lại `consider_next_round` nếu comparable≥threshold và core floors đạt; còn lại `review_required`.

`allowed_actions` là UI convenience, không thay authorization trên action endpoint. `is_stale`/`requires_reconfirmation` tính trên current pointers/generations ngay mỗi read/action, không chờ background sweeper. Đổi identity/contact không làm assessment stale vì không là input đánh giá; sửa CV/JD/rubric/sanitized hoặc revoke approval thì có. Chỉ thay title requisition không ảnh hưởng rubric hash nên không làm run stale; đừng dùng toàn bộ row_version requisition như điều kiện semantic staleness.

## 14. Migration, indexes và acceptance tests bắt buộc

### 14.1. Trình tự migrations

1. Auth/roles/organization/requisitions/membership/grants.
2. Candidate/application/document/sanitized/provenance.
3. JD/rubric/release/run/criterion/evidence.
4. HR revision/attestation/decision/interview banks/drafts/revisions.
5. Jobs/invocations/budget/idempotency/audit/deletion/onboarding.
6. pgvector extension + chunks/indexes; có chế độ fulltext khi embedding chưa ready, không silently bỏ feature flag.

Có thể chia nhỏ migration theo FK cycles: application current pointers thêm sau bảng đích; mọi current pointer nullable khi chưa có nguồn. Không tắt FK để seed pass. Seed admin/synthetic là command riêng, không gắn real default password vào migration.

Index tối thiểu: session token_hash; membership(user_id,active); grant(app,user,expires_at); application(req,received_at,id); document(app,version_no); span(source,start_cp); chunk(source,config); assessment(app,run_no); job claimable queue + lease expiry; audit(req,time,id); deletion active target; idempotency scope key. Với ít chunk per-CV, exact vector search là baseline; ANN index chỉ thêm sau benchmark theo04, không bắt buộc HNSW mặc định.

### 14.2. Contract/integration tests nghiệm thu

- Hai user khác membership không đọc chéo qua path, list filter, span_id, job_id, raw download hoặc candidate identity.
- Admin không grant không raw; revoke/expiry grant được kiểm tra lại ở mỗi request, không chỉ lúc tạo link.
- Upload10.485.761bytes, PDF quá10trang, DOCX zip bomb, MIME spoof, traversal filename, missing parser trả lỗi đúng; không có file ngoài storage root.
- Same Idempotency-Key+same payload tạo đúng một resource; khác payload409; simultaneous duplicates không gọi hai lần; active run unique enforced.
- Missing If-Match428, old If-Match412; stale semantic snapshot409 dù row version có vẻ khớp.
- Citation tiếng Việt, emoji/supplementary Unicode và CRLF→LF resolve đúng; mismatch quote bị reject, không fuzzy repair.
- Schema output đủ sáu IDs nhưng có duplicate ID bị reject; score0 không evidence reject; null score không trở thành0.
- Crash sau file rename/trước DB commit có orphan cleanup; crash sau LLM admission/trước settlement tạo outcome_unknown, không auto double-call.
- Lease cũ không heartbeat/commit sau reclaim; deleting app không được worker tái tạo payload/vector; queued cancellation không gọi provider.
- Rubric/source đổi lúc owner đang xem form: finalize/decision409; hai owner concurrent decisions không overwrite; finalized HR revision/AI output immutable.
- Manual HR revision hoạt động khi API lỗi nhưng source hợp lệ; OCR thất bại vẫn cho owner có grant đọc safe raw và quyết định qua manual-document attestation.
- Technical request cho phép request_information không có sanitized text; từ chối advance/not_advance, giả mã lỗi, sai document hoặc raw file không qua safety.
- Cancel running analysis trước manual decision: response đến muộn không publish nguồn/result; usage vẫn settle; manual decision không tăng AI success/score agreement metric.
- Deletion scope application không xóa application khác của candidate; candidate deletion purge toàn bộ; restore áp deletion markers trước phục vụ traffic.
- OpenAPI client contract và các fixture thực phải dùng UUID/hash/codepoint lengths tính đúng; không copy các ví dụ placeholder trong tài liệu làm fixture valid.

## 15. Phase guards và annotation không lộ AI

`organizations.environment` vẫn chỉ `sandbox|pilot`; `pilot_stage` là null khi sandbox, `shadow` mặc định khi tạo deployment pilot, `assisted` chỉ sau gate06/09. Nhãn UX suy ra hai field này. Runtime config không cho browser tự đổi stage. Lệnh vận hành `talentscreen gates activate --stage shadow|assisted --report <restricted-report>` phải validate report hashes, source/manifest/rubric versions, approver HR/IT và gate bắt buộc, rồi cập nhật stage + audit atomically. Đây là lệnh cần implement trong B25, không lệnh có sẵn trong bộ plan. Admin vận hành không tự thay chữ ký HR bằng account admin. Không dùng cờ `all_gates_pass=true` tùy ý.

Shadow có các điều chỉnh authorization/projection bắt buộc:

- Worker có thể tạo immutable AI runs trong restricted store; mọi application list/detail/assessment/history/interview/cache API cho người dùng nghiệp vụ **không trả score, recommendation, criterion rationale, AI evidence selection hoặc AI-generated questions**. Response chỉ safe technical status và `ai_visibility:"withheld_shadow"`; endpoint cần nội dung AI trả409 `SHADOW_RESULT_WITHHELD`. Job result_ref không mở lối đọc bỏ guard. Admin không có đường xem payload nhờ role admin.
- HR vẫn đọc sanitized source/rubric, ghi HR-only revision `base_run_id=null` hoặc dùng manual document/technical basis để quyết định. Attest AI run bị chặn trong shadow. UI không chỉ dùng CSS để che dữ liệu đã tải về. Cancel/race rule ở5.4 vẫn áp dụng nếu đang có job chưa hoàn tất.
- B19 chọn **annotation qua JSON export/import cục bộ có quyền**, không xây portal gán nhãn riêng trong MVP. `talentscreen eval export --round <id> --rater <user>` xuất chỉ approved sanitized spans + rubric + blank label template; không AI output, identity hoặc nhãn người khác. Directory nằm trong private storage với quyền hạn chế; chia tệp cho đúng người theo quy trình trường, không gửi bằng công cụ ngoài mặc định.
- `talentscreen eval import-labels` xác thực actor/rater/scope, JSON shape như06§3.2, exact source/rubric hashes và nguồn evidence. Label ở private blob store; metadata `evaluation_label_sets` gồm app/document/sanitized/rubric IDs, opaque rater ID, round ID, label_kind `hr_independent|adjudicated`, revision, content_hash/blob_key, `frozen_at nullable`. Không gán nhãn independent cho HR revision được tạo sau khi nhìn AI. Lưu các phiên bản riêng, freeze bất biến, audit; xóa application phải purge cả labels/reports chứa nội dung liên quan.
- Mỗi `evaluation_rounds` row có dataset manifest/hash, application snapshot refs, planned raters, frozen model/rubric manifest, phase `collecting|labels_frozen|reported`, `labels_frozen_at`, `report_blob_key nullable`, `report_hash nullable`. Chỉ coordinator được owner chỉ định rõ trong round và có membership liên quan mới export/import/freeze/report qua CLI authenticated local; đây là assignment trong round, không account role mới. Labels một rater không được đưa cho rater khác trước freeze. Người chạy command có admin OS là giới hạn local-trust đã nêu05, không tuyên bố chống được chủ máy toàn quyền.
- Báo cáo khác biệt chỉ mở sau freeze nhãn của round; đối với real shadow còn yêu cầu các quyết định HR tương ứng đã được ghi/đóng băng. Không sửa labels independent từ kết quả AI rồi giữ tên independent. Nếu còn hồ sơ đang chấm trong một round, chỉ xuất báo cáo tổng hợp không chứa nội dung tiết lộ; báo cáo từng hồ sơ chờ round đóng.
- Bước đánh giá independent cần spans/sanitized để so cùng tập thông tin. Case chỉ có raw manual, parse thất bại hoặc HR dùng nguồn ngoài CV được ghi ở funnel/missing labels, không tự biến thành cặp score hợp lệ.
- Chuyển assisted không tự thay decision đã ghi hoặc công bố bulk score để chọn top-N. Các version trong gate phải còn đúng; code/model/rubric đổi cần regression và gate tương ứng. Privacy revoke/quarantine/deletion áp trước mọi phase/report access.

Test tối thiểu: shadow user gọi trực tiếp endpoint/list/interview/job-ref vẫn không thấy AI; HR-only revision và quyết định hoạt động; export không có nhãn/AI của người khác; import sai source/rater bị chặn; report trước freeze bị chặn; deletion dọn label/report dẫn xuất; stage promotion thiếu report hoặc report sai manifest bị chặn. B19 triển khai import/export/report, B22 kiểm access và B25 kiểm stage activation. Những endpoint/command mang tên trong spec là hợp đồng cần viết, chưa được thực thi.
