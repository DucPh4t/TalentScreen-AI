# Evaluation data contract

Use `scripts/eval_harness.py` only with two separately recorded files: AI predictions from a real assessment run and labels entered by an HR reviewer **before** seeing those predictions. Keep files under `private_storage/eval/` (gitignored). `sample_id` is a pseudonymous join key, never a name, email or CV text. One row per case; JSONL or a JSON array is accepted. Duplicate IDs and unknown rubric IDs are rejected.

Example AI prediction (`ai_predictions.jsonl`):

```json
{"sample_id":"sample-001","run_id":"assessment-run-uuid","prompt_version":"assessment-v1","model":"deepseek-chat","criterion_scores":{"python_backend":3,"api_design":2,"sql_data":2,"testing_debugging":null,"security_privacy":1,"delivery_ops":2},"recommendation":"needs_clarification","input_tokens":1900,"output_tokens":450,"observed_cost_usd":0.0008}
```

Example independent label (`hr_blind_labels.jsonl`):

```json
{"sample_id":"sample-001","split":"real_shadow","language":"mixed","label_origin":"hr_blind","reviewer_id":"hr-pseudonym-01","criterion_scores":{"python_backend":2,"api_design":2,"sql_data":3,"testing_debugging":null,"security_privacy":1,"delivery_ops":2},"recommendation":"needs_clarification"}
```

All six rubric IDs are required; a `null` anchor means insufficient comparable evidence, never zero. Recommendation values are `consider_next_round`, `needs_clarification`, `review_required`. Languages are `vi`, `en`, `mixed`. Splits are `smoke`, `dev`, `holdout`, `real_shadow`. `design_expected` labels may be used for engineering diagnostics but do not qualify as independent HR ratings. Capture `run_id`, prompt version and model from the persisted assessment, not from memory.

The initial 12 synthetic scenarios in `fixtures/` are **unlabeled smoke/dev cases**. They cannot produce G5 MAE or kappa. The 30-family holdout, HR blind labels and real shadow batch still need to be collected. Freeze the holdout and verify its source/consent before scoring. The CLI reports missing predictions and undefined metrics explicitly and leaves the gate pending human sign-off.

For prompt A/B testing, record both variants on **the same** frozen sample IDs and use the same labels:

```bash
.venv/bin/python scripts/prompt_compare.py \
  --labels private_storage/eval/hr_blind_labels.jsonl --split dev \
  --variant assessment-v1=private_storage/eval/predictions-v1.jsonl \
  --variant assessment-v2=private_storage/eval/predictions-v2.jsonl \
  --output private_storage/eval/prompt-comparison.json
```

The comparator rejects missing cases and prompt-version mismatches. `scripts/prompt_regression.py` records prompt hashes and performs static safety checks; it does not call DeepSeek or prove output quality. Keep the prior prompt text/hash and recorded outputs to enable a real rollback comparison.
