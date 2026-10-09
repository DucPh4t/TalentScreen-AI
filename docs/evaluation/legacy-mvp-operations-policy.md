# 07 — Local runtime, chi phí, SLO và chuẩn bị deploy

> Historical MVP proposal (26 September 2026), retained as the source of the legacy benchmark threshold profile. This is not the current runtime setup or a record of passing gates. See [current readiness](../runbooks/rag-agent-readiness.md), [reproduction](ai-benchmark-reproducibility.md), and the root README for current commands.

## 1. Mục tiêu môi trường

Ưu tiên một người có thể cài, chạy, debug và phục hồi trên MacBook Air M4. Không chạy DeepSeek đầy đủ trên laptop; DeepSeek là API remote đã được phép theo trường. GPU tích hợp dùng cho embedding khi MPS chạy ổn; parser/OCR chủ yếu CPU. Dung lượng RAM chưa kiểm tra được trong phiên lập plan, nên không khẳng định cấu hình máy đáp ứng một throughput cụ thể.

Apple mô tả PyTorch GPU acceleration qua MPS trên Apple Silicon. Docker Desktop không nên được cấu hình dựa trên giả định `--gpus all` sẽ truyền GPU Apple vào Linux container; hướng dẫn GPU Desktop được Docker công bố cho Windows/WSL2. Vì vậy chọn native Python cho MPS, có đường CPU khi cần. [Apple MPS](https://developer.apple.com/metal/pytorch/), [Docker GPU](https://docs.docker.com/desktop/features/gpu/).

## 2. Hai profile cần triển khai

| Thành phần | `local-native` — mặc định phát triển/pilot cùng máy | `docker-cpu` — kiểm thử đóng gói và chuẩn bị cloud |
|---|---|---|
| PostgreSQL + pgvector | Container, persistent volume, port chỉ loopback | Container/private network, không public port |
| FastAPI | Native Python virtual env | Container non-root |
| Worker | Native, một process, MPS hoặc CPU | Container CPU, một worker |
| Next.js | Native Node, proxy `/api` để cùng origin | Container build production |
| Parser/OCR helper | Container local không network; file input hẹp; CPU | Cùng image/helper profile CPU |
| Storage | Private directory ngoài repo/sync drive | Persistent encrypted volume khi deploy |
| TLS | Loopback local HTTP dev; HTTPS nếu truy cập ngoài máy | Reverse proxy TLS khi cloud/LAN |

MPS không phải acceptance blocker nếu CPU đạt nhu cầu pilot; benchmark và ghi device thực. Không nhân nhiều worker MPS khi chưa đo RAM và race. Laptop sleep sẽ dừng tiến độ: hiển thị worker heartbeat và stale queue, không giả định máy hoạt động 24/7. Khi pilot đã chạy, có owner giữ máy thức trong giờ làm việc theo chính sách IT và backup trước khi tắt.

### 2.1 Bootstrap và dependency policy

- Chọn một Python stable còn được dependency hỗ trợ (baseline đề xuất 3.12) và Node LTS tương thích Next.js tại lúc implement; pin phiên bản thực tế bằng lockfile sau smoke test. Đây là lựa chọn nền, không yêu cầu dùng package latest không pin.
- Python: FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, driver PostgreSQL, httpx, sentence-transformers/PyTorch, parser/OCR client, password hashing và pytest.
- Frontend: Next.js App Router + TypeScript, UI form/table cơ bản, client API types sinh từ OpenAPI, Playwright. Chọn thư viện nhỏ, không thêm state framework nếu server state/form state đã đủ.
- Parser container: extractor PDF có text, OCR Tesseract có `vie` và `eng`, render PDF cho DOCX bằng công cụ được pin. Kiểm tra license và platform arm64 của các dependency trước khóa. DOCX không có pagecount thật nếu chưa render, không lấy số section làm số trang.
- Tải embedding model một lần từ revision đã pin, không bật remote code tùy tiện, bật offline cache runtime khi đã có weights. Kiểm tra dung lượng và tải trên Mac trước full dataset.
- Doctor output: OS/arch, Python/Node, Docker running, DB extension, free storage, RAM do người dùng/host cung cấp, MPS available, embedding revision, OCR languages, parser smoke, writable private directory, key present (chỉ boolean), model-probe state. Không in key hoặc full environment.

### 2.2 Make targets phải có ở bản implement

| Target | Hợp đồng |
|---|---|
| `make doctor` | Read-only environment checks; trả actionable error, không tự install hoặc gửi CV |
| `make bootstrap` | Cài dependency theo lockfile và hướng dẫn prerequisite còn thiếu |
| `make db-up` / `make migrate` | Khởi động DB riêng; apply migration bằng migration role |
| `make dev` | Chạy API/web/worker hoặc in đúng ba lệnh nếu process manager không dùng |
| `make seed-sandbox` | Tạo dữ liệu synthetic + accounts test local; không chạy trên real environment |
| `make provider-probe` | Gửi fixture synthetic rất nhỏ với model cấu hình; budget riêng; không tự đổi model |
| `make test` / `make test-integration` / `make test-e2e` | Unit nhanh / PostgreSQL integration / flow browser; default mock external |
| `make eval-smoke` / `make eval-dev` / `make eval-holdout` | Eval theo manifest, opt-in external, cost preflight; kiểm soát quyền holdout |
| `make load-test` | Dataset synthetic cố định, workload mô tả bên dưới, xuất counts và timing |
| `make backup` / `make restore-drill` | Encrypted backup và restore môi trường isolated, áp deletion ledger |
| `make compose-smoke` | Build/chạy profile Docker CPU và health/E2E synthetic |

Các tên lệnh là acceptance contract; trong bộ tài liệu hiện tại chúng chưa được implement. Không ghi "chạy được" chỉ vì có Makefile target trống.

## 3. Cấu hình runtime đề xuất

| Key | Default hoặc yêu cầu | Ý nghĩa |
|---|---|---|
| `APP_ENV` | `sandbox` | `sandbox`/`pilot`; khác DB/storage/credentials |
| `PILOT_STAGE` | null trong sandbox; `shadow` khi tạo pilot | Giá trị được lưu server-side theo03; chuyển `assisted` chỉ qua gate activation có audit, không browser toggle |
| `APP_BIND_HOST` | `127.0.0.1` | Không expose LAN ngoài ý muốn |
| `DATABASE_URL` | secret, không ví dụ password thật | Runtime role least privilege |
| `PRIVATE_STORAGE_ROOT` | path ngoài repository/sync | File CV và derivatives |
| `LLM_PROVIDER` | `mock` | Chỉ bật `deepseek` sau probe và config |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | Server allowlist cố định; không cho user thay arbitrary host qua web |
| `DEEPSEEK_MODEL` | `deepseek-chat` theo user | Phải probe; không tự thay alias |
| `DEEPSEEK_API_KEY` | secret | Backend/worker only |
| `EXTERNAL_REAL_DATA_POLICY` | `allowed_deepseek_confirmed_by_owner` khi setup pilot | Ghi nhận quyền đã được user xác nhận; không tự mở vendor khác |
| `REQUIRE_SANITIZED_APPROVAL` | `true` | Không tắt cho real CV |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-base` | Pin revision khi benchmark hoàn tất |
| `EMBEDDING_DEVICE` | `auto` (`mps` khi smoke pass, else CPU) | Ghi actual device, không silent MPS failure |
| `RAG_MODE` | `full_text_baseline` | `hybrid` chỉ sau benchmark + approved manifest |
| `WORKER_CONCURRENCY` | `1` | Single-host pilot |
| `LLM_MAX_CONCURRENCY` | `1` | Không vượt budget/rate/load profile |
| `UPLOAD_MAX_BYTES` | `10485760` | 10 MiB, label UI hiển thị rõ |
| `UPLOAD_MAX_PAGES` | `10` | DOCX render trước xác nhận |
| `UPLOAD_BATCH_MAX_FILES` | `20` | Chia nhiều batch nếu cần |
| `LLM_STAGE_MAX_ATTEMPTS` | `2` | Lần đầu + một retry/repair; không nhân retry các tầng |
| `ASSESSMENT_MAX_EXTERNAL_CALLS` | `4` | Gồm tất cả retry, repair và fallback |
| `LLM_READ_TIMEOUT_SECONDS` | `90` đề xuất | Điều chỉnh sau synthetic probe; tổng run deadline vẫn kiểm soát |
| `ASSESSMENT_DEADLINE_SECONDS` | `900` | Sau đó technical failure/manual, không chạy vô hạn |
| `DEV_EVAL_BUDGET_USD` | `10` | Trần đề xuất, không số tiền sẽ tự chi |
| `PILOT_MONTHLY_BUDGET_USD` | `10` | Trần đề xuất, có thể đổi qua config có audit |
| `RATE_CARD_VERIFIED_AT` | chưa có cho model user | Thiếu rate card của model thực => chặn paid batch |
| `RETENTION_POLICY_ID` | bắt buộc ở real environment | Chính sách trường; không invent luật |

Actual output token limits theo từng task và input sizing theo [current request fitter](../../services/backend/app/services/agent/request_budget.py). Key mismatch giữa docs phải được sửa trước implement; không định nghĩa nhiều biến tên khác nhau cho cùng một policy.

## 4. DeepSeek capability probe và model drift

Tại ngày rà soát, trang API/pricing chính thức hiển thị tên `deepseek-flash` và `deepseek-v4-pro`, không đủ để xác nhận tài khoản của user còn chấp nhận `deepseek-chat`. Không kết luận model user đã hỏng chỉ từ điều này. Giữ model configurable và thực hiện probe synthetic khi triển khai. [DeepSeek first call](https://api-docs.deepseek.com/), [pricing](https://api-docs.deepseek.com/quick_start/pricing/).

Probe checklist:

1. Key/base URL/model config có nhưng không log secret.
2. Một completion tiny không chứa CV thật; kiểm tra HTTP, response.model, usage và stop reason.
3. JSON mode với một schema tối giản, validate tại Pydantic; test empty/truncated content bằng mock fault, không tiêu tiền cố gây sự cố.
4. Kiểm tra non-thinking mode với đúng API/model hiện tại; nếu parameter không hỗ trợ, ghi capability, không mò nhiều request có tính phí. Không lưu reasoning payload.
5. Ghi capability manifest: requested_model, observed_model, timestamp, feature flags, schema policy, usage mapping, verified rate card URL/date, synthetic test report.
6. 400/404 model unsupported -> `PROVIDER_MODEL_UNAVAILABLE`, đưa hướng dẫn cấu hình tên hợp lệ và chạy lại eval; không fallback âm thầm. 401/402 -> xử lý credential/balance, không retry vô hạn.

JSON mode của DeepSeek yêu cầu hướng dẫn JSON trong prompt và có thể trả empty content; vì vậy branch xử lý lỗi bắt buộc. Không coi JSON mode là enforcement đầy đủ của JSON Schema. [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/).

Release manifest ghi cả requested/observed model. Nếu provider đổi alias sau probe, lần chạy phát hiện observed_model khác phải flag drift và ngăn tự so sánh với baseline cũ cho tới khi smoke eval được rà; không giả vờ pin được weights của một API alias. Rubric output, prompt version và source snapshot vẫn lưu để kiểm toán nhưng tái chạy LLM có thể khác kết quả.

## 5. Chi phí và admission control

### 5.1 Định nghĩa ledger

Lưu mỗi external attempt: task, run ID, attempt number, requested/observed model, input cached/uncached nếu vendor có, output tokens, rate_card_version, estimated_cost, actual_cost, status, request timestamp. Không ghi prompt/CV.

MVP có đúng hai budget scopes theo03: `development` gộp toàn bộ development + evaluation với cap đề xuất USD10 cho đợt triển khai; `pilot` là cap API toàn deployment theo tháng, đề xuất USD10/tháng. Chạy lại benchmark, đổi prompt hoặc tạo requisition mới không tạo thêm cap development. Evaluation vẫn có task/usage tag để phân tích chi phí nhưng không có một ví tiền hoặc hạn mức độc lập. Theo requisition chỉ là báo cáo phân bổ từ job/application liên quan; không xây parent/child budget hoặc cap riêng mỗi requisition trong MVP. Mỗi invocation thuộc đúng một scope/window, không bị ghi chi phí hai lần.

`actual_cost = uncached_input_tokens × input_miss_rate + cached_input_tokens × input_hit_rate + output_tokens × output_rate`, tất cả rate quy đổi token đơn vị rõ ràng. Nếu provider không phân biệt cache, dùng mức input cao hơn để dự trù, reconcile theo usage/billing khi có. Thời gian CPU/storage chưa nằm trong API bill nhưng phải báo riêng khi deploy.

Không dùng giá một model khác làm giá `deepseek-chat`. Rate card hiện tại của provider chỉ dùng làm nguồn tra cứu; thay đổi theo model/thời điểm. Giá phải được kiểm tra tại lúc bật model thật, không hardcode thành hằng vĩnh viễn trong business code. Không ưu tiên gửi CV vào giờ rẻ nếu làm trễ SLO mà HR chưa chấp nhận.

### 5.2 Reservation transaction

- Trước external call, estimate upper bound từ token count/giới hạn output và rate cao nhất đã xác minh của model; ghi rõ estimator version, sai số dự phòng. Nếu chưa có tokenizer tương thích, dùng giới hạn byte thận trọng đã test với provider, không giả định tiếng Việt có tỷ lệ ký tự/token bằng tiếng Anh.
- Transaction lock đúng một budget row theo scope/window, kiểm tra `spent + reserved + upper_bound <= cap`; reserve nếu đủ. Thiếu budget -> blocked/manual, không chấm điểm0. Không được chuyển invocation từ development sang pilot hoặc qua cửa sổ khác chỉ để vượt cap; caller dùng mode/environment được cấu hình và audit.
- Các retry dùng cùng run nhưng attempt ledger riêng; reservation cho attempt mới trước khi gửi. Max attempts hai và run tổng bốn calls không được nhân lên vì SDK cũng tự retry: tắt SDK auto-retry hoặc gom về đúng một tầng quản lý.
- Khi nhận usage, settle reservation. Nếu timeout sau gửi chưa biết vendor đã bill, giữ `cost_unknown` conservative; không giải phóng rồi retry miễn phí giả định. Reconcile bằng thông tin usage/billing sẵn có; uncertainty vượt cap thì chặn call mới và báo owner.
- Network call không nằm trong DB transaction lâu. Lease/fencing không ngăn provider bị gọi trùng khi worker chết giữa lúc gửi và ghi receipt; state `external_outcome_unknown` cần xử lý riêng, không hứa exactly-once billing.
- Hết cap -> giữ HR manual flow hoạt động, không tự tăng trần, mua credit hoặc đổi model rẻ hơn.

Cost dashboard: spent, reserved, unknown, remaining của hai scopes; phân bổ chi phí theo task, batch, evaluation và requisition; p50/p95 cost per completed assessment và failed-call cost. Phân bổ chỉ là reporting, không tạo thêm hạn mức. API cost/CV không được bỏ các retry thất bại khỏi tử số.

## 6. SLO: mục tiêu đo, không lời hứa đã đạt

### 6.1 Workload tham chiếu

Profile P1 cho local pilot ban đầu: một HR dùng UI, một worker, model đã warm-up, tài liệu tối đa 10 trang nhưng benchmark thường 1–5 trang, 70% PDF text/20% DOCX/10% scan đọc được, arrival trung bình tối đa một CV/phút và burst ba CV. Mỗi benchmark ít nhất 30 synthetic documents để kiểm thử cơ chế; sample này chưa đủ chứng minh độ tin cậy dài hạn.

Cho phép upload 20 file/batch, nhưng burst20 là profile P2 riêng cần đo; không đem SLO P1 gắn lên mọi batch rồi loại các job chậm khỏi mẫu. UI hiển thị queue length và trạng thái, không hứa ETA chính xác trước có số đo. Báo latency cả theo profile và toàn bộ accepted jobs.

Admission technical timing bắt đầu khi một assessment job đủ điều kiện (JD/rubric approved, sanitized approved, source parse đạt, policy/budget/config đủ) được server chấp nhận. Tính cả queue/retry đến assessment validated `succeeded`. Bên cạnh đó có metric ingestion từ upload đến sanitized ready, và metric wall-clock upload đến decision gồm chờ người. Không gọi thời gian chỉ LLM là end-to-end CV processing.

| SLI | Mục tiêu thăm dò P1 | Mẫu số/ngoại lệ |
|---|---|---|
| Assessment ready đúng hạn | ≥95% accepted assessment jobs trong 5 phút | Tính fail/timeout là không đạt; không xóa outlier. Chờ người trước admission được báo metric riêng |
| Upload -> sanitized ready | ≥95% accepted documents trong 5 phút trên P1 | Gồm parse/OCR/queue; không gồm người kiểm bản sanitized |
| OCR failure | <5% tài liệu cần OCR sau bounded retry | Mẫu số là tài liệu OCR, không toàn bộ CV; report fail reason và count |
| Privacy/authorization invariants | Không chấp nhận vi phạm đã biết | Release gate bằng test; không dùng tỷ lệ95% cho security |
| Invalid output publish | 0 kết quả sai cấu trúc/quy tắc được publish trong test | Output bị chặn vẫn tính technical failure cho completion metric |
| Worker liveness | phát hiện heartbeat stale trong ≤60 giây | Job recovery theo lease; không lập tức gửi lại API không rõ outcome |
| Local active-store deletion | ≤24 giờ sau yêu cầu hợp lệ | Khóa truy cập ngay; backup/provider status báo riêng |
| Rollback | ≤15 phút trong diễn tập đang có người vận hành | Không hứa 24/7 support trên laptop |

Chưa đặt overall technical success99% như một cam kết đồng thời với OCR fail<5% khi chưa biết document mix. Sau hai tuần pilot có thể thống nhất target cao hơn dựa trên số đo; thay mục tiêu phải có lý do/version, không sửa để che fail.

### 6.2 Error budget và escalation

Với on-time SLO95%, error budget của cửa sổ đo N job là 0,05×N. Ví dụ 100 job có năm vi phạm; 1.000 job có 50. Một job vừa timeout vừa schema-fail vẫn là một failed event trong SLI đó, nhưng có thể thuộc nhiều diagnostic counters. Dùng rolling7day report, luôn hiện numerator/denominator. [Google SRE](https://sre.google/workbook/implementing-slos/).

- Một job fail: chuyển status rõ và giữ manual review, không gửi email tự động ngoài phạm vi.
- Ba lỗi liên tiếp cùng provider/parser: circuit pause nhánh lỗi; báo người vận hành qua UI/log alert được cấu hình, không gọi lại liên tục.
- Hết budget trong cửa sổ đủ mẫu: tạm dừng feature/prompt releases không phục vụ reliability; sửa nguyên nhân và chạy benchmark lại. Low-volume pilot dùng case review kèm counts, không tự suy luận p95 đáng tin từ ba job.
- P0 privacy, cross-candidate evidence hoặc unauthorized decision: dừng chức năng bị ảnh hưởng ngay, revoke egress/credentials nếu cần; HR được báo trạng thái hệ thống và tiếp tục quy trình thủ công.

Mỗi incident lưu owner, start/end, affected runs, root cause, action và regression ID; không đính CV thô vào issue tracker.

## 7. Observability không rò payload

Structured log các field: timestamp, level, component, request_id, job_id, run_id, stage, event_code, duration_ms, attempt, token counts, cost, error_class. UUID opaque không dùng làm high-cardinality metric label. Loại field chứa quote, raw filename, contact, API key hoặc model response body. Error handler sanitize provider errors trước logging.

Dashboard MVP có thể dùng trang admin đọc aggregate DB; không bắt buộc Prometheus/Grafana. Cần tối thiểu queue depth, oldest job age, worker heartbeat, stage failure counts, processing latency, budget, output validation failures, pending sanitized review và pending HR decisions. Có health endpoints tách liveness và readiness; provider outage không làm mất khả năng đọc hồ sơ/manual review.

Polling job status 2 giây khi tab active, backoff tối đa10 giây, dừng khi terminal; không cần websocket/SSE cho MVP. Một lỗi UI polling không được tạo lại assessment.

## 8. Backup, restore và release runbook

### 8.1 Backup

- Backup metadata DB + private blobs + manifests + deletion ledger nhất quán; không chỉ pg_dump mà quên file CV.
- Backup encrypted; key tách khỏi bản backup, quyền phục hồi được kiểm soát. Rolling7day là đề xuất kỹ thuật phải phù hợp retention trường. Tạo snapshot trước migration và tối thiểu hàng ngày trong thời gian pilot có dữ liệu mới.
- Restore drill vào database/path khác, không ghi đè runtime. Sau restore áp deletion ledger, kiểm tra referential integrity/source hashes và quyền, rồi chạy synthetic smoke. Không tự bật outbound DeepSeek ở restored environment.
- Không khẳng định zero data loss: ghi RPO/RTO đo được trong drill; target ban đầu RPO≤24h và restore≤2h trong giờ có người, chỉ sau đo mới cam kết với HR.

### 8.2 Release

1. Pin commit/dependency/prompt manifest/schema và evidence reports.
2. Unit/integration/E2E + security regression pass; synthetic provider smoke nếu adapter/model thay đổi.
3. Migration dry-run trên restored copy, kiểm tra compatibility của rollback.
4. Tạm ngừng nhận job mới, cho in-flight settle hoặc gắn outcome_unknown đúng cách; backup.
5. Deploy code/config/migrations; readiness + synthetic end-to-end; mở queue.
6. Theo dõi batch nhỏ trước toàn bộ hồ sơ. Không dùng score của phiên bản mới lẫn cũ để sort mà không ghi rõ.
7. Rollback code/prompt/config khi có lỗi; database rollback chỉ theo migration plan đã test, không downgrade phá dữ liệu. Có thể forward-fix schema và rollback app tương thích.

Không hứa tái chạy sẽ trả đúng byte kết quả cũ. Audit đảm bảo biết hệ thống đã dùng nguồn/cấu hình nào và kết quả đã lưu, không đảm bảo model remote deterministic.

## 9. Điều kiện chuyển từ local sang deploy

Cloud chưa nằm trong tác vụ hiện tại. Chuẩn bị portable Docker CPU, health checks và config injection từ đầu; chỉ deploy khi user giao việc và đã chọn môi trường.

Checklist chuyển môi trường: TLS, private DB/network, encrypted persistent storage, secrets manager hoặc secret file quyền hẹp, backup/restore tested, admin account riêng, retention configured, không sample password, no debug endpoints, upload limits ở proxy, outbound allowlist DeepSeek, local vs cloud benchmarks, privacy policy/processing location phù hợp cấu hình trường. Không expose laptop qua public tunnel chỉ để bỏ qua các bước này.

Một VM/container host đơn giản đủ cho pilot nhỏ nếu load-test pass. Managed Postgres/object store là bước sau khi cần uptime và backup tốt hơn; không chọn cloud provider hoặc thuê máy trong bản lập kế hoạch này.
