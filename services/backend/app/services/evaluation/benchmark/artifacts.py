"""Exclusive experiments, atomic manifests and fsynced append-only journals."""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
from .contracts import RunRecord

def create_output(path: Path) -> None:
    if path.exists() or path.is_symlink():raise ValueError('BENCHMARK_OUTPUT_EXISTS')
    if any(p.is_symlink() for p in path.parents):raise ValueError('BENCHMARK_OUTPUT_PATH_INVALID')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.mkdir(mode=0o700)

def atomic_json(path: Path,value) -> None:
    if path.is_symlink():raise ValueError('ARTIFACT_PATH_INVALID')
    data=value.model_dump(mode='json') if hasattr(value,'model_dump') else value
    atomic_text(path,json.dumps(data,ensure_ascii=False,indent=2)+'\n')

def atomic_text(path: Path,value: str) -> None:
    if path.is_symlink():raise ValueError('ARTIFACT_PATH_INVALID')
    fd,name=tempfile.mkstemp(dir=path.parent,prefix='.artifact-')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            f.write(value);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
        directory=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if os.path.exists(name):os.unlink(name)

def append_event(path: Path,event: dict) -> None:
    if path.is_symlink():raise ValueError('ARTIFACT_PATH_INVALID')
    with path.open('a',encoding='utf-8') as f:
        f.write(json.dumps(event,ensure_ascii=False,separators=(',',':'))+'\n')
        f.flush();os.fsync(f.fileno())

def read_events(path: Path) -> list[dict]:
    if not path.exists():return []
    if path.is_symlink():raise ValueError('ARTIFACT_PATH_INVALID')
    raw=path.read_text()
    if raw and not raw.endswith('\n'):raise ValueError('INCOMPLETE_JOURNAL')
    try:
        rows=[json.loads(line) for line in raw.splitlines()]
        if any(not isinstance(row,dict) for row in rows):raise ValueError()
        return rows
    except (ValueError,TypeError) as e:raise ValueError('INCOMPLETE_JOURNAL') from e

def read_records(path: Path) -> list[RunRecord]:
    try:rows=[RunRecord.model_validate(row) for row in read_events(path)]
    except ValueError as e:raise ValueError('INCOMPLETE_JOURNAL') from e
    keys=[(r.case_id,r.profile) for r in rows]
    if len(keys)!=len(set(keys)):raise ValueError('DUPLICATE_RUN_RECORD')
    return rows

def append_record(path: Path,record: RunRecord) -> None:
    if any((r.case_id,r.profile)==(record.case_id,record.profile) for r in read_records(path)):
        raise ValueError('DUPLICATE_RUN_RECORD')
    append_event(path,record.model_dump(mode='json'))
