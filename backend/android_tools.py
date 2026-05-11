import glob
import os
from pathlib import Path

from backend.shell_runner import run_command

DATA_DIR = Path(os.getenv('DEVCONSOLE_DATA_DIR', '/var/lib/devconsole'))
PROJECTS_DIR = DATA_DIR / 'projects'


def _runtime_env_prefix() -> str:
    runtime_home = os.getenv('DEVCONSOLE_RUNTIME_HOME') or os.getenv('HOME') or '/home/devconsole'
    android_home = os.getenv('ANDROID_HOME') or os.getenv('ANDROID_SDK_ROOT') or f'{runtime_home}/Android'
    flutter_home = os.getenv('FLUTTER_HOME') or f'{runtime_home}/flutter'
    return (
        f'export HOME="{runtime_home}" '
        f'ANDROID_HOME="{android_home}" '
        f'ANDROID_SDK_ROOT="{android_home}" '
        f'PATH="{flutter_home}/bin:{android_home}/cmdline-tools/latest/bin:{android_home}/platform-tools:$PATH" && '
    )


def _adb(command: str) -> str:
    return f'{_runtime_env_prefix()}adb {command}'


def list_devices() -> dict:
    result = run_command(_adb('devices -l'), PROJECTS_DIR.as_posix(), timeout=60)
    result['devices'] = parse_devices(result.get('stdout', ''))
    return result


def _parse_adb_line_metadata(parts: list[str]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for part in parts[2:]:
        if ':' not in part:
            continue
        key, value = part.split(':', 1)
        metadata[key.strip()] = value.strip()
    return metadata


def _pretty_token(value: str) -> str:
    return value.replace('_', ' ').replace('-', ' ').strip()


def parse_devices(stdout: str) -> list[dict]:
    devices: list[dict] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.startswith('List of devices'):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial = parts[0]
        state = parts[1]
        adb_meta = _parse_adb_line_metadata(parts)
        if state != 'device':
            devices.append({'serial': serial, 'state': state, 'title': f'{serial} ({state})', 'subtitle': 'Устройство не готово'})
            continue
        props = get_device_props(serial)
        brand = props.get('brand') or adb_meta.get('product') or ''
        model = props.get('model') or adb_meta.get('model') or ''
        device = props.get('device') or adb_meta.get('device') or ''
        android = props.get('android') or ''
        sdk = props.get('sdk') or ''
        title_parts = []
        if brand:
            title_parts.append(_pretty_token(brand).title())
        if model and model.lower() != brand.lower():
            title_parts.append(_pretty_token(model))
        if not title_parts and device:
            title_parts.append(_pretty_token(device))
        title = ' '.join(title_parts).strip() or serial
        subtitle_parts = []
        if android:
            subtitle_parts.append(f'Android {android}')
        if sdk:
            subtitle_parts.append(f'SDK {sdk}')
        if device:
            subtitle_parts.append(device)
        if adb_meta.get('transport_id'):
            subtitle_parts.append(f"transport {adb_meta['transport_id']}")
        subtitle_parts.append(serial)
        devices.append({
            'serial': serial,
            'state': state,
            'brand': brand,
            'model': model,
            'device': device,
            'android': android,
            'sdk': sdk,
            'adb_meta': adb_meta,
            'title': title,
            'subtitle': ' · '.join(subtitle_parts),
        })
    return devices


def get_device_props(serial: str) -> dict:
    commands = {
        'brand': _adb(f'-s {serial} shell getprop ro.product.brand'),
        'model': _adb(f'-s {serial} shell getprop ro.product.model'),
        'device': _adb(f'-s {serial} shell getprop ro.product.device'),
        'android': _adb(f'-s {serial} shell getprop ro.build.version.release'),
        'sdk': _adb(f'-s {serial} shell getprop ro.build.version.sdk'),
    }
    props: dict[str, str] = {}
    for key, command in commands.items():
        try:
            result = run_command(command, PROJECTS_DIR.as_posix(), timeout=20)
            props[key] = (result.get('stdout') or '').strip()
        except Exception:
            props[key] = ''
    return props


def find_apks(workspace: str) -> list[str]:
    root = Path(workspace).resolve()
    patterns = [
        str(root / '**' / 'build' / 'app' / 'outputs' / 'flutter-apk' / '*.apk'),
        str(root / '**' / 'build' / 'outputs' / 'apk' / '**' / '*.apk'),
        str(root / '**' / '*.apk'),
    ]
    found: list[str] = []
    for pattern in patterns:
        found.extend(glob.glob(pattern, recursive=True))
    return sorted(set(found), key=lambda p: os.path.getmtime(p), reverse=True)


def build_android(workspace: str) -> dict:
    root = Path(workspace).resolve()
    if (root / 'pubspec.yaml').exists():
        return run_command('flutter build apk --debug', root.as_posix(), timeout=1800)
    gradlew = root / 'gradlew'
    if gradlew.exists():
        return run_command('chmod +x ./gradlew && ./gradlew assembleDebug', root.as_posix(), timeout=1800)
    if (root / 'android' / 'gradlew').exists():
        return run_command('cd android && chmod +x ./gradlew && ./gradlew assembleDebug', root.as_posix(), timeout=1800)
    return run_command('gradle assembleDebug', root.as_posix(), timeout=1800)


def install_latest_apk(workspace: str) -> dict:
    apks = find_apks(workspace)
    if not apks:
        raise ValueError('APK not found. Build project first.')
    return run_command(_adb(f'install -r "{apks[0]}"'), Path(workspace).resolve().as_posix(), timeout=600)
