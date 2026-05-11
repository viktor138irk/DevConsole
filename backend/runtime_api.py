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

from backend.android_tools import find_apks, list_devices
from backend.ota_publish import publish_project_ota
from backend.runtime_logs import get_logs, add_log
from backend.shell_runner import run_command

router = APIRouter(prefix='/api/runtime', tags=['runtime'])
ACTIVE_PROCESSES: dict[str, subprocess.Popen] = {}

PUBLISH_AFTER_COMMANDS = {'flutter_build_apk', 'flutter_run_profile'}


def _runtime_env_prefix() -> str:
    runtime_home = os.getenv('DEVCONSOLE_RUNTIME_HOME') or os.getenv('HOME') or '/home/devconsole'
    flutter_home = os.getenv('FLUTTER_HOME') or f'{runtime_home}/flutter'
    android_home = os.getenv('ANDROID_HOME') or os.getenv('ANDROID_SDK_ROOT') or f'{runtime_home}/Android'
    pub_cache = os.getenv('PUB_CACHE') or f'{runtime_home}/.pub-cache'
    return f'export HOME="{runtime_home}" PUB_CACHE="{pub_cache}" ANDROID_HOME="{android_home}" ANDROID_SDK_ROOT="{android_home}" PATH="{flutter_home}/bin:{android_home}/cmdline-tools/latest/bin:{android_home}/platform-tools:$PATH" && '


def _flutter(command: str) -> str:
    return f'{_runtime_env_prefix()}flutter {command}'


class RuntimeCommandRequest(BaseModel):
    workspace: str
    command: str | None = None
    device: str | None = None
    package_name: str | None = None
    apk_path: str | None = None


class RuntimeStopRequest(BaseModel):
    task_id: str | None = None
    send_confirm: bool = True


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


def _safe_apk_path(workspace: str, apk_path: str | None) -> Path:
    if not apk_path:
        raise HTTPException(status_code=400, detail='apk_path is required')
    root = Path(workspace).resolve()
    target = Path(apk_path).resolve()
    if not root.exists():
        raise HTTPException(status_code=400, detail='Workspace path does not exist')
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail='APK file not found')
    if root not in target.parents and target != root:
        raise HTTPException(status_code=403, detail='APK is outside workspace')
    if target.suffix.lower() != '.apk':
        raise HTTPException(status_code=403, detail='Only APK files are allowed')
    return target


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


def _publish_events(workspace: str):
    yield _event({'type': 'line', 'message': 'OTA publish: preparing latest.json and APK upload'})
    try:
        result = publish_project_ota(workspace)
        if result.get('success'):
            yield _event({'type': 'line', 'message': 'OTA publish: completed'})
            yield _event({'type': 'publish', 'success': True, 'result': result})
        else:
            yield _event({'type': 'line', 'message': f"OTA publish skipped: {result.get('message')}"})
            yield _event({'type': 'publish', 'success': False, 'result': result})
    except Exception as exc:
        yield _event({'type': 'error', 'message': f'OTA publish failed: {exc}'})


def _stream_command(command_id: str, command: str, cwd: str, timeout: int):
    task_id = uuid.uuid4().hex
    process = subprocess.Popen(
        command,
        cwd=cwd,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
        bufsize=1,
        preexec_fn=os.setsid,
    )
    ACTIVE_PROCESSES[task_id] = process
    yield _event({'type': 'start', 'task_id': task_id, 'message': command})
    started_at = time.time()

    try:
        assert process.stdout is not None
        while True:
            if time.time() - started_at > timeout:
                yield _event({'type': 'error', 'task_id': task_id, 'message': 'Command timeout'})
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
        ACTIVE_PROCESSES.pop(task_id, None)

    if returncode == 0 and command_id in PUBLISH_AFTER_COMMANDS:
        yield from _publish_events(cwd)

    yield _event({'type': 'done', 'task_id': task_id, 'returncode': returncode})


@router.get('/logs')
async def runtime_logs():
    return {'success': True, 'logs': get_logs()}


@router.get('/commands')
async def runtime_commands():
    return {'success': True, 'commands': [{'id': command_id, 'label': config['label'], 'needs_device': bool(config.get('device'))} for command_id, config in _runtime_commands().items()]}


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
    if result['returncode'] == 0 and payload.command in PUBLISH_AFTER_COMMANDS:
        result['ota_publish'] = publish_project_ota(cwd)
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
    return StreamingResponse(_stream_command(payload.command, command, cwd, int(config.get('timeout', 900))), media_type='application/x-ndjson')


@router.post('/stop')
async def runtime_stop(payload: RuntimeStopRequest):
    targets = []
    if payload.task_id:
        process = ACTIVE_PROCESSES.get(payload.task_id)
        if process:
            targets.append((payload.task_id, process))
    else:
        targets = list(ACTIVE_PROCESSES.items())
    stopped = []
    for task_id, process in targets:
        try:
            if payload.send_confirm and process.stdin:
                process.stdin.write('Y\n')
                process.stdin.flush()
                time.sleep(0.4)
            if process.poll() is None:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            stopped.append(task_id)
        except Exception as exc:
            add_log(f'Runtime stop error: {exc}')
    add_log(f'Runtime stop requested: {stopped}')
    return {'success': True, 'stopped': stopped}


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


@router.post('/install-apk')
async def runtime_install_apk(payload: RuntimeCommandRequest):
    cwd = _workspace_cwd(payload.workspace)
    apk = _safe_apk_path(cwd, payload.apk_path)
    adb = f'{_runtime_env_prefix()}adb'
    if payload.device:
        adb = f'{_runtime_env_prefix()}adb -s {payload.device}'
    command = f'{adb} install -r "{apk.as_posix()}"'
    add_log(f'Runtime selected APK install started: {apk.name}')
    result = run_command(command, cwd, timeout=900)
    add_log(f"Runtime selected APK install finished: {apk.name} (exit {result['returncode']})")
    return {'success': result['returncode'] == 0, 'apk': apk.as_posix(), 'device': payload.device, 'result': result}


@router.post('/install-apk-all-devices')
async def runtime_install_apk_all_devices(payload: RuntimeCommandRequest):
    cwd = _workspace_cwd(payload.workspace)
    apk = _safe_apk_path(cwd, payload.apk_path)
    devices = list_devices().get('devices') or []
    installed = []
    adb_base = f'{_runtime_env_prefix()}adb'
    for device in devices:
        serial = device.get('serial')
        if not serial:
            continue
        command = f'{adb_base} -s {serial} install -r "{apk.as_posix()}"'
        result = run_command(command, cwd, timeout=900)
        installed.append({'serial': serial, 'success': result['returncode'] == 0, 'result': result})
    add_log(f'Runtime APK install all devices finished: {apk.name}')
    return {'success': all(item['success'] for item in installed) if installed else False, 'apk': apk.as_posix(), 'devices': installed}


@router.post('/delete-apk')
async def runtime_delete_apk(payload: RuntimeCommandRequest):
    cwd = _workspace_cwd(payload.workspace)
    apk = _safe_apk_path(cwd, payload.apk_path)
    apk_name = apk.name
    apk.unlink()
    add_log(f'APK artifact deleted: {apk_name}')
    return {'success': True, 'deleted': apk_name}


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
