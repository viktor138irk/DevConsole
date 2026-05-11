import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from backend.config_store import get_github_public_config, has_openai_key
from backend.runtime_logs import add_log
from backend.shell_runner import run_command

router = APIRouter(prefix='/api/system', tags=['system'])

DATA_DIR = Path(os.getenv('DEVCONSOLE_DATA_DIR', '/var/lib/devconsole'))
PROJECTS_DIR = DATA_DIR / 'projects'


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


def _check(command: str, timeout: int = 20) -> dict:
    try:
        result = run_command(command, PROJECTS_DIR.as_posix(), timeout=timeout)
        return {
            'ok': result['returncode'] == 0,
            'returncode': result['returncode'],
            'stdout': (result.get('stdout') or '').strip()[-600:],
            'stderr': (result.get('stderr') or '').strip()[-600:],
        }
    except Exception as exc:
        return {'ok': False, 'returncode': -1, 'stdout': '', 'stderr': str(exc)}


class SystemRestartRequest(BaseModel):
    target: str


@router.get('/checks')
async def system_checks():
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    env = _runtime_env_prefix()

    checks = [
        {
            'id': 'devconsole',
            'title': 'DevConsole',
            'restartable': True,
            **_check('systemctl is-active devconsole || true', 10),
        },
        {
            'id': 'github',
            'title': 'GitHub',
            'restartable': False,
            'ok': bool(get_github_public_config().get('token_set')),
            'returncode': 0,
            'stdout': 'token configured' if get_github_public_config().get('token_set') else 'token missing',
            'stderr': '',
        },
        {
            'id': 'openai',
            'title': 'OpenAI',
            'restartable': False,
            'ok': has_openai_key(),
            'returncode': 0,
            'stdout': 'configured' if has_openai_key() else 'not configured',
            'stderr': '',
        },
        {
            'id': 'flutter',
            'title': 'Flutter',
            'restartable': False,
            **_check(f'{env}flutter --version | head -n 1', 30),
        },
        {
            'id': 'android_sdk',
            'title': 'Android SDK',
            'restartable': False,
            **_check(f'{env}sdkmanager --version', 30),
        },
        {
            'id': 'adb',
            'title': 'ADB',
            'restartable': True,
            **_check(f'{env}adb version | head -n 1', 20),
        },
        {
            'id': 'docker',
            'title': 'Docker',
            'restartable': True,
            **_check('docker --version', 20),
        },
        {
            'id': 'nginx',
            'title': 'Nginx',
            'restartable': True,
            **_check('systemctl is-active nginx || true', 10),
        },
    ]

    for item in checks:
        if item['id'] == 'devconsole':
            item['ok'] = 'active' in item.get('stdout', '')
        if item['id'] == 'nginx':
            item['ok'] = 'active' in item.get('stdout', '')

    return {'success': True, 'systems': checks}


@router.post('/restart')
async def system_restart(payload: SystemRestartRequest):
    target = payload.target
    commands = {
        'devconsole': 'sudo systemctl restart devconsole',
        'adb': f'{_runtime_env_prefix()}adb kill-server && {_runtime_env_prefix()}adb start-server',
        'docker': 'sudo systemctl restart docker',
        'nginx': 'sudo systemctl restart nginx',
    }

    command = commands.get(target)
    if not command:
        return {'success': False, 'message': 'Restart is not allowed for this target'}

    add_log(f'System restart requested: {target}')
    result = _check(command, 60)
    return {'success': result['ok'], 'target': target, 'result': result}
