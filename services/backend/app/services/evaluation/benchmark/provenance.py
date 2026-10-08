"""Local code identity only; never export Git paths, remotes or status filenames."""
from pathlib import Path
import os
import re
import subprocess


def git_source_provenance(root: Path | None = None) -> dict:
    root = root or Path(__file__).resolve().parents[6]
    unavailable = {'git_sha': None, 'git_dirty': None, 'git_provenance_status': 'unavailable'}
    # Hooks can inherit repository redirects; identify the requested source checkout.
    environment = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    environment['GIT_OPTIONAL_LOCKS'] = '0'  # status must not refresh/write the index
    try:
        revision = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                                  capture_output=True, text=True, timeout=5, check=False, env=environment)
        status = subprocess.run(['git', '-C', str(root), 'status', '--porcelain', '-z', '--untracked-files=normal'],
                                capture_output=True, text=False, timeout=5, check=False, env=environment)
        sha = revision.stdout.strip()
        if revision.returncode or status.returncode or not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', sha):
            return unavailable
        return {'git_sha': sha, 'git_dirty': bool(status.stdout), 'git_provenance_status': 'available'}
    except (OSError, subprocess.SubprocessError):
        return unavailable
