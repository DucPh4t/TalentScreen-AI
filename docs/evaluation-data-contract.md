# Evaluation data contract

Use `scripts/eval_harness.py` with separately recorded AI predictions and reviewer labels. For blind evaluation, HR must enter labels **before** seeing AI predictions. Keep all real-CV files under `private_storage/eval/` (gitignored). `sample_id` is a pseudonymous join key, never a name, email or CV text. One row per case; JSONL or a JSON array is accepted. `rubric_id` identifies the immutable, approved role-specific rubric used for that case. Criterion IDs are dynamic slugs scoped to that rubric; the evaluator rejects a prediction whose rubric or criterion set differs from the expected label. Use `role_family` for role-level disaggregation. `design_expected` labels are assistant-authored test expectations, not independent HR ground truth.

Example AI prediction (`ai_predictions.jsonl`):

```json
{"sample_id":"sample-001","rubric_id":"backend_node_intern_v1","role_family":"backend_node","run_id":"assessment-run-uuid","prompt_version":"assessment-v1.3.0","model":"deepseek-chat","criterion_scores":{"backend_implementation":2,"api_design":2,"data_management":null,"testing_delivery":null},"recommendation":"needs_clarification","input_tokens":1900,"output_tokens":450,"observed_cost_usd":0.0008}
```

Example independent label (`hr_blind_labels.jsonl`):

```json
{"sample_id":"sample-001","rubric_id":"backend_node_intern_v1","role_family":"backend_node","split":"real_shadow","language":"mixed","label_origin":"hr_blind","reviewer_id":"hr-pseudonym-01","criterion_scores":{"backend_implementation":2,"api_design":2,"data_management":null,"testing_delivery":null},"recommendation":"needs_clarification"}
```

Each row must carry its rubric ID and 2–12 dynamic criterion IDs. The prediction and label must use the same rubric and exact criterion set; `null` means insufficient comparable evidence, never zero. The harness reports per-rubric errors plus role-family and language breakdowns. Recommendation values are `consider_next_round`, `needs_clarification`, `review_required`. Languages are `vi`, `en`, `mixed`. Splits are `smoke`, `dev`, `holdout`, `real_shadow`. `design_expected` labels may be used for engineering diagnostics but do not qualify as independent HR ratings. Capture `run_id`, prompt version and model from the persisted assessment, not from memory.

The initial 12 synthetic scenarios in `fixtures/` are **unlabeled smoke/dev cases**. `fixtures/holdout_rehearsal/` contains 30 distinct, hash-frozen, **unlabeled synthetic** families (10 per language group) for workflow rehearsal. Neither set can produce a G5 MAE or kappa until independent labels and recorded predictions exist, and neither substitutes for the actual real-shadow batch. Freeze any operational holdout and verify its source/consent before scoring. The CLI reports missing predictions and undefined metrics explicitly and leaves the gate pending human sign-off.

For prompt A/B testing, record both variants on **the same** frozen sample IDs and use the same labels:

```bash
.venv/bin/python scripts/prompt_compare.py \
  --labels private_storage/eval/hr_blind_labels.jsonl --split dev \
  --variant assessment-v1=private_storage/eval/predictions-v1.jsonl \
  --variant assessment-v2=private_storage/eval/predictions-v2.jsonl \
  --output private_storage/eval/prompt-comparison.json
```

The comparator rejects missing cases and prompt-version mismatches. `scripts/prompt_regression.py` records prompt hashes and performs static safety checks; it does not call DeepSeek or prove output quality. Keep the prior prompt text/hash and recorded outputs to enable a real rollback comparison.
