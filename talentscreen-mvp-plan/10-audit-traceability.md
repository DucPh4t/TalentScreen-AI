# 10 — Tự review, truy vết yêu cầu và giới hạn còn lại

## 1. Kết luận review thiết kế

Brainstorm ban đầu đủ định hướng nhưng không đủ giao một AI triển khai nhất quán. Bộ đặc tả này chốt nghiệp vụ, cấu trúc dữ liệu, quyền, đầu ra AI, luồng lỗi, kiểm thử và thứ tự làm. Các quyết định mới được chọn để giữ dự án trong phạm vi một người, một trường và một họ vị trí IT.

Đây là **review tài liệu và hợp đồng mẫu**. Không phải security audit của phần mềm đã chạy, không phải đánh giá accuracy/fairness của một model trên ứng viên thật và không phải xác nhận đạt SLO.

## 2. Các vấn đề đã phát hiện và cách xử lý

| ID | Vấn đề trong brainstorm | Quyết định sửa | Nơi đặc tả |
|---|---|---|---|
| REV-01 | Giả định 2–3 người chưa xác nhận | Một người, local MacAirM4, 4 tuần nội bộ/6–8 tuần pilot có điều kiện | 00,07,09 |
| REV-02 | Chưa chọn loại vị trí | Một JD Backend Python cho hệ thống trường; HR/IT duyệt seed | 01, examples/JD+rubric |
| REV-03 | Độ dài/độ chi tiết bằng chứng bị trộn với năng lực | Skills listing không đủ; anchor theo tác vụ/scope; unknown null | 00,04,rubric |
| REV-04 | Điểm quan sát có thể làm hồ sơ thiếu thông tin đứng đầu | Coverage riêng; comparablescore chỉ fullcoverage; default không rank; không tự reject | 00,01,04 |
| REV-05 | Hợp đồng criterion/evidence chưa chặt | Exact criterion set; strict schema; backend source IDs; quote nguyên span; foreign source reject | 03,04,contracts |
| REV-06 | JSON mode bị hiểu như strict schema/semantic correctness | Pydantic + nghiệp vụ + source validation; empty/truncated branches; semantic HR eval | 04,06,07 |
| REV-07 | DeepSeek alias và giá có thể đổi | Giữ cấu hình user, synthetic probe, verified rate card; no silent fallback | 00,04,07 |
| REV-08 | Multi-agent scope quá dễ phình | Ba task bounded; code orchestration; không autonomous tools/microservices | 02,04 |
| REV-09 | RAG có thể bỏ sót so với fulltext | Fulltext baseline, hybrid feature flag, benchmark evidence recall và fallback có giới hạn | 04,06 |
| REV-10 | CV song ngữ bị gom một nhãn/ngôn ngữ | Per-section/chunk language, nguồn gốc giữ nguyên, shared rubric, bilingual dedup | 04,06 |
| REV-11 | Public dataset bị nhầm thành HR ground truth | Rà origin/license, synthetic source bootstrap; source heuristic tách khỏi HR labels | 08,06 |
| REV-12 | Không có model dữ liệu ứng viên nhiều vị trí | Candidate/Application/DocumentVersion/AssessmentRun tách rõ | 03 |
| REV-13 | Xử lý retry tưởng là exactly-once | PostgreSQL lease/fence, version snapshots, bounded retry và provider outcome unknown | 02,03,07 |
| REV-14 | Xóa rồi worker có thể tái tạo dữ liệu | Tombstone + generation checks + idempotent purge + restore ledger | 03,05,07 |
| REV-15 | Audit lưu quá nhiều nội dung làm quyền xóa khó thực thi | Metadata append-only, payload private/purgable; backup/vendor status riêng | 05 |
| REV-16 | HR approve chỉ tồn tại trên UI | Backend owner permission, decision snapshots, reasons, revision history | 01,03,05 |
| REV-17 | OCR fail bị coi như thiếu năng lực | Technical state tách criterion state; manual/request-info path rõ | 01–04 |
| REV-18 | SLO không có định nghĩa đồng hồ/tải | Tách upload→sanitized, assessment admission→result và thời gian người; P1/P2 workloads | 06,07 |
| REV-19 | GPU M4 bị hiểu như GPU Linux container | Native Python MPS; profile Docker CPU để deploy | 02,07 |
| REV-20 | Onboarding và bản sandbox chưa thành task | Walkthrough, tooltip, fault cases, UAT; deployment/data tách | 01,09 |
| REV-21 | Nhiều prompt variants có thể tiêu tiền mà không giới hạn | Smoke10/dev60/holdout30, paid eval opt-in, cost estimate/reservation, rollback | 04,06,07 |
| REV-22 | Threshold70 có vẻ như chuẩn đã validated | Seed threshold draft HR hiệu chuẩn, không gọi review_required là ứng viên kém | 00,01,06,09 |

