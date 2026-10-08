"""Explicit, owned disposable database and storage for benchmark mutation."""
from __future__ import annotations
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings

LABEL = 'talentscreen.benchmark.experiment'

@dataclass(frozen=True)
class IsolationContext:
    experiment_id: uuid.UUID
    container_id: str
    nonce: str = field(repr=False)
    database_name: str
    database_url: str = field(repr=False)
    database_sync_url: str = field(repr=False)
    temporary_root: Path
    storage_root: Path

    def private_environment(self) -> dict[str, str]:
        # This descriptor stays in the local child environment, never a report.
        return {'DATABASE_URL': self.database_url, 'DATABASE_SYNC_URL': self.database_sync_url,
                'PRIVATE_STORAGE_ROOT': str(self.storage_root), 'BENCHMARK_ISOLATION_CONTEXT': json.dumps({
                    'experiment_id': str(self.experiment_id), 'container_id': self.container_id,
                    'nonce': self.nonce, 'database_name': self.database_name,
                    'temporary_root': str(self.temporary_root), 'storage_root': str(self.storage_root)})}

    @classmethod
    def from_environment(cls):
        raw=json.loads(os.environ['BENCHMARK_ISOLATION_CONTEXT'])
        return cls(experiment_id=uuid.UUID(raw['experiment_id']), container_id=raw['container_id'],
                   nonce=raw['nonce'],database_name=raw['database_name'],
                   database_url=os.environ['DATABASE_URL'],database_sync_url=os.environ['DATABASE_SYNC_URL'],
                   temporary_root=Path(raw['temporary_root']),storage_root=Path(raw['storage_root']))


def _verify_storage(context: IsolationContext) -> None:
    root=context.temporary_root
    storage=context.storage_root
    if (root.is_symlink() or storage.is_symlink() or not root.is_dir() or not storage.is_dir()
        or not root.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())
        or root.resolve()==Path(tempfile.gettempdir()).resolve()
        or not storage.resolve().is_relative_to(root.resolve()) or storage.resolve()==root.resolve()
        or not (root/'.benchmark-owner').is_file()
        or (root/'.benchmark-owner').is_symlink()
        or (root/'.benchmark-owner').read_text()!=context.nonce):
        raise ValueError('BENCHMARK_ISOLATION_STORAGE_INVALID')


async def assert_isolated_database(db: AsyncSession, context: IsolationContext) -> None:
    _verify_storage(context)
    settings=get_settings()
    if Path(settings.PRIVATE_STORAGE_ROOT).resolve()!=context.storage_root.resolve():
        raise ValueError('BENCHMARK_ISOLATION_STORAGE_MISMATCH')
    async_url=make_url(context.database_url)
    sync_url=make_url(context.database_sync_url)
    actual_url=db.bind.url
    comparable=lambda u: (u.username,u.password,u.host,u.port,u.database)
    if (async_url.host!='127.0.0.1' or not async_url.port
        or async_url.database!=context.database_name or comparable(async_url)!=comparable(sync_url)
        or comparable(actual_url)!=comparable(async_url)):
        raise ValueError('BENCHMARK_ISOLATION_DSN_MISMATCH')
    row=(await db.execute(text("SELECT current_database(), shobj_description(oid, 'pg_database') "
                               "FROM pg_database WHERE datname=current_database()"))).one()
    if row[0]!=context.database_name or row[1]!='benchmark:'+context.nonce:
        raise ValueError('BENCHMARK_ISOLATION_DATABASE_MISMATCH')


def _docker(args: list[str]) -> str:
    return subprocess.run(['docker',*args],check=True,capture_output=True,text=True).stdout.strip()


def cleanup_owned_container(container_id: str, experiment_id: str) -> bool:
    try:
        owner=_docker(['inspect','--format','{{ index .Config.Labels "'+LABEL+'" }}',container_id])
        if owner!=experiment_id:
            return False
        _docker(['stop',container_id])
        return True
    except subprocess.CalledProcessError:
        return False


def run_in_isolation(command: list[str]) -> int:
    """Own the exact ID for migrations, child invocation and interruption cleanup."""
    experiment_id=uuid.uuid4()
    nonce=secrets.token_hex(32)
    password=secrets.token_hex(24)
    root=Path(tempfile.mkdtemp(prefix='talentscreen-benchmark-'))
    root.chmod(0o700)
    (root/'.benchmark-owner').write_text(nonce)
    storage=root/'storage'
    storage.mkdir(mode=0o700)
    container_id=None
    previous=signal.getsignal(signal.SIGTERM)
    child=None
    def terminate(signum,frame):
        if child is not None and child.poll() is None:
            child.send_signal(signal.SIGTERM)
            try:child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill();child.wait()
            return
        raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM,terminate)
    try:
        container_id=_docker(['run','--rm','--label',f'{LABEL}={experiment_id}',
            '-e',f'POSTGRES_PASSWORD={password}','-e','POSTGRES_DB=talentscreen_benchmark',
            '-p','127.0.0.1::5432','-d','pgvector/pgvector:pg16'])
        # pg_isready is bounded and all SQL executes inside this exact owned container.
        import time
        for attempt in range(30):
            try:
                _docker(['exec',container_id,'pg_isready','-U','postgres','-d','talentscreen_benchmark'])
                break
            except subprocess.CalledProcessError:
                if attempt==29: raise RuntimeError('BENCHMARK_DATABASE_NOT_READY')
                time.sleep(1)
        port=_docker(['port',container_id,'5432/tcp'])
        if not re.fullmatch(r'127\.0\.0\.1:\d+',port):
            raise ValueError('BENCHMARK_ISOLATION_PORT_INVALID')
        context=IsolationContext(experiment_id,container_id,nonce,'talentscreen_benchmark',
            f'postgresql+asyncpg://postgres:{password}@{port}/talentscreen_benchmark',
            f'postgresql://postgres:{password}@{port}/talentscreen_benchmark',root,storage)
        _docker(['exec',container_id,'psql','-U','postgres','-d','talentscreen_benchmark','-v','ON_ERROR_STOP=1','-c',
                 "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"; "
                 "COMMENT ON DATABASE talentscreen_benchmark IS 'benchmark:"+nonce+"';"])
        env={**os.environ,**context.private_environment(),'PYTHONPATH':'services/backend','APP_ENV':'sandbox',
             'PILOT_STAGE':'','JEV_MODE':'off','JEV_API_KEY':''}
        subprocess.run([sys.executable,'-m','alembic','upgrade','head'],env=env,check=True)
        child=subprocess.Popen(command,env=env)
        try:return child.wait()
        except KeyboardInterrupt:
            terminate(signal.SIGTERM,None)
            return 130
    finally:
        signal.signal(signal.SIGTERM,previous)
        if container_id:
            cleanup_owned_container(container_id,str(experiment_id))
        # Never remove a directory whose ownership marker changed.
        if (root/'.benchmark-owner').is_file() and (root/'.benchmark-owner').read_text()==nonce:
            shutil.rmtree(root)

if __name__=='__main__':
    args=sys.argv[1:]
    if args and args[0]=='--': args=args[1:]
    if not args: raise SystemExit('Usage: isolation -- command [arguments]')
    raise SystemExit(run_in_isolation(args))
