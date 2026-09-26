# 02 — Kiến trúc triển khai và ranh giới xử lý

Tài liệu đặc tả, chưa phải hệ thống đã triển khai. Quyết định nền ở [00-scope-decisions.md](00-scope-decisions.md) có ưu tiên cao hơn. Hợp đồng dữ liệu/API ở [03-data-api-state-machines.md](03-data-api-state-machines.md), AI ở [04-ai-rag-prompts.md](04-ai-rag-prompts.md), bảo mật ở [05-security-privacy.md](05-security-privacy.md), vận hành ở [07-operations-deployment.md](07-operations-deployment.md).

## 1. Kiến trúc được chọn và điều không xây trong MVP

- Một modular monolith FastAPI; một Python worker dùng cùng domain/service/repository code, entrypoint riêng.
- PostgreSQL là nguồn sự thật cho nghiệp vụ, job, ngân sách, audit và metadata file. pgvector giữ embedding sanitized, không giữ vector raw.
- Một BlobStore abstraction: adapter filesystem riêng tư cho local/CPU Docker; không bắt buộc S3. Trả file qua backend có kiểm tra quyền, không mount thành public URL.
- Next.js render giao diện; không chứa khóa DeepSeek, không tự tính điểm quyết định, không gọi thẳng model từ browser.
- Queue bằng bảng PostgreSQL và lease; một worker, concurrency mặc định 1. Không Redis, Celery, Kafka, microservices, Kubernetes hoặc agent tự lập kế hoạch.
- Chỉ một organization trong mỗi deployment. `organization_id` giữ trong thực thể để tránh nhầm dữ liệu và kiểm tra consistency; không có giao diện tạo tenant, billing SaaS hoặc cách ly đa tenant bằng RLS trong MVP.
- Sandbox và pilot là hai deployment/database/volume/secrets khác nhau. Không dùng một cột `is_demo` làm ranh giới duy nhất. Copy từ pilot sang sandbox bị cấm; seed synthetic là luồng mặc định.

## 2. Hai topology bắt buộc chạy cùng code

### 2.1. Development trên MacBook Air M4

```text
Browser
  └─ http://localhost:3000 (Next.js native)
       └─ /api/* reverse proxy → FastAPI native 127.0.0.1:8000
                                 ├─ PostgreSQL + pgvector (Docker; bind localhost)
                                 ├─ private filesystem volume (ngoài public/)
                                 └─ PostgreSQL job queue
                                      └─ Python worker native
                                           ├─ parser/OCR helper container (CPU, no network)
                                           ├─ local embedding CPU hoặc MPS
                                           └─ egress gateway → DeepSeek HTTPS
```

`MPS` chỉ là lựa chọn embedding trong Python native sau capability probe; không giả định GPU Apple được truyền vào Linux Docker. Parser/OCR và DB không phụ thuộc MPS. Máy ít RAM phải chuyển embedding CPU hoặc full-text baseline, giảm batch size; không âm thầm đổi model embedding. Next.js proxy tạo same-origin cho session cookie/CSRF; không bật CORS `*` với cookie.

### 2.2. Deploy-ready CPU profile

```text
TLS reverse proxy
  ├─ / → Next.js container
  └─ /api/* → FastAPI container
                   ├─ PostgreSQL/pgvector container (private network)
                   ├─ shared private file volume
                   └─ worker container (CPU; cùng version backend)
```

Profile này phải pass smoke test bằng Docker Compose trước bàn giao. Chưa yêu cầu publish cloud. FastAPI và worker dùng cùng image với command khác nhau; chạy migration bằng một job/command rõ ràng trước khi mở traffic, không để mọi replica tự chạy migration. Worker cần quyền ghi file công việc; frontend không mount raw volume. DB không public port khi deploy. Reverse proxy/backend thống nhất giới hạn body upload và timeout; API upload không chờ OCR/LLM.

### 2.3. Cấu hình tối thiểu