## 3. Ma trận truy vết yêu cầu người dùng

| Requirement | Thiết kế | Task chính | Bằng chứng nghiệm thu cần có |
|---|---|---|---|
| HR quyết định cuối | Owner-only final decision; AI không tool quyết định | B02,B13,B22 | Direct API bypass tests + UAT |
| Không dùng thuộc tính bị cấm | Sanitizer + HR source approval + bounded payload + output checks | B08,B22 | Captured egress fixtures, counterfactual tests |
| Chấm năng lực và giải thích | Six anchored criteria + exact evidence + deterministic math | B04,B10,B11,B12 | Schema/rules tests + semantic review |
| Grounded CV/JD thật | Source versions, supplied span registry, JD source refs | B06,B08,B10 | Foreign/stale/fabricated source rejection |
| Audit log | Events with actor/snapshot and immutable revisions | B13,B17 | Truy vết một decision sau override/reassessment |
| Phân quyền và bảo mật | Sessions, scoped membership, raw grant, private storage | B02,B05,B22 | SEC-01..15 |
| Xóa theo yêu cầu | Tombstone/cancel/purge, dependency inventory, backups | B17,B24 | Delete-race + restore drill |
| AI–HR similarity | Blinded labels + MAE/kappa/status comparisons, HR–HR subset | B19,B25 | Eval report có denominators và label origin |
| Kiểm soát chi phí | Model capability, rate card, budget reservation, call cap | B09,B23 | Simulated budget race + actual usage report sau chạy |
| Prompt lifecycle | Git/schema/release bundle, tests, rollback | B10,B14,B20 | Prompt comparison report + rollback drill |
| SLO/error budget | Pipeline metrics + workload profiles + incident actions | B23 | Load report và bảng số job vi phạm |
| CV Việt/Anh/mixed | OCR vie+eng, E5 benchmark, original quotes | B08,B15,B16,B19 | Per-language recall/score/error report |
| Onboarding HR | Sandbox + walkthrough + tooltip + planted errors | B21,B25 | HR thực hiện task training không cần làm hộ |
| MacAirM4 local trước | Native CPU/MPS + DB Docker + portable CPU compose | B00,B24 | Doctor + native/CPU smoke |
| Domain IT, JD tự soạn | Backend Python seed có source requirements và anchors | B04,B18 | HR/IT phê chuẩn version thực tế |
| Tìm luồng dataset | Registry/inspect/import/synthetic fixtures + origin labels | B18,B19 | DATA-01..10 + attribution |

## 4. Các quyết định còn cần kiểm chứng, không cần hỏi lại để viết plan

| Điểm chưa có kết quả | Cách giải quyết khi implement | Có chặn việc nào? |
|---|---|---|
| RAM và throughput máy thực | Doctor + embedding/parser benchmark | Không chặn mock/base UI; chặn tuyên bố throughput |
| Alias `deepseek-chat` thực tế | Synthetic capability probe khi cấu hình key | Chặn real provider activation nếu chưa chạy được; không chặn mock |
| Giá bill đúng model/tài khoản | Rate card verified + usage reconciliation | Chặn paid batch khi chưa có cap/ước lượng đáng tin |
| Retention cụ thể của trường/provider | Ghi cấu hình chính sách áp dụng, trách nhiệm và thời hạn | Chặn vận hành dữ liệu thật nếu chưa biết cách lưu/xóa; quyền dùng DeepSeek đã được xác nhận, không hỏi lại |
| HR/IT lịch tham gia | Mời sớm theo H1–H5; chấm mẫu thực tế | Chặn rubric activation/live-validity claims nếu chưa có người duyệt/nhãn |
| 70 điểm và core floor2 phù hợp không | Calibration dev set, HR duyệt trước freeze | Không tự tối ưu theo holdout hoặc giữ ngưỡng vì tiện demo |
| Dataset ngoài tại revision cụ thể | Inspect/pin/license snapshot/PII scan trước import | Không chặn fixtures tự soạn |
| Hiệu quả fulltext vs hybrid | Cùng held-out spans/inputs, cost+latency+recall comparison | Hybrid có thể để off; không ép dùng RAG để đủ tên stack |

