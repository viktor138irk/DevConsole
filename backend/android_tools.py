import glob
import os
from pathlib import Path

from backend.shell_runner import run_command

DATA_DIR = Path(os.getenv('DEVCONSOLE_DATA_DIR', '/var/lib/devconsole'))
PROJECTS_DIR = DATA_DIR / 'projects'


def list_devices() -> dict:
    result = run_command('adb devices -l', PROJECTS_DIR.as_posix(), timeout=60)
    result['devices'] = parse_devices(result.get('stdout', ''))
    return result


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

        if state != 'device':
            devices.append({
                'serial': serial,
                'state': state,
                'title': f'{serial} ({state})',
                'subtitle': 'Устройство не готово',
            })
            continue

        props = get_device_props(serial)
        brand = props.get('brand') or ''
        model = props.get('model') or ''
        device = props.get('device') or ''
        android = props.get('android') or ''
        sdk = props.get('sdk') or ''

        title = ' '.join(part for part in [brand, model] if part).strip() or serial
        subtitle_parts = []
        if android:
            subtitle_parts.append(f'Android {android}')
        if sdk:
            subtitle_parts.append(f'SDK {sdk}')
        if device:
            subtitle_parts.append(device)
        subtitle_parts.append(serial)

        devices.append({
            'serial': serial,
            'state': state,
            'brand': brand,
            'model': model,
            'device': device,
            'android': android,
            'sdk': sdk,
            'title': title,
            'subtitle': ' · '.join(subtitle_parts),
        })

    return devices


def get_device_props(serial: str) -> dict:
    commands = {
        'brand': f'adb -s {serial} shell getprop ro.product.brand',
        'model': f'adb -s {serial} shell getprop ro.product.model',
        'device': f'adb -s {serial} shell getprop ro.product.device',
        'android': f'adb -s {serial} shell getprop ro.build.version.release',
        'sdk': f'adb -s {serial} shell getprop ro.build.version.sdk',
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
    return run_command(f'adb install -r "{apks[0]}"', Path(workspace).resolve().as_posix(), timeout=600)