| Biến/nhóm | Ý nghĩa và default |
|---|---|
| `APP_ENV` | `sandbox` mặc định, `pilot` chỉ khi qua gate |
| `DATABASE_URL` | Secret; không log |
| `PRIVATE_STORAGE_ROOT` | Đường dẫn tuyệt đối ngoài source/public; namespace deployment |
| `APP_ORIGIN` | Origin duy nhất được chấp nhận cho cookie requests |
| `LLM_PROVIDER` | `mock` mặc định; `deepseek` khi capability/rate-card/budget đã được xác minh |
| `DEEPSEEK_MODEL` | `deepseek-chat` cho đến probe; không fallback identifier |
| `DEEPSEEK_API_KEY` | Chỉ API/worker cần thiết; không cấp cho frontend |
| `EMBEDDING_DEVICE` | `auto`, probe rồi pin actual device vào manifest |
| `EMBEDDING_MODEL_REVISION` | Commit/revision được benchmark; không `latest` trong pilot |
| `UPLOAD_MAX_BYTES`, `UPLOAD_MAX_PAGES`, `UPLOAD_BATCH_MAX_FILES` | 10 MiB (10.485.760 bytes), 10 trang, 20 file; cùng giá trị ở API/UI/parser |
| `WORKER_CONCURRENCY`, `LLM_MAX_CONCURRENCY` | 1, 1 |
| `JOB_LEASE_SECONDS`, `JOB_HEARTBEAT_SECONDS` | 120, 20; chỉ là default thử nghiệm |
| `JOB_STAGE_TIMEOUTS` | Phân theo parse/OCR/embed/LLM; xem tài liệu vận hành |
| `RETENTION_POLICY_ID` | Bắt buộc cấu hình policy thật trước pilot; không lấy con số mặc định làm policy trường |
| `BUDGET_*` | Theo 00 và 07; gate chặn gọi nếu thiếu rate card |

Secret thực tế đặt ngoài Git và ngoài artifact báo cáo. `.env.example` chỉ có placeholder. App startup kiểm tra cấu hình, nhưng không thực hiện cuộc gọi trả phí để health check.

## 3. Module tree mục tiêu

Tên file dưới đây là kiến trúc mục tiêu để AI triển khai, không phải file đang tồn tại.

```text
apps/web/
  src/app/                         # routes theo 01; page/layout/loading/error
  src/features/{auth,requisitions,applications,review,onboarding}/
  src/components/{evidence,score,status,forms}/
  src/lib/{api,csrf,formatting}/    # client types sinh từ OpenAPI
services/backend/
  app/main.py                     # app factory, middleware, routers
  app/config.py
  app/api/v1/{auth,users,requisitions,documents,assessments,reviews,jobs,audit}.py
  app/domain/
    enums.py                      # một nguồn định nghĩa enum
    scoring.py                    # pure functions; không LLM/DB
    authorization.py              # policy predicates; default deny
    snapshots.py                  # canonical hashes; stale checks
    state_rules.py                # transition guards
  app/services/
    intake.py                     # upload admission, file validation dispatch
    sanitization.py               # immutable versions, approval/revocation
    requisitions.py               # JD/rubric lifecycle
    assessment.py                 # admission + snapshot + persistence
    human_review.py               # HR revisions/attestations/decision
    deletion.py                    # tombstone, purge, reconciliation
    jobs.py                       # enqueue/claim/renew/cancel/complete
    budgets.py                    # reservations + settlement
    audit.py                      # allowed metadata only
  app/repositories/               # SQLAlchemy queries; no auth assumptions
  app/db/{models,migrations}/
  app/contracts/                  # Pydantic input/output; schema versions
  app/ai/
    provider.py                   # interface; mock/deepseek adapters
    prompts/                      # immutable release bundles
    orchestrator.py               # bounded task pipeline
    validation.py                 # schema + evidence registry + rubric checks
    retrieval.py                  # fulltext/hybrid strategy; no hiring decisions
    embedding.py                  # pinned model; CPU/MPS
  app/documents/
    parsers/{pdf,docx,ocr}.py
    normalize.py                  # NFC + LF canonical text
    sanitizer.py                  # spans + forbidden-data rules
    spans.py                      # deterministic source registry
    rendering.py                  # safe sanitized/plaintext rendering
  app/infrastructure/
    blob_store.py                 # private files; generated paths
    telemetry.py                  # metadata metrics/logs
    clock.py                      # injectable clock for lease/expiry tests
  app/worker/{main,handlers}.py
  tests/{unit,integration,security,contract,fixtures}/
packages/contracts/               # generated TS/OpenAPI artifact, không edit tay
infra/{compose.local.yml,compose.cpu.yml,proxy/}
scripts/{seed_sandbox,capability_probe,backup,restore_smoke,retention_sweep}/
evaluation/                       # datasets manifests; không commit raw real CV
```

