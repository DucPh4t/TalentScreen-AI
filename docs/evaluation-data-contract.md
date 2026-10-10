# Evaluation data contract

The current evaluation contract is [`docs/evaluation/independent-human-evaluation-design.md`](evaluation/independent-human-evaluation-design.md), with annotator instructions at [`docs/evaluation/human-evaluation-annotator-guide.md`](evaluation/human-evaluation-annotator-guide.md) and the machine-readable schema at [`schemas/evaluation/human-evaluation-v1.schema.json`](../schemas/evaluation/human-evaluation-v1.schema.json).

The new evaluator accepts a local package containing `manifest.json` and `annotations.json`. The manifest pins the source snapshot, source-manifest SHA-256, documented permission reference, and exact annotation bytes. Candidate and JD keys must be opaque random/HMAC values. The package contains no row IDs or identity map. The reader verifies hashes and schema before metrics and emits only aggregate output or stable error codes.

Retrieval labels must come from JD/JD-criterion queries independent of CVs. Assessment requires two blind annotators and adjudication. The evaluator reports retrieval and rubric assessment separately. No independent JD set or new HR/IT labels have been collected for this protocol, so no new quality metric is available.

Older `scripts/eval_harness.py` artifacts and visible synthetic fixtures are legacy software/evaluation tooling. They are not accepted as human labels, independent queries, or hiring-quality evidence. Keep any local real-CV package under approved access-controlled storage, never in Git; do not upload text, excerpts, PII, row IDs, or labels to external providers for this evaluation.
