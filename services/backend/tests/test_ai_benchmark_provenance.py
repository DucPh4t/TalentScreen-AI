"""Source identity must be real Git state, never filename/credential exports."""
import json
from pathlib import Path
import subprocess
import pytest
from app.services.evaluation.benchmark.runner import run_experiment
from app.services.evaluation.benchmark.mock_provider import BenchmarkMockProvider
from tests.test_ai_benchmark_runner import experiment
from tests.test_ai_benchmark_isolation import owned_context
from tests.test_ai_benchmark_budget import fresh_period


def test_git_provenance_tracks_actual_source_and_excludes_ignored_secrets(tmp_path):
    from app.services.evaluation.benchmark.provenance import git_source_provenance
    def git(*args):
        return subprocess.check_output(['git','-C',str(tmp_path),*args],text=True).strip()
    git('init','-q');git('config','user.name','Fixture');git('config','user.email','fixture@example.test')
    (tmp_path/'code.py').write_text('value = 1\n')
    (tmp_path/'.gitignore').write_text('.env\n')
    git('add','.');git('commit','-qm','Fixture source')
    sha=git('rev-parse','HEAD')
    (tmp_path/'.env').write_text('PRIVATE_MARKER=do-not-export\n')
    clean=git_source_provenance(tmp_path)
    assert clean=={'git_sha':sha,'git_dirty':False,'git_provenance_status':'available'}
    (tmp_path/'code.py').write_text('value = 2\n')
    assert git_source_provenance(tmp_path)['git_dirty'] is True
    git('checkout','--','code.py')
    (tmp_path/'private-name@example.test.txt').write_text('PRIVATE_MARKER')
    output=git_source_provenance(tmp_path)
    assert output['git_sha']==sha and output['git_dirty'] is True
    assert all(marker not in json.dumps(output) for marker in ('PRIVATE_MARKER','private-name','do-not-export',str(tmp_path)))


def test_missing_git_metadata_is_explicitly_unavailable(tmp_path):
    from app.services.evaluation.benchmark.provenance import git_source_provenance
    assert git_source_provenance(tmp_path)=={'git_sha':None,'git_dirty':None,'git_provenance_status':'unavailable'}


@pytest.mark.asyncio
async def test_runner_manifest_retains_source_identity(test_session_factory,experiment):
    inputs,selection,plan,context,output=experiment
    async with test_session_factory() as db:
        result=await run_experiment(db,inputs,selection,context,provider=BenchmarkMockProvider(),budget_plan=plan,output=output,embedding_mode='scripted')
    assert len(result.provenance['git_sha']) in (40,64)
    assert type(result.provenance['git_dirty']) is bool
    assert result.provenance['git_provenance_status']=='available'


def test_git_provenance_ignores_inherited_repository_redirect(tmp_path,monkeypatch):
    from app.services.evaluation.benchmark.provenance import git_source_provenance
    roots=[tmp_path/'source',tmp_path/'other']
    shas=[]
    for n,root in enumerate(roots):
        root.mkdir()
        def git(*args):
            return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
        git('init','-q');git('config','user.name','Fixture');git('config','user.email','fixture@example.test')
        (root/'code.py').write_text(f'value = {n}\n')
        git('add','.');git('commit','-qm',f'Source {n}');shas.append(git('rev-parse','HEAD'))
    monkeypatch.setenv('GIT_DIR',str(roots[1]/'.git'))
    monkeypatch.setenv('GIT_WORK_TREE',str(roots[1]))
    assert git_source_provenance(roots[0])['git_sha']==shas[0]


def test_git_provenance_handles_non_utf8_status_bytes(monkeypatch):
    from app.services.evaluation.benchmark import provenance
    import sys
    original_run=subprocess.run
    def raw_status(command,**kwargs):
        if 'status' in command:
            return original_run([sys.executable,'-c',"import sys; sys.stdout.buffer.write(b'?? invalid-\\xff\\x00')"],**kwargs)
        return subprocess.CompletedProcess(command,0,stdout='a'*40+'\n',stderr='')
    monkeypatch.setattr(provenance.subprocess,'run',raw_status)
    assert provenance.git_source_provenance(Path('/tmp'))=={
        'git_sha':'a'*40,'git_dirty':True,'git_provenance_status':'available'}