Router chỉ parse/authenticate/authorize rồi gọi service; service sở hữu transaction và business invariants; repository không commit tự ý. Domain scoring là hàm xác định được kiểm thử độc lập. Tất cả đường gọi LLM đi qua `provider.py` + admission/budget guard; không để agent/route gọi SDK trực tiếp.

## 4. Luồng nghiệp vụ từ đầu đến cuối

### 4.1. JD và rubric

1. Owner tạo requisition và JD version, rà tiêu chí bị cấm.
2. Trước gửi JD ra provider, người có quyền xác nhận nội dung JD được phép gửi; draft rubric là job hữu hạn. Seed/template có thể dùng không gọi LLM.
3. LLM draft luôn là đề xuất. Backend validate criteria IDs/anchors/weights/source references; owner sửa và approve một rubric version.
4. Approval khóa nội dung rubric và threshold config. Đổi rubric tạo version mới. Requisition trỏ đến approved version hiện tại.
5. Run đã tạo không đổi snapshot. Đổi pointer rubric làm kết quả trước đó stale theo phép so sánh snapshot; không cần fan-out cập nhật mọi row application.

### 4.2. CV và sanitization

1. HR upload; hệ thống kiểm tra quyền, file size/type và idempotency; lưu quarantine bằng generated UUID path.
2. Worker kiểm tra file thực, page count, giải nén DOCX có giới hạn, parse/OCR có timeout/resource limit. Tài liệu không đạt không bị cắt ngắn để tiếp tục chấm.
3. Lưu raw artifact/trích xuất ở private vault; tạo sanitized draft cùng mapping nguồn. Nội dung chưa duyệt có thể còn PII nên dùng quyền raw cho màn hình sửa.
4. HR được phân công + raw grant xem raw/sanitized cạnh nhau, sửa bản sanitized nếu cần; owner có raw grant duyệt cuối. Mỗi lần sửa tạo content version mới, không sửa body nguồn đã xuất bản.
5. Approval do owner có raw_cv grant thực hiện, gắn user, timestamp, hash cụ thể. Chỉ bản này được embedding/gửi LLM. Sửa lại nội dung làm mất hiệu lực approval của nội dung mới; không tái sử dụng approval cũ.
6. Display provenance từ immutable sanitized text, không yêu cầu model tự tạo page/offset. Viewer raw là hành động riêng được audit.

### 4.3. Assessment

1. API kiểm tra quyền và preconditions: application active, CV/sanitized hiện hành approved, rubric approved, requisition cho phép xử lý, budget/policy config.
2. Trong một transaction: khóa application + requisition theo thứ tự cố định; tạo exact snapshot; tạo run + job + budget admission metadata + audit.
3. Worker nhận job, kiểm tra fence/tombstone/current generation. Build context chỉ từ source IDs trong snapshot. Chạy full-text baseline hoặc hybrid strategy đã ghim.
4. Model chỉ trả criterion assessment. Backend validate schema, ID, evidence, constraints; tính score/recommendation bằng code.
5. Commit kết quả chỉ khi lease fence còn hợp lệ và application chưa xóa. Nếu nguồn hiện tại đã thay đổi, lưu terminal `stale` kèm kết quả lịch sử nếu không có deletion; không đưa vào current recommendation.
6. HR xem từng tiêu chí; giữ nguyên AI hợp lệ thì attest trực tiếp, sửa thì tạo/finalize revision trước attestation và quyết định của owner. Khi OCR thất bại nhưng tài liệu đã qua kiểm tra an toàn và người đọc được, owner có raw grant có thể dùng manual document review + attestation theo03, không tạo AI score giả. Khi chưa có tài liệu đọc được, owner có thể request_information với technical basis. Không có đường từ LLM output đến hiring decision.

### 4.4. Interview

