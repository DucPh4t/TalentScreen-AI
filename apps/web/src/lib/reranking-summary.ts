type EvidenceSummary = {mode: string; applied: boolean; needs_evidence_review: boolean};

export function evidenceReviewMessage(summary?: EvidenceSummary | null): string | null {
  if (!summary?.applied || !summary.needs_evidence_review || !["rerank", "gate_experiment"].includes(summary.mode)) return null;
  return "Một số bằng chứng chưa được đưa vào đánh giá. Hãy đối chiếu CV hoặc yêu cầu AI tìm thêm trước khi quyết định.";
}
