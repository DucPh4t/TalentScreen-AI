"""Real PDF/DOCX smoke passes through intake, parsing and PII redaction."""
from pathlib import Path
import pytest
from app.services.evaluation.benchmark.dataset import load_inputs
from app.services.evaluation.benchmark.documents import materialize_documents, run_document_smoke
from tests.test_ai_benchmark_isolation import owned_context

DATA=Path(__file__).resolve().parents[3]/'fixtures/ai_benchmark/golden_100'

@pytest.mark.asyncio
async def test_four_documents_preserve_technical_evidence_and_remove_pii(test_session_factory,owned_context,tmp_path):
    inputs=load_inputs(DATA)
    output=owned_context.temporary_root/'documents'
    files=materialize_documents(inputs,output)
    assert len(files)==4
    assert sum(p.suffix=='.pdf' for p in files)==2
    assert sum(p.suffix=='.docx' for p in files)==2
    async with test_session_factory() as db:
        report=await run_document_smoke(db,inputs,owned_context,output)
        assert report['processed']==4 and report['passed']==4
        assert {r['language'] for r in report['documents']}=={'vi','en','mixed'}
        assert {r['role_family'] for r in report['documents']}==set(inputs.roles)
        assert all(r['pii_removed'] and r['evidence_preserved'] for r in report['documents'])
        assert all(len(r['sha256'])==64 for r in report['documents'])