Chỉ khi HR yêu cầu; snapshot tiêu chí và assessment/HR revision hiện hành. Output gồm câu hỏi có mục đích và nguồn theo schema AI. Không tự gửi ứng viên. Source thay đổi thì bộ câu hỏi stale. Không cần lưu một agent conversation kéo dài.

## 5. Queue, transaction và at-least-once execution

### 5.1. Nguyên tắc

Không giữ transaction/row lock mở trong thời gian parse/OCR/model call. DB transaction ngắn; external side effect không nằm trong transaction. Queue có thể xử lý một job nhiều lần; **exactly-once billing external API không được hứa**. Idempotency bảo vệ việc ghi kết quả và tạo job nghiệp vụ, không mặc nhiên bảo vệ lời gọi provider.

### 5.2. Claim và fencing

- Claim chọn job `queued/retry_wait` đã tới `available_at`, chưa cancellation, rồi khóa row bằng chiến lược skip-locked.
- Transaction claim đặt `status=running`, tăng `lease_epoch`, tăng `claim_count`, tạo `lease_owner`, đặt `lease_expires_at` từ thời gian DB.
- Mỗi publish/write nội dung/complete yêu cầu `(job_id, lease_epoch, lease_owner)` đúng, lease còn hạn, `cancel_requested_at IS NULL` và target chưa tombstone. Heartbeat/settle cost/đánh dấu terminal cancellation có nhánh riêng cho job đã yêu cầu dừng; không được publish kết quả sau cancel. Nếu update affected rows = 0, worker đã mất quyền commit.
- Lease heartbeat chạy định kỳ; chặn heartbeat không được kéo dài HTTP call vô hạn. External request có timeout riêng; stage có deadline.
- Sweeper chỉ reclaim lease hết hạn nếu còn attempts và không có unresolved external invocation. Trường hợp crash giữa provider request/response chuyển `provider_outcome_unknown`, cần reconciliation theo 07, không tự gửi lại mù.
- Hai worker cũ/mới có thể cùng chạy CPU ngắn; chỉ worker có fence mới được commit. Mọi write artifact dùng attempt-specific temp path; loser cleanup riêng.

### 5.3. Ba loại version không được nhập làm một

| Trường | Bảo vệ điều gì |
|---|---|
| `row_version` | Optimistic concurrency khi người dùng sửa entity |
| `application_generation` | Mọi thay đổi nguồn nghiệp vụ: CV hiện tại, sanitized approval, deletion/cancel supersession theo rule |
| `job.lease_epoch` | Worker ownership khi lease được reclaim |

Rubric hiện hành dùng `requisition.current_rubric_version_id` + `requisition.row_version`; run snapshot lưu cả. API không nhận tùy ý generation từ client để ghi đè; chỉ dùng `If-Match` để kiểm tra version đã đọc.

### 5.4. Transaction boundaries bắt buộc

| Hành động | Trong transaction | Ngoài transaction / recovery |
|---|---|---|
| Nhận upload | Metadata document, app linkage, enqueue ingest, audit | Stream temp file + checksum trước; atomic rename trước metadata commit; orphan sweeper xử lý file không được tham chiếu |
| Duyệt sanitized | Lock app/source; approved hash; cập nhật current source/generation; audit | Embed sau bằng job nếu cần |
| Duyệt rubric | Lock requisition; freeze version; update pointer/version; audit | Không gọi LLM trong approval |
| Tạo assessment | Lock req/app; validate exact source; snapshot + run + job + idempotency record; audit | Provider sau claim |
| Commit assessment | Fence + deletion/generation check; output + criterion rows + score + job terminal + audit | Mọi external usage settlement ghi riêng dù output không còn current |
| Final decision | Lock req/app; current snapshot + basis-specific guards + attestation của owner + expected version theo03; immutable decision event; update current pointer; audit | Không gửi mail/ATS trong MVP |
| Request deletion | Lock target; tombstone + generation bump + cancellation + revoke grants/tokens + deletion job + audit | Purge file/vector/provider reconciliation bất đồng bộ |

DB commit thành công là ranh giới API success. Nếu audit bắt buộc không ghi được cùng transaction, mutation nghiệp vụ rollback. Logs quan sát bổ sung không thay audit nghiệp vụ.

### 5.5. Idempotency

