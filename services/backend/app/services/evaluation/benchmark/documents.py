"""Generated synthetic files exercise actual intake and parsing, without AI jobs."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid
from docx import Document as WordDocument
from docx.shared import Inches,Pt
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Application,Candidate,CandidateIdentity
from app.services.intake import upload_application_document
from app.services.provenance import ingest_and_parse_document
from .contracts import DatasetInputs,PROFILES
from .dataset import canonical_case,select_runs
from .isolation import IsolationContext,assert_isolated_database
from .seed import seed_cases

GENERATOR='python-docx+libreoffice.v1'

def document_cases(inputs):
    rows=[]
    for role in sorted(inputs.roles):
        candidates=[c for c in inputs.cases if c.role_family==role]
        rows.extend(candidates[i] for i in (0,4,8,1))
    return rows

def _libreoffice():
    binary=shutil.which('soffice') or shutil.which('libreoffice')
    mac=Path('/Applications/LibreOffice.app/Contents/MacOS/soffice')
    if not binary and mac.is_file(): binary=str(mac)
    if not binary: raise RuntimeError('BENCHMARK_LIBREOFFICE_REQUIRED')
    # Production intake checks PATH; retain the real renderer for the entire smoke.
    os.environ['PATH']=str(Path(binary).parent)+os.pathsep+os.environ.get('PATH','')
    return binary

def materialize_documents(inputs: DatasetInputs,output: Path) -> list[Path]:
    binary=_libreoffice()
    output.mkdir(parents=True,exist_ok=True)
    files=[]
    metadata=[]
    version=subprocess.run([binary,'--version'],capture_output=True,text=True,check=True).stdout.strip()
    with tempfile.TemporaryDirectory(prefix='talentscreen-fixture-render-') as temp:
        for index,case in enumerate(document_cases(inputs)):
            word=WordDocument()
            word.sections[0].top_margin=Inches(.6)
            word.sections[0].bottom_margin=Inches(.6)
            style=word.styles['Normal']
            style.font.name='Arial'
            style.font.size=Pt(10)
            style.paragraph_format.space_after=Pt(3)
            for line in case.cv_text.splitlines(): word.add_paragraph(line)
            source=Path(temp)/(case.case_id+'.docx')
            word.save(source)
            suffix='.pdf' if index%2==0 else '.docx'
            destination=output/(case.case_id+suffix)
            if suffix=='.pdf':
                subprocess.run([binary,f'-env:UserInstallation={(Path(temp)/"profile").as_uri()}',
                    '--headless','--convert-to','pdf','--outdir',str(output),str(source)],
                    timeout=45,check=True,capture_output=True)
                if not destination.is_file(): raise RuntimeError('BENCHMARK_PDF_RENDER_FAILED')
            else:
                shutil.copyfile(source,destination)
            files.append(destination)
            metadata.append({'case_id':case.case_id,'file':destination.name,'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
                'language':case.language,'role_family':case.role_family})
    (output/'document-manifest.json').write_text(json.dumps({'generator':GENERATOR,'renderer_version':version,'documents':metadata},indent=2))
    return files

async def run_document_smoke(db: AsyncSession,inputs: DatasetInputs,context: IsolationContext,output: Path) -> dict:
    await assert_isolated_database(db,context)
    if not output.resolve().is_relative_to(context.temporary_root.resolve()):
        raise ValueError('BENCHMARK_ISOLATION_DOCUMENT_PATH')
    rows=document_cases(inputs)
    selection=select_runs(inputs,split=None,case_ids=tuple(c.case_id for c in rows),profiles=PROFILES,seed=20261008)
    seeded=await seed_cases(db,inputs,selection,context)
    manifest=json.loads((output/'document-manifest.json').read_text())
    results=[]
    compact=lambda s: ' '.join(s.split())
    for case,info in zip(rows,manifest['documents'],strict=True):
        seed=seeded[case.case_id]
        core=await db.get(Application,seed.application_id)
        original_candidate=await db.get(Candidate,core.candidate_id)
        candidate=Candidate(id=uuid.uuid4(),organization_id=original_candidate.organization_id,public_label='SMOKE-'+uuid.uuid4().hex)
        db.add(candidate)
        await db.flush()
        db.add(CandidateIdentity(candidate_id=candidate.id,name='Linh Nguyen'))
        app=Application(id=uuid.uuid4(),requisition_id=core.requisition_id,candidate_id=candidate.id,generation=1,row_version=1)
        db.add(app)
        await db.flush()
        source=output/info['file']
        response,_=await upload_application_document(db,app.id,source.read_bytes(),source.name,seed.ctx)
        sanitized=await ingest_and_parse_document(db,response.document.id)
        text=sanitized.canonical_text
        # Fixture contacts only; the report exports booleans, never document text.
        pii_removed='Linh Nguyen' not in text and '.example.test' not in text
        spans=canonical_case(case)[2]
        technical=[s.text for previous,s in zip(spans,spans[1:]) if previous.text=='TECHNICAL EXPERIENCE']
        evidence_preserved=bool(technical) and all(compact(t) in compact(text) for t in technical)
        results.append({**info,'pii_removed':pii_removed,'evidence_preserved':evidence_preserved,
                        'sanitized_sha256':sanitized.sha256,'status':sanitized.status.value})
    await db.flush()
    return {'generator':GENERATOR,'processed':len(results),'passed':sum(r['pii_removed'] and r['evidence_preserved'] for r in results),
            'documents':results}
