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


class ManualFlutterBatchRequest(BaseModel):
    workspace: str
    commands: str
    device: str | None = None
    timeout_per_command: int | None = 3600
    stop_on_error: bool = True


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


def _split_batch(raw_commands: str) -> list[str]:
    commands = []
    for line in (raw_commands or '').splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith('#'):
            continue
        commands.append(cleaned)
    if not commands:
        raise HTTPException(status_code=400, detail='Flutter command batch is empty')
    if len(commands) > 30:
        raise HTTPException(status_code=400, detail='Too many commands in batch')
    return commands


def _event(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + '\n'


def _run_flutter_process(cwd: str, args: str, device: str | None, timeout: int, batch_index: int | None = None):
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
    label = ' '.join(command)
    add_log('Manual Flutter command started: ' + label)
    yield _event({'type': 'start', 'task_id': task_id, 'batch_index': batch_index, 'message': label})

    started_at = time.time()
    try:
        assert process.stdout is not None
        while True:
            if time.time() - started_at > timeout:
                yield _event({'type': 'error', 'task_id': task_id, 'batch_index': batch_index, 'message': 'Manual Flutter command timeout'})
                break
            line = process.stdout.readline()
            if line:
                yield _event({'type': 'line', 'task_id': task_id, 'batch_index': batch_index, 'message': line.rstrip()})
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

    add_log('Manual Flutter command finished: ' + label + f' exit {returncode}')
    yield _event({'type': 'done', 'task_id': task_id, 'batch_index': batch_index, 'returncode': returncode, 'message': label})
    return returncode


def _stream_manual_flutter(workspace: str, args: str, device: str | None, timeout: int):
    cwd = _workspace_cwd(workspace)
    yield from _run_flutter_process(cwd, args, device, timeout)


def _stream_manual_flutter_batch(payload: ManualFlutterBatchRequest):
    cwd = _workspace_cwd(payload.workspace)
    commands = _split_batch(payload.commands)
    timeout = max(30, min(int(payload.timeout_per_command or 3600), 7200))
    yield _event({'type': 'batch_start', 'message': f'Flutter batch started: {len(commands)} commands', 'total': len(commands)})
    add_log(f'Manual Flutter batch started: {len(commands)} commands')

    for index, command in enumerate(commands, start=1):
        yield _event({'type': 'line', 'batch_index': index, 'message': f'▶ [{index}/{len(commands)}] {command}'})
        returncode = None
        runner = _run_flutter_process(cwd, command, payload.device, timeout, index)
        try:
            while True:
                item = next(runner)
                yield item
        except StopIteration as stop:
            returncode = stop.value
        if returncode != 0 and payload.stop_on_error:
            yield _event({'type': 'error', 'batch_index': index, 'message': f'Batch stopped on error: {command}'})
            yield _event({'type': 'batch_done', 'success': False, 'failed_index': index})
            add_log(f'Manual Flutter batch stopped on command {index}')
            return

    yield _event({'type': 'batch_done', 'success': True, 'message': 'Flutter batch completed'})
    add_log('Manual Flutter batch completed')


@router.post('/flutter-manual-stream')
async def flutter_manual_stream(payload: ManualFlutterRequest):
    timeout = max(30, min(int(payload.timeout or 3600), 7200))
    return StreamingResponse(
        _stream_manual_flutter(payload.workspace, payload.args, payload.device, timeout),
        media_type='application/x-ndjson',
    )


@router.post('/flutter-batch-stream')
async def flutter_batch_stream(payload: ManualFlutterBatchRequest):
    return StreamingResponse(
        _stream_manual_flutter_batch(payload),
        media_type='application/x-ndjson',
    )
