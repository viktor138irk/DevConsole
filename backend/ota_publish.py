import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import paramiko

from backend.android_tools import find_apks
from backend.projects_registry import find_project_by_workspace
from backend.pubspec_tools import read_pubspec_version
from backend.runtime_logs import add_log


def _safe_name(value: str) -> str:
    return value.strip().replace('/', '-').replace(' ', '-').lower()


def _apply_pubspec_version(settings: dict, workspace: str) -> dict:
    synced = dict(settings)
    pubspec = read_pubspec_version(workspace)

    if pubspec:
        synced['version'] = pubspec.get('version') or synced.get('version')
        synced['build'] = pubspec.get('build') or synced.get('build')

    return synced


def _latest_json(settings: dict) -> dict:
    notes_raw = settings.get('notes') or ''
    notes = [line.strip() for line in notes_raw.splitlines() if line.strip()]
    if not notes:
        notes = ['Немного нового']

    version = settings.get('version') or '0.0.1'
    build = int(settings.get('build') or 1)
    public_base_url = settings.get('public_base_url') or ''
    latest_apk_name = settings.get('latest_apk_name') or 'pulse-latest.apk'
    versioned_apk_name = settings.get('versioned_apk_name') or f'pulse-{version}+{build}.apk'

    return {
        'version': version,
        'build': build,
        'notes': notes,
        'apk_url': urljoin(public_base_url.rstrip('/') + '/', latest_apk_name),
        'versioned_apk_url': urljoin(public_base_url.rstrip('/') + '/', versioned_apk_name),
    }


def _mkdir_p_sftp(sftp, remote_path: str) -> None:
    path = remote_path.strip('/')
    if not path:
        return
    current = ''
    for part in path.split('/'):
        current += '/' + part
        try:
            sftp.stat(current)
        except IOError:
            sftp.mkdir(current)


def publish_project_ota(workspace: str) -> dict:
    project = find_project_by_workspace(workspace)
    if not project:
        return {'success': False, 'message': 'Project not found in registry'}

    settings = _apply_pubspec_version(project.get('ota') or {}, workspace)
    if not settings.get('enabled'):
        return {'success': False, 'message': 'OTA publish disabled'}

    apks = find_apks(workspace)
    if not apks:
        return {'success': False, 'message': 'APK not found'}

    host = settings.get('sftp_host') or ''
    username = settings.get('sftp_username') or ''
    password = settings.get('sftp_password') or ''
    remote_path = settings.get('remote_path') or ''

    if not host or not username or not password or not remote_path:
        return {'success': False, 'message': 'SFTP settings are incomplete'}

    latest_apk_name = settings.get('latest_apk_name') or 'pulse-latest.apk'
    version = settings.get('version') or '0.0.1'
    build = int(settings.get('build') or 1)
    versioned_apk_name = settings.get('versioned_apk_name') or f'pulse-{version}+{build}.apk'
    latest_json_name = settings.get('latest_json_name') or 'latest.json'

    latest_json = _latest_json(settings)
    tmp_json = Path('/tmp') / f'devconsole-{_safe_name(project.get("name", "project"))}-latest.json'
    tmp_json.write_text(json.dumps(latest_json, ensure_ascii=False, indent=4), encoding='utf-8')

    apk_path = apks[0]

    add_log(f'OTA publish started: {project.get("name")} -> {host}:{remote_path}')
    add_log(f'OTA version synced from pubspec: {version}+{build}')

    transport = paramiko.Transport((host, int(settings.get('sftp_port') or 22)))
    try:
        transport.connect(username=username, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        remote_dir = '/' + remote_path.strip('/')
        _mkdir_p_sftp(sftp, remote_dir)

        sftp.put(apk_path, f'{remote_dir}/{latest_apk_name}')
        sftp.put(apk_path, f'{remote_dir}/{versioned_apk_name}')
        sftp.put(tmp_json.as_posix(), f'{remote_dir}/{latest_json_name}')
        sftp.close()
    finally:
        transport.close()

    add_log(f'OTA publish completed: {latest_json.get("apk_url")}')

    return {
        'success': True,
        'apk': apk_path,
        'latest_json': latest_json,
        'uploaded': [latest_apk_name, versioned_apk_name, latest_json_name],
        'published_at': datetime.utcnow().isoformat() + 'Z',
    }
