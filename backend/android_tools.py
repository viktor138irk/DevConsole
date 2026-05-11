import glob
import os
from pathlib import Path

from backend.shell_runner import run_command

DATA_DIR = Path(os.getenv('DEVCONSOLE_DATA_DIR', '/var/lib/devconsole'))
PROJECTS_DIR = DATA_DIR / 'projects'


def list_devices() -> dict:
    return run_command('adb devices -l', PROJECTS_DIR.as_posix(), timeout=60)


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
