import json
import os
import signal
import subprocess
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.runtime_logs import add_log

router = APIRouter(prefix='/api/runtime', tags=['runtime-flutter-manual'])
ACTIVE_MANUAL_FLUTTER: dict[str, subprocess.Popen] = {}

ALLOWED_FIRST_WORDS = {
    'analyze',
    'assemble',
    'attach',
    'build',
    'channel',
    'clean',
    'config',
    'devices',
    'doctor',
    'drive',
    'emulators',
    'gen-l10n',
    'logs',
    'packages',
    'precache',
    'pub',
    'run',
    'screenshot',
    'test',
    'upgrade',
    'version',
}


class ManualFlutterRequest(BaseModel):
    workspace: str
    args: str
    device: str | None = None
    timeout: int | None = 3600


def _runtime_env() -> dict:
    runtime_home = os.getenv('DEVCONSOLE_RUNTIME_HOME') or os.getenv('HOME') or '/home/devconsole'
    flutter_home = os.getenv('FLUTTER_HOME') or f'{runtime_home}/flutter'
    android_home = os.getenv('ANDROID_HOME') or os.getenv('ANDROID_SDK_ROOT') or f'{runtime_home}/Android'
    pub_cache = os.getenv('PUB_CACHE') or f'{runtime_home}/.pub-cache'
    env = os.environ.copy()
    env.update({
        'HOME': runtime_home,
        'PUB_CACHE': pub_cache,
        'ANDROID_HOME': android_home,
        'ANDROID_SDK_ROOT': android_home,
        'PATH': f'{flutter_home}/bin:{android_home}/cmdline-tools/latest/bin:{android_home}/platform-tools:' + env.get('PATH', ''),
    })
    return env


def _workspace_cwd(workspace: str) -> str:
    path = Path(workspace).resolve()
    if not path.exists():
        raise HTTPException(status_code=400, detail='Workspace path does not exist')
    return path.as_posix()


def _split_args(raw_args: str) -> list[str]:
    cleaned = (raw_args or '').strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail='Flutter command is empty')
    if cleaned.startswith('flutter '):
        cleaned = cleaned[len('flutter '):].strip()
    if any(ch in cleaned for ch in ['\n', '\r', '\x00']):
        raise HTTPException(status_code=400, detail='Invalid Flutter command')
    parts = cleaned.split()
    if not parts:
        raise HTTPException(status_code=400, detail='Flutter command is empty')
    if parts[0] not in ALLOWED_FIRST_WORDS:
        raise HTTPException(status_code=400, detail='Unsupported Flutter subcommand')
    return parts


def _event(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + '\n'


def _stream_manual_flutter(workspace: str, args: str, device: str | None, timeout: int):
    cwd = _workspace_cwd(workspace)
    parts = _split_args(args)
    if device and '-d' not in parts and '--device-id' not in parts:
        parts.extend(['-d', device])
    command = ['flutter', *parts]
    task_id = uuid.uuid4().hex

    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=_runtime_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
        bufsize=1,
        preexec_fn=os.setsid,
    )
    ACTIVE_MANUAL_FLUTTER[task_id] = process
    add_log('Manual Flutter command started: ' + ' '.join(command))
    yield _event({'type': 'start', 'task_id': task_id, 'message': ' '.join(command)})

    started_at = time.time()
    try:
        assert process.stdout is not None
        while True:
            if time.time() - started_at > timeout:
                yield _event({'type': 'error', 'task_id': task_id, 'message': 'Manual Flutter command timeout'})
                break
            line = process.stdout.readline()
            if line:
                yield _event({'type': 'line', 'task_id': task_id, 'message': line.rstrip()})
                continue
            if process.poll() is not None:
                break
            time.sleep(0.1)
        returncode = process.poll()
        if returncode is None:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            returncode = -1
    finally:
        ACTIVE_MANUAL_FLUTTER.pop(task_id, None)

    add_log('Manual Flutter command finished: ' + ' '.join(command) + f' exit {returncode}')
    yield _event({'type': 'done', 'task_id': task_id, 'returncode': returncode})


@router.post('/flutter-manual-stream')
async def flutter_manual_stream(payload: ManualFlutterRequest):
    timeout = max(30, min(int(payload.timeout or 3600), 7200))
    return StreamingResponse(
        _stream_manual_flutter(payload.workspace, payload.args, payload.device, timeout),
        media_type='application/x-ndjson',
    )
