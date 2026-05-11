from pathlib import Path
import json
import os

DATA_DIR = Path(os.getenv('DEVCONSOLE_DATA_DIR', '/var/lib/devconsole'))
REGISTRY_FILE = DATA_DIR / 'projects_registry.json'


def load_projects():
    if not REGISTRY_FILE.exists():
        return []

    try:
        return json.loads(REGISTRY_FILE.read_text(encoding='utf-8'))
    except Exception:
        return []


def save_project(project: dict):
    projects = load_projects()

    existing = [p for p in projects if p.get('repo_url') != project.get('repo_url')]
    existing.append(project)

    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

    return existing
