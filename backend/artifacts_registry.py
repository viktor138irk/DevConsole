import json
import os
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(os.getenv('DEVCONSOLE_DATA_DIR', '/var/lib/devconsole'))
ARTIFACTS_FILE = DATA_DIR / 'apk_artifacts.json'
MAX_ARTIFACTS_PER_WORKSPACE = 50


def _read_all() -> list[dict]:
    if not ARTIFACTS_FILE.exists():
        return []
    try:
        data = json.loads(ARTIFACTS_FILE.read_text(encoding='utf-8'))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_all(items: list[dict]) -> list[dict]:
    ARTIFACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    return items


def list_artifacts(workspace: str | None = None, limit: int = 20) -> list[dict]:
    items = _read_all()
    if workspace:
        items = [item for item in items if item.get('workspace') == workspace]
    return sorted(items, key=lambda item: item.get('created_at', ''), reverse=True)[:limit]


def record_apk_artifact(
    workspace: str,
    apk_path: str,
    project_name: str | None = None,
    version: str | None = None,
    build: str | int | None = None,
    ota_result: dict | None = None,
    source: str = 'runtime',
) -> dict:
    path = Path(apk_path)
    stat = path.stat() if path.exists() else None
    item = {
        'id': f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{abs(hash((workspace, apk_path))) % 1000000}",
        'workspace': workspace,
        'project_name': project_name or '',
        'apk_path': path.as_posix(),
        'apk_name': path.name,
        'size_bytes': stat.st_size if stat else 0,
        'version': version or '',
        'build': str(build or ''),
        'source': source,
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'ota_success': bool((ota_result or {}).get('success')),
        'ota_latest_json': (ota_result or {}).get('latest_json'),
        'ota_uploaded': (ota_result or {}).get('uploaded') or [],
    }

    items = _read_all()
    items.append(item)

    workspace_items = [entry for entry in items if entry.get('workspace') == workspace]
    workspace_items = sorted(workspace_items, key=lambda entry: entry.get('created_at', ''), reverse=True)
    keep_ids = {entry.get('id') for entry in workspace_items[:MAX_ARTIFACTS_PER_WORKSPACE]}
    items = [entry for entry in items if entry.get('workspace') != workspace or entry.get('id') in keep_ids]

    _write_all(items)
    return item