`POST` tạo application, upload, assess, reassess, approve, finalize, decision và deletion phải có `Idempotency-Key` UUID do client sinh một lần cho một thao tác. Scope key gồm actor, method, route family và resource. Server lưu hash canonical body (upload dùng file checksum+metadata), status code và response reference.

- Cùng key+cùng request trả cùng resource; không enqueue job hay gọi provider lần nữa.
- Cùng key+khác request trả `409 IDEMPOTENCY_CONFLICT`.
- Hai request đồng thời được xử lý bằng unique constraint + transaction, không check-then-insert thiếu khóa.
- Retention key mặc định 7 ngày trong sandbox; policy pilot cấu hình. Expired key không cho phép vượt unique domain constraint của active run.
- Mỗi application chỉ một assessment run non-terminal. Reassess yêu cầu không có run active hoặc explicit cancel trước; không tạo hàng loạt job trùng.

Thứ tự kiểm tra bắt buộc cho request có idempotency key:

1. Authenticate session; kiểm tra quyền hiện tại, resource scope, tombstone và quarantine. Key cũ không cấp lại quyền đã bị thu hồi. Endpoint metadata của deletion request có thể trả tiến độ cho người có quyền; ngoại lệ này không cho đọc lại CV hoặc kết quả đã xóa.
2. Tìm idempotency record trong đúng actor/method/route/resource scope; xác minh request hash. Nếu đã hoàn tất và request giống nhau, trả lại cùng resource/status đã ghi mà không chạy mutation hoặc kiểm tra lại `If-Match` cũ. Trước khi serialize vẫn áp projection/quyền đọc hiện tại; không replay response payload đã cache để vượt tombstone, raw grant expiry hoặc quarantine. Response resource sau này đổi trạng thái có thể được đọc mới qua GET; replay không tạo một phiên bản nghiệp vụ mới.
3. Nếu key mới, kiểm tra `If-Match` và toàn bộ domain guards trong transaction trước mutation. Concurrent request cùng key phải đi qua unique constraint; request thua đọc kết quả đã commit hoặc chờ/poll bounded nếu request đầu còn xử lý.

Điểm quan trọng của thứ tự này: khi server đã tăng row version nhưng client mất response, retry cùng key không bị trả412 chỉ vì vẫn gửi ETag ban đầu. Ngược lại, request mới với ETag cũ vẫn nhận412. Contract tests phải kiểm tra cả hai và trường hợp replay sau revoke quyền/quarantine/delete.

### 5.6. Cancel, source change và deletion race

Cancel là cooperative, không hứa thu hồi request đã gửi provider. Đặt cancel flag ngay; worker kiểm tra trước mỗi stage, trước egress và trước commit. Nếu source thay đổi trong khi model đang chạy, output lịch sử không trở thành current. Không hoàn lại chi phí thực tế đã phát sinh.

Deletion ưu tiên hơn mọi work: transaction đánh dấu tombstone, ngắt quyền đọc ngay, tăng generation, cancel jobs, tạo purge task. Egress gate khóa/check app ngay trước admission invocation; request đã được admitted trước thời điểm tombstone có thể đang in-flight. Worker không được persist payload/embedding/output của app đã tombstone; usage metadata tối thiểu có thể được settle không chứa PII. Deletion job chỉ complete khi pipeline đã quiescent và inventory purge đạt; nếu provider outcome chưa rõ, báo phần external retention theo policy thay vì tuyên bố đã xóa toàn bộ.

Một script reconciliation cần tìm: orphan temp blobs, jobs lease expired, admissions chưa settled, tombstoned app còn chunk/vector, rows trỏ file thiếu. Chỉ dọn dữ liệu đã xác định ownership; không `rm -rf` trên đường dẫn do người dùng cung cấp.

## 6. Ranh giới tin cậy và bảo mật kiến trúc

