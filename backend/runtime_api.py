import json
import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.android_tools import find_apks
from backend.runtime_logs import get_logs, add_log
from backend.shell_runner import run_command

router = APIRouter(prefix='/api/runtime', tags=['runtime'])


def _runtime_env_prefix() -> str:
    runtime_home = os.getenv('DEVCONSOLE_RUNTIME_HOME') or os.getenv('HOME') or '/home/devconsole'
    flutter_home = os.getenv('FLUTTER_HOME') or f'{runtime_home}/flutter'
    android_home = os.getenv('ANDROID_HOME') or os.getenv('ANDROID_SDK_ROOT') or f'{runtime_home}/Android'
    pub_cache = os.getenv('PUB_CACHE') or f'{runtime_home}/.pub-cache'

    return (
        f'export HOME="{runtime_home}" '
        f'PUB_CACHE="{pub_cache}" '
        f'ANDROID_HOME="{android_home}" '
        f'ANDROID_SDK_ROOT="{android_home}" '
        f'PATH="{flutter_home}/bin:{android_home}/cmdline-tools/latest/bin:{android_home}/platform-tools:$PATH" && '
    )


def _flutter(command: str) -> str:
    return f'{_runtime_env_prefix()}flutter {command}'


class RuntimeCommandRequest(BaseModel):
    workspace: str
    command: str
    device: str | None = None
    package_name: str | None = None


def _runtime_commands() -> dict[str, dict]:
    return {
        'git_pull': {'label': 'Git Pull', 'command': 'git pull', 'timeout': 600},
        'flutter_clean': {'label': 'Flutter Clean', 'command': _flutter('clean'), 'timeout': 900},
        'flutter_pub_get': {'label': 'Flutter Pub Get', 'command': _flutter('pub get'), 'timeout': 900},
        'flutter_build_apk': {'label': 'Flutter Build APK', 'command': _flutter('build apk --release'), 'timeout': 3600},
        'flutter_run_profile': {'label': 'Flutter Run Profile', 'command': _flutter('run --profile'), 'timeout': 1800, 'device': True},
        'adb_reconnect': {'label': 'ADB Reconnect', 'command': f'{_runtime_env_prefix()}adb reconnect', 'timeout': 120},
        'adb_logcat': {'label': 'ADB Logcat Snapshot', 'command': f'{_runtime_env_prefix()}adb logcat -d -t 300', 'timeout': 120, 'device': True},
    }


def _workspace_cwd(workspace: str) -> str:
    path = Path(workspace).resolve()
    if not path.exists():
        raise HTTPException(status_code=400, detail='Workspace path does not exist')
    return path.as_posix()


def _with_device(command: str, device: str | None, enabled: bool) -> str:
    if not enabled or not device:
        return command
    if 'adb ' in command:
        return command.replace('adb ', f'adb -s {device} ', 1)
    if 'flutter ' in command and ' -d ' not in command:
        return f'{command} -d {device}'
    return command


def _event(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + '\n'


def _stream_command(command: str, cwd: str, timeout: int):
    process = subprocess.Popen(
        command,
        cwd=cwd,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )

    yield _event({'type': 'start', 'message': command})

    try:
        assert process.stdout is not None
        for line in iter(process.stdout.readline, ''):
            if not line:
                break
            yield _event({'type': 'line', 'message': line.rstrip()})

        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        returncode = -1
        yield _event({'type': 'error', 'message': 'Command timeout'})

    yield _event({'type': 'done', 'returncode': returncode})


@router.get('/logs')
async def runtime_logs():
    return {'success': True, 'logs': get_logs()}


@router.get('/commands')
async def runtime_commands():
    return {
        'success': True,
        'commands': [
            {'id': command_id, 'label': config['label'], 'needs_device': bool(config.get('device'))}
            for command_id, config in _runtime_commands().items()
        ],
    }


@router.post('/event')
async def runtime_event(payload: dict):
    message = payload.get('message', 'unknown runtime event')
    add_log(message)
    return {'success': True, 'message': message}


@router.post('/command')
async def runtime_command(payload: RuntimeCommandRequest):
    commands = _runtime_commands()
    config = commands.get(payload.command)
    if not config:
        raise HTTPException(status_code=400, detail='Runtime command is not allowed')

    cwd = _workspace_cwd(payload.workspace)
    command = _with_device(config['command'], payload.device, bool(config.get('device')))

    add_log(f"Runtime command started: {config['label']}")
    result = run_command(command, cwd, timeout=int(config.get('timeout', 900)))
    add_log(f"Runtime command finished: {config['label']} (exit {result['returncode']})")

    return {'success': result['returncode'] == 0, 'command': payload.command, 'label': config['label'], 'result': result}


@router.post('/command-stream')
async def runtime_command_stream(payload: RuntimeCommandRequest):
    commands = _runtime_commands()
    config = commands.get(payload.command)
    if not config:
        raise HTTPException(status_code=400, detail='Runtime command is not allowed')

    cwd = _workspace_cwd(payload.workspace)
    command = _with_device(config['command'], payload.device, bool(config.get('device')))

    add_log(f"Runtime stream started: {config['label']}")

    return StreamingResponse(
        _stream_command(command, cwd, int(config.get('timeout', 900))),
        media_type='application/x-ndjson',
    )


@router.post('/install-latest-apk')
async def runtime_install_latest_apk(payload: RuntimeCommandRequest):
    cwd = _workspace_cwd(payload.workspace)
    apks = find_apks(cwd)
    if not apks:
        raise HTTPException(status_code=404, detail='APK not found. Build project first.')

    adb = f'{_runtime_env_prefix()}adb'
    if payload.device:
        adb = f'{_runtime_env_prefix()}adb -s {payload.device}'

    command = f'{adb} install -r "{apks[0]}"'
    add_log(f'Runtime APK install started: {apks[0]}')
    result = run_command(command, cwd, timeout=900)
    add_log(f"Runtime APK install finished (exit {result['returncode']})")
    return {'success': result['returncode'] == 0, 'apk': apks[0], 'device': payload.device, 'result': result}


@router.post('/restart-app')
async def runtime_restart_app(payload: RuntimeCommandRequest):
    if not payload.package_name:
        raise HTTPException(status_code=400, detail='package_name is required')

    cwd = _workspace_cwd(payload.workspace)
    adb = f'{_runtime_env_prefix()}adb'
    if payload.device:
        adb = f'{_runtime_env_prefix()}adb -s {payload.device}'

    command = f'{adb} shell monkey -p {payload.package_name} 1'
    add_log(f'Runtime app restart requested: {payload.package_name}')
    result = run_command(command, cwd, timeout=120)
    add_log(f"Runtime app restart finished (exit {result['returncode']})")
    return {'success': result['returncode'] == 0, 'package_name': payload.package_name, 'device': payload.device, 'result': result}
