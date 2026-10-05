# TalentScreen AI — Thiết kế kết hợp DeepSeek + Jev

Ngày cập nhật: 2026-10-05

## Mục tiêu sản phẩm

HR tạo nhiều đợt tuyển dụng với JD khác nhau, nhận CV, xem mức độ phù hợp theo rubric của từng JD, truy ngược từng nhận định về đúng đoạn CV, sinh câu hỏi phỏng vấn và tự quyết định. Không dùng điểm AI để tự loại/chọn người. Không dùng thuộc tính nhạy cảm hay proxy bị cấm. Mỗi phiên bản JD, rubric, prompt, provider/model và quyết định HR phải truy vết được.

## Phân vai mô hình

- **Parser + code xác định:** đọc PDF/DOCX, chuẩn hóa văn bản, tách đoạn, khử định danh, lưu hash/source spans, xác thực schema/trích dẫn, tính tổng điểm và kiểm tra quyền, ngân sách, trạng thái hồ sơ.
- **DeepSeek:** tác vụ sinh/hiểu ngôn ngữ cần diễn giải: trích xuất yêu cầu JD thành bản rubric nháp; ghép bằng chứng CV vào từng tiêu chí; viết giải thích tham khảo; tạo câu hỏi làm rõ/phỏng vấn. Chỉ nhận bản CV đã che được HR duyệt. Không giao quyền quyết định cuối.
- **Jev (TypeSafe):** tác vụ phán đoán hẹp, đầu ra có kiểu: chấm một chiều kỹ năng theo các anchor đã định nghĩa, mức độ bằng chứng hỗ trợ, hoặc mức cần HR xem lại. Chỉ nhận trạng thái JSON tối thiểu gồm tiêu chí và các đoạn bằng chứng đã chọn, không nhận tên/ID/ảnh/thông tin liên hệ/CV thô. Chạy shadow trước; không thay điểm DeepSeek hoặc recommendation cho đến khi được đánh giá và phê duyệt riêng.
- **Orchestrator:** gọi theo chính sách, không cho hai model tự sửa output của nhau. Validator và code là nơi quyết định tính hợp lệ; bất đồng/thiếu bằng chứng/độ chắc chắn thấp thì gắn cờ HR.