## 5. Những giới hạn phải xuất hiện trong sản phẩm/báo cáo

- CV là lời khai, có nguồn không đồng nghĩa kinh nghiệm đã được xác minh ngoài đời.
- Hệ thống hỗ trợ đánh giá mức đáp ứng thể hiện trong hồ sơ; không đo năng lực tuyệt đối, tiềm năng, tính cách hoặc xác suất thành công.
- Không có bằng chứng không chứng minh thiếu năng lực; lượng thông tin không đều có thể làm coverage thấp. HR có đường hỏi thêm và quyết định thủ công.
- Mọi metric trên synthetic phải gắn nhãn; thử phản thực không đủ để chứng minh demographic fairness của tuyển dụng thật.
- Human-in-the-loop cũng có automation bias; cần independent labels và giao diện ưu tiên nguồn, không chỉ thêm nút Approve.
- Local laptop không phải dịch vụ uptime24/7. SLO áp theo workload/giờ vận hành đã ghi, không dùng con số chưa đo để quảng bá.
- Xóa active data, hết hạn backup và vendor retention là các trạng thái khác nhau; UI không hứa instant deletion ở mọi nơi.
- Tái hiện cấu hình và kết quả đã lưu là khả thi; tái chạy remote LLM cho cùng output tuyệt đối không được bảo đảm.

## 6. Quy tắc đo bất biến fairness đúng cách

Counterfactual fixtures đổi tên/trường có thể được server gán application/source IDs khác nhau. So sánh canonicalized scoring content sau khi loại metadata opaque không mang ý nghĩa; không yêu cầu byte equality của random ID. Không loại nội dung thực để làm test pass. Payload sau che phải không còn thông tin bị cấm; model output được đối chiếu theo criterion và source mapping đúng family.

Test translation/layout là robustness suite riêng; tính điểm chênh lệch cần đối chiếu với noise của repeat cùng payload. Không dùng tên/ảnh để suy đoán nhân khẩu của ứng viên thật chỉ để có dashboard đẹp.

## 7. Trạng thái xác minh bộ plan

Các kiểm tra cuối cần ghi trong README sau khi thực sự chạy: JSON parse; JSON Schema syntax và valid/invalid examples; đủ6criteria/weights100/anchors0..4/JD references; tồn tại các local link; task dependency không vòng; cấu hình nhất quán; không file CV thật/secret; archive content inventory.

Không chuyển bất kỳ mục "test của ứng dụng" ở05/06/09 thành PASS trong quá trình kiểm tra tài liệu. Chỉ các kiểm tra artifact đặc tả đã chạy mới được ghi đã đạt.

## Bổ sung sau đối chiếu API–UX

Đã tách ba căn cứ quyết định ở03: review assessment, manual document review và technical information request. Nhờ vậy OCR/API lỗi không buộc HR tạo sanitized source hoặc điểm giả; manual vẫn có owner/grant/source/error attestation và audit. Đã đồng bộ quyền upload reviewer, owner cấp raw grant, giới hạn form, checksum scope, job embed_sanitized, tên config RAG và span registry bất biến. Tests T-E2E-011..013 và B13 phải được implement; việc tài liệu có test case chưa có nghĩa test phần mềm đã pass.


Review cuối cũng đã sửa quyền đọc payload sau revoke, thứ tự idempotency trước kiểm version của request mới, scope ngân sách, trạng thái xóa từng kho, lưu/sửa bank và followups phỏng vấn, cùng phase guard shadow ở API. Gán nhãn chọn CLI JSON có quyền để giảm phạm vi UI; report shadow chỉ mở sau khi đóng băng nhãn/quyết định độc lập. Kết quả kiểm chứng artifact thực tế nằm ở [artifact-validation.json](artifact-validation.json); test ứng dụng vẫn chưa chạy vì đây là bộ kế hoạch.
