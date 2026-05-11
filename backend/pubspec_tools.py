import re
from pathlib import Path


_VERSION_RE = re.compile(r'^\s*version\s*:\s*([^\s#]+)')


def read_pubspec_version(workspace: str) -> dict | None:
    """Read Flutter version/build from pubspec.yaml.

    Supports the standard Flutter format: version: 1.2.3+45
    Returns None when pubspec.yaml is missing or version is not declared.
    """
    pubspec_path = Path(workspace).resolve() / 'pubspec.yaml'
    if not pubspec_path.exists():
        return None

    try:
        content = pubspec_path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        content = pubspec_path.read_text(errors='ignore')

    for line in content.splitlines():
        match = _VERSION_RE.match(line)
        if not match:
            continue

        full_version = match.group(1).strip()
        version, build = _split_flutter_version(full_version)
        return {
            'success': True,
            'version': version,
            'build': build,
            'full_version': full_version,
            'pubspec_path': pubspec_path.as_posix(),
        }

    return None


def _split_flutter_version(full_version: str) -> tuple[str, str]:
    if '+' not in full_version:
        return full_version, '1'

    version, build = full_version.split('+', 1)
    return version.strip() or '0.0.1', build.strip() or '1'