Jev trả score/probabilities/confidence cho thang mức mô tả; confidence không phải xác suất đúng đã được hiệu chuẩn trên dữ liệu tuyển dụng của trường. Model version phải được ghim, không dùng alias tự trôi trong đánh giá chính thức. Tham khảo: [TypeSafe API quick start](https://docs.typesafe.ai/introduction/quickstart), [Score primitive](https://docs.typesafe.ai/primitives/score), [model versions](https://jev-ai.org/docs/models/).

## Các phương án kiến trúc và đánh đổi

| Phương án | Cách làm | Ưu điểm | Đánh đổi / khi dùng |
|---|---|---|---|
| DeepSeek + rule engine | DeepSeek trích bằng chứng/giải thích; backend kiểm chứng span và tính điểm theo rubric | Ít vendor, đơn giản, giữ nguyên một nguồn đánh giá; phù hợp baseline an toàn | Không có cross-check độc lập; JSON hợp lệ không đồng nghĩa đánh giá đúng |
| DeepSeek + Jev shadow (**đề xuất trước**) | DeepSeek tạo evidence; Jev chấm cùng các evidence theo anchor riêng; bất đồng chỉ tạo cờ review | Đo được Jev có giúp không mà không làm thay đổi score/HR outcome; kết quả tách model, có thể so offline | Thêm nhà cung cấp/chi phí/egress; cần schema lưu thứ hai, audit, version pin và approval riêng |
| DeepSeek + Jev score fusion | Chỉ sau benchmark, hợp nhất score đã hiệu chuẩn với rule quyết định xác định | Có thể giảm một số lỗi đánh giá theo tiêu chí | Rủi ro đồng thuận giả, phụ thuộc calibration/dataset; không nên dùng trong MVP trước khi chứng minh trên dữ liệu trường |
| Jev làm scorer duy nhất | Jev nhận rubric + evidence và chấm | Đầu ra cấu trúc, nhanh, không cần model viết score JSON | Không tạo được JD-to-rubric, narrative rationale hay câu hỏi; chưa chứng minh chất lượng CV Việt/ngôn ngữ hỗn hợp; không phù hợp standalone |

Với mọi phương án, không giao model quyền chốt ADVANCE/NOT_ADVANCE. Jev trả score spectrum có thể là số thập phân; chỉ được map về 0..4 theo quy tắc đã đăng ký trước và không được biến confidence thành xác suất chính xác.

## Retrieval và số lượng agent

- **Full-text/keyword baseline:** dễ truy nguồn, rẻ, debug được; dùng trước cho CV thường ngắn và giữ source spans nguyên văn.
- **Hybrid lexical + multilingual embedding + reranker:** hữu ích nếu CV dài/song ngữ hoặc nhiều tài liệu; tăng chi phí/độ phức tạp và có thể bỏ sót đoạn. Nếu bật, retrieval chỉ chọn đoạn; nó không tự chấm. Lưu span ID/relevance trace và luôn cho HR xem nguồn.
- **Không cần agent swarm:** dùng một orchestrator tất định, DeepSeek cho tác vụ sinh/hiểu, Jev cho score atoms, backend cho policy/score/cost. Nhiều agent tự gọi tool làm khó dự toán và truy vết.

## Fairness và HITL cụ thể

- Giữ identity map riêng; LLM/Jev chỉ nhận pseudonymous application id nội bộ hoặc không nhận ID, cùng tiêu chí đã duyệt và text đã che.
- Xóa/không chuyển giới tính, tuổi/ngày sinh, ảnh, quê quán/địa chỉ, tên trường, tình trạng gia đình; loại các tiêu chí như school prestige, khoảng nghỉ việc hoặc “culture fit” khỏi rubric mặc định. Nếu JD nêu điều kiện pháp lý bắt buộc, cần HR/pháp chế duyệt và lý do nghiệp vụ rõ trước khi cho phép.
- Counterfactual fixtures thay tên/đại từ/tên trường nhưng giữ nguyên kinh nghiệm; điểm và evidence phải bất biến. Phân tích fairness theo nhóm chỉ dùng dữ liệu riêng được phép, cỡ mẫu đủ và không gửi nhóm nhạy cảm tới scorer.
- UI hiển thị JD/rubric version, trạng thái AI vs HR, confidence như tín hiệu không chắc chắn, từng quote/span, nội dung thiếu/mâu thuẫn, nguồn model và nút override bắt buộc lý do. HR có thể quyết định khác AI; không ép chọn recommendation.
- Không để model phản biện/“thuyết phục” HR. Nếu DeepSeek và Jev lệch hơn mức nội bộ định trước hoặc Jev confidence thấp, ẩn tổng kết tự động và yêu cầu HR đánh giá evidence độc lập.

## Rủi ro chính và tiêu chí go/no-go

- **Hallucination / quote hợp lệ nhưng suy luận sai:** exact-span validator chặn quote bịa; HR đánh giá entailment, không chỉ substring.
- **Prompt injection trong CV/JD:** coi hồ sơ là dữ liệu không tin cậy, không thực thi hướng dẫn/tool; model không được quyền gọi công cụ hay truy cập CV khác.
- **Drift / version thay đổi:** ghim Jev và DeepSeek model id, log phiên bản trả về, prompt/rubric hash; nâng phiên bản phải chạy bộ regression/holdout mới.
- **Bất đồng hai model:** không coi majority-vote là ground truth; chuyển HR và dùng nhãn chuyên gia phân xử.
- **Egress / xóa không hoàn chỉnh:** hạn chế evidence truyền ra ngoài, kiểm tra processor/transfer, lưu danh mục artifacts và drill xóa + backup ledger.
- **Mục tiêu kỹ thuật ban đầu (ngưỡng do HR/IT khóa trước khi mở holdout):** 100% điểm khác null có span tồn tại và quote khớp; 0 câu khẳng định nhạy cảm; agreement AI-human báo cáo riêng từng tiêu chí với khoảng tin cậy; counterfactual score invariant; p95 xử lý theo SLO đã chọn; cost/ứng viên nằm dưới cap; khi provider lỗi thì fail closed sang hàng đợi HR.

## Luồng đích

1. HR tạo requisition và nhập JD.
2. DeepSeek đề xuất rubric nháp: tiêu chí, trọng số tổng 100, định nghĩa năng lực, anchor 0..4, must-have và bằng chứng JD hỗ trợ. Bộ lọc quy tắc chặn thuộc tính nhạy cảm/proxy.
3. HR + hiring lead duyệt rubric bất biến cho một phiên bản JD. Tái sử dụng khung đo lường và anchor chung; tiêu chí/weight cụ thể theo vị trí. Không dùng rubric Backend để chấm Frontend/Data/DevOps.
4. CV được quét an toàn; nếu cần OCR thì chạy pipeline được cấu hình. Candidate identity tách khỏi văn bản chấm. Owner kiểm tra và duyệt bản đã che.
5. DeepSeek trả criterion observations có span IDs; server bắt buộc kiểm tra span tồn tại và quote bằng nguyên văn. “Không tìm thấy trong CV” là insufficient evidence/null, không phải 0.
6. Jev shadow chỉ khi được bật có chủ đích, provider đã được tổ chức duyệt, và cấu hình giá/phiên bản hợp lệ. Jev nhận đúng đoạn bằng chứng cho tiêu chí; không truyền các đoạn không liên quan. Output giữ riêng như quan sát thứ hai, không âm thầm ghi đè DeepSeek.
7. Code chuẩn hóa điểm theo anchor, tính score/coverage và trạng thái so sánh; nếu một tiêu chí thiếu hoặc mâu thuẫn thì không đưa vào ranking so sánh. Cả hai model không thể phát quyết định ADVANCE/NOT_ADVANCE.
8. HR xem CV đã che, source spans, DeepSeek rationale, kết quả đối chiếu Jev nếu có, tạo override có lý do, ghi quyết định HR và chọn câu hỏi phỏng vấn.
9. Lưu immutable input snapshot/hash, prompt/model versions, token/cost, lỗi/retry, kết quả mỗi model và thao tác HR theo retention policy; hỗ trợ xóa dữ liệu và kiểm tra lại.

## Rubric dùng cho nhiều JD

Tách **khung chung** khỏi **tiêu chí kỹ năng**:

- Khung chung: anchor 0..4, quy tắc bằng chứng, null/mâu thuẫn, fairness, weighting, coverage, quyết định con người, schema/version.
- Tiêu chí: cấu hình theo từng JD/job family, có mã ổn định do hệ thống tạo (không enum Python cố định). Mỗi tiêu chí phải liên kết yêu cầu cụ thể trong JD. Những năng lực chung chỉ xuất hiện nếu JD yêu cầu.
- Tạo rubric bằng AI luôn ở trạng thái draft; approval của HR/hiring lead là điều kiện trước ingestion assessment. Sửa JD/rubric tạo version mới và đánh giá cũ giữ nguyên snapshot.

## Kiểm soát vận hành và chi phí

- Mặc định `LLM_PROVIDER=mock`, `JEV_MODE=off`.
- Tắt egress Jev nếu chưa có JEV API key, model pin, price card được xác nhận và data-processing approval. Không lấy giá marketing/ước tính từ model làm giá production.
- Một lần assessment có giới hạn số tiêu chí/calls/tokens, timeout, retry chỉ khi lỗi retryable, idempotency và cap ngân sách chung. Provider timeout không rõ kết quả phải ghi `outcome_unknown`, không retry mù.
- Metric bắt buộc: token/cost trên hồ sơ và theo provider; p50/p95; lỗi parse/extraction; schema-valid rate; citation exact-match; evidence coverage; HR override rate; agreement theo tiêu chí; phân tích bất đồng và fairness.

## Gate trước dùng CV ứng viên

1. Tổ chức duyệt căn cứ xử lý/thông báo, nhà cung cấp, hợp đồng/data flow và mọi yêu cầu chuyển dữ liệu. DeepSeek được duyệt không tự động bao gồm Jev.
2. Dữ liệu giữ trong phạm vi, quyền xem/tải/xóa, backup restore + deletion replay, audit, secret management, TLS/ingress/rate limit đều được diễn tập.
3. HR và chuyên gia IT thật gán nhãn độc lập trên tập holdout khóa trước khi chỉnh prompt/rubric. Agent mô phỏng không phải nhãn độc lập.
4. Đạt ngưỡng nội bộ đã định trước về citation accuracy, agreement, coverage, cost/latency và counterfactual invariance; ghi khoảng tin cậy và giới hạn cỡ mẫu.
5. Bắt đầu ở chế độ shadow/assisted có người rà soát toàn bộ; không auto-reject, không tự gửi email ứng viên. Có nút dừng và quy trình quay về đánh giá thủ công.

## Đánh giá Jev trước khi đưa vào quyết định hỗ trợ

- Freeze một phiên bản Jev và cùng tập CV đã được phép, cùng bản JD/rubric, so sánh DeepSeek-only với DeepSeek+Jev và nhãn HR/IT độc lập.
- Đo weighted agreement theo từng tiêu chí, calibration, độ chính xác theo ngôn ngữ CV (Việt/Anh/song ngữ), tần suất Jev bất đồng, số ca Jev làm thay đổi score, latency và cost.
- Làm counterfactual test: đổi/xóa tên, giới tính, tuổi, địa chỉ, tên trường mà không đổi nội dung năng lực; score/bằng chứng không được đổi.
- Không dùng confidence làm ngưỡng tiếp tục cho tuyển dụng khi chưa calibration. Trong shadow, mọi bất đồng đều chuyển HR; không điều chỉnh score sau khi biết nhãn holdout.

## Hiện trạng repo và backlog triển khai

Repo hiện có ingestion/sanitization approval, exact-span validation, HR decisions, audit/cost ledger và UI demo PDF; bài đánh giá hiện **mock** và schema/rubric bị khóa sáu criterion Backend Python. Docker/cloud và provider live chưa nghiệm thu. Vì vậy “sẵn sàng deploy” cần chia:

- **P0 sản phẩm:** dynamic rubric xuyên schema/assessment/HR revision/interview/comparison; JD-to-rubric draft + approval; evidence retrieval/validator giữ bất biến.
- **P0 mô hình:** Jev HTTP adapter có schema/error mapping, ghim version, chạy shadow tùy chọn, lưu riêng outputs theo run và API/UI compare; cost theo rate card cấu hình đã duyệt.
- **P0 dữ liệu:** chính sách xử lý cho từng provider; Jev tắt mặc định, chỉ gửi sanitized/minimized evidence sau khi được duyệt.
- **P0 chất lượng:** prompt registry/version + regression set; holdout thật do HR/IT chấm độc lập; DeepSeek-vs-Jev-vs-HR report; fairness counterfactual.
- **P1 deploy:** Docker/cloud/TLS secrets, backup/restore, deletion ledger độc lập, health/worker heartbeat/alerts, load/failure drills, runbook, rollback.

Không tuyên bố production-ready chỉ vì build/tests qua. Việc bật Jev hoặc xử lý CV thật cần gate dữ liệu, benchmark và nghiệm thu nghiệp vụ riêng.

## Trạng thái triển khai trong repo (2026-10-05)

- Đã thêm adapter HTTPX cho TypeSafe System One, contract cho Score/Choice/Noul, kiểm tra output và giới hạn dữ liệu request; chưa gọi API thật.
- `JEV_MODE=off` là mặc định. Muốn bật shadow, cấu hình còn yêu cầu API key, model pin, giá input đã xác minh, ngày xác minh và cờ phê duyệt xử lý dữ liệu riêng cho Jev.
- Assessment có thể gửi sang Jev đúng các đoạn trích đã được DeepSeek validator xác minh cho tiêu chí có điểm; không gửi các tiêu chí thiếu bằng chứng, không gửi CV đầy đủ hay identity ID. Jev được ghi ở `secondary_model_output`, có cost ledger và audit event; lỗi Jev không đổi điểm chính/recommendation.
- Trang hồ sơ có bảng so sánh Jev/DeepSeek và chú thích confidence, vẫn giữ HR là người kiểm tra và quyết định.
- Migration thêm JSONB đã được tạo và đã được áp dụng thành công lên PostgreSQL disposable trong test; database ứng dụng chưa bị thay đổi.
- Chưa gọi API thật, chưa migrate vào database ứng dụng, chưa chạy bộ CV holdout hoặc diễn tập e2e; không có CV ứng viên nào được gửi tới nhà cung cấp trong lần triển khai này.
- Đã gỡ hardcode sáu criterion ở rubric validation, assessment schema/prompt/mock, HR revision/attestation và interview bank/follow-up. Rubric hiện cho phép 2–12 tiêu chí dạng slug, tổng weight 100, anchors 0..4; assessment phải trả đúng tập ID từ rubric đã duyệt. Custom interview bank được tạo dưới dạng draft câu hỏi chung và cần Owner xem/duyệt.
- Ma trận so sánh đã có endpoint Owner-only và UI theo rubric hiện hành; không cần xây lại tính năng này.
- HR hiện có form tạo/sửa rubric động ngay trên trang requisition, với tối đa 12 criterion, weight, core floor, 5 anchors và trích dẫn nguồn JD nguyên văn; form không tự sinh tiêu chí bằng AI. Chưa có thao tác AI đề xuất rubric từ JD.
- Regression suite mới bao gồm rubric động, exact criterion set/scoring, Jev request/response/gates/secret handling, và kiểm tra schema migration; toàn bộ 175 backend tests đã chạy thành công trên PostgreSQL disposable. Chưa có provider live check, holdout HR/IT hoặc nghiệm thu cloud/production. Live interview scorecard, dossier export và email template là P1; chúng không thay thế các gate bắt buộc về chất lượng, bảo mật và pháp lý.
- Kiểm chứng mã: Python `compileall`, Next.js production build, `alembic heads` trả `c2f1a90d34b7 (head)`, Alembic upgrade toàn bộ chain trên PostgreSQL disposable và `git diff --check` đều thành công. Chưa migrate database ứng dụng, gọi DeepSeek/Jev hoặc diễn tập trên dữ liệu ứng viên.
- Vì vậy repository đã có nền tảng release candidate tốt hơn và hỗ trợ rubric nhiều vị trí, nhưng chưa thể xác nhận sẵn sàng nhận hồ sơ tuyển dụng thật cho đến khi provider/budget/failure drills, holdout HR/IT và nghiệm thu của phụ trách dữ liệu được hoàn tất.
