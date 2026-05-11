import os
import subprocess
from pathlib import Path

DATA_DIR = Path(os.getenv('DEVCONSOLE_DATA_DIR', '/var/lib/devconsole'))
PROJECTS_DIR = DATA_DIR / 'projects'

BLOCKED_TOKENS = [
    'rm -rf /',
    'mkfs',
    ':(){',
    'dd if=',
    'shutdown',
    'reboot',
    'poweroff',
]


def _is_inside_projects(path: Path) -> bool:
    try:
        path.resolve().relative_to(PROJECTS_DIR.resolve())
        return True
    except ValueError:
        return False


def run_command(command: str, cwd: str | None = None, timeout: int = 900) -> dict:
    if not command.strip():
        raise ValueError('Command is empty')

    lowered = command.lower()
    for token in BLOCKED_TOKENS:
        if token in lowered:
            raise ValueError(f'Blocked unsafe command: {token}')

    workdir = Path(cwd or PROJECTS_DIR).resolve()
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

    if not _is_inside_projects(workdir):
        raise ValueError('Command cwd must be inside DevConsole projects directory')

    process = subprocess.run(
        command,
        cwd=workdir,
        shell=True,
        text=True,
        capture_output=True,
        timeout=timeout,
    )

    return {
        'command': command,
        'cwd': workdir.as_posix(),
        'returncode': process.returncode,
        'stdout': process.stdout[-20000:],
        'stderr': process.stderr[-20000:],
    }