- Browser gửi input không tin cậy; actor/resource scope luôn được backend suy ra từ session và membership.
- CV/DOCX/PDF là input không tin cậy. Parser không thực thi macro, không fetch external URL, không cài package từ file, không truy cập key provider.
- Sanitized text vẫn có thể chứa prompt injection và vẫn là dữ liệu cá nhân theo context. LLM không có tools ghi DB/gửi mail/tìm web.
- API session opaque server-side, cookie HttpOnly/Secure ở deploy/SameSite, CSRF token cho mutation; HTTPS ở deploy. Admin reset user không gửi password qua log/email trong MVP.
- Admin role quản lý người dùng/config không mặc nhiên đọc applicant identity/raw. Membership giới hạn requisition. Raw grant là quyền bổ sung có hạn, không thay membership.
- DB/files at rest dựa trên volume encryption được xác minh (FileVault ở máy Mac thật) và backup mã hóa; không xây một KMS giả trong MVP.
- Audit/log/metrics không giữ raw text, prompt hoặc tên ứng viên. Exact model payload cần lưu để audit thì chỉ trong encrypted-at-rest private store, quyền assessment scoped, có retention/delete; không đưa vào telemetry vendor.
- Render văn bản bằng escape mặc định; không `dangerouslySetInnerHTML` với CV/model. Evidence preview dùng sanitized canonical text; PDF raw download tách origin/attachment nếu cần theo tài liệu security.

## 7. Quan sát, version và release

Mỗi request có `request_id`; mỗi job/run có UUID. Metric labels chỉ dùng stage/status/model release, không candidate_id hoặc prompt text. Audit có actor/action/entity/version/result, không chứa full source.

Release manifest bất biến gồm app commit, prompt bundle, schema version, model identifier+parameters, parser/sanitizer/renderer/retriever versions, embedding revision/dimension, rate-card version và config hash. Run lưu actual resolved values, không chỉ tên alias `production`. Có source snapshot file/hash để debug; chỉ checksum không đủ dựng lại context.

Rollback dùng một release bundle tương thích và migration strategy. Không rollback schema phá hủy dữ liệu để cứu prompt lỗi; deployment trước đó phải đọc được schema mở rộng hoặc có migration forward fix. Đổi embedding model/revision cần namespace index mới + re-embed approved sources; không trộn vector ở cùng index config. Backup/restore và xóa sau restore theo 05/07.

## 8. Những trade-off đã chủ động chấp nhận

| Quyết định | Lợi ích | Giới hạn và điểm mở rộng |
|---|---|---|
| Một worker + PostgreSQL queue | Dễ debug, kiểm soát chi phí | Throughput thấp; chỉ tăng worker khi fencing/rate limit đã test |
| Native Python trên Mac | Dùng MPS khi thực sự hữu ích | Cần CPU smoke test để tránh phụ thuộc máy cá nhân |
| Private filesystem | Ít dịch vụ vận hành | API/worker phải cùng volume; mở rộng nhiều host cần BlobStore adapter khác |
| HR approve sanitized | Giảm rủi ro egress và có kiểm tra nguồn | Thêm thời gian HR; đo cả thời gian này vào hiệu quả sản phẩm |
| Application-level auth | Đủ cho một tổ chức nếu phủ integration tests | Không được quảng cáo là multi-tenant isolation; RLS chỉ cân nhắc sau |
| Immutable snapshots | Audit, rollback và so sánh dễ | Tốn storage; bắt buộc retention/delete có inventory |
| Fulltext baseline trước RAG | Ít lỗi retrieval cho CV ngắn | Context/token phải được kiểm tra trước call; không truncate ngầm |

## 9. Definition of Done của kiến trúc

1. Sandbox chạy end-to-end bằng mock provider trên Mac native profile và CPU Docker profile.
2. Worker chết/restart không tạo hai kết quả current hoặc hai final decisions; provider outcome unknown được chặn retry theo thiết kế.
3. Test cạnh tranh gồm rubric đổi lúc run đang chạy, sanitized edit trong review, hai HR cùng finalize, cancel lúc request đang chạy, delete lúc embedding/LLM commit.
4. Người không có membership nhận 404 cho resource; admin không raw grant không lấy được raw; revoke session/grant có hiệu lực theo policy.
5. Không model/API secret trong frontend bundle/log; không raw CV trong git/test report/metrics.
6. Không đạt performance bằng cách bỏ page, bỏ tiêu chí hoặc đếm `needs_manual_review` thành AI success.
7. README có command bootstrap, migration, seed synthetic, smoke test, backup/restore và worker stop; tài liệu ghi rõ gate pilot chưa đạt nếu chưa có dữ liệu kiểm chứng.
