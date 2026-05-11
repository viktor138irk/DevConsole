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


def save_projects(projects: list[dict]) -> list[dict]:
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(
        json.dumps(projects, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )
    return projects


def save_project(project: dict):
    projects = load_projects()
    existing_project = None

    for item in projects:
        if item.get('repo_url') == project.get('repo_url') or item.get('workspace') == project.get('workspace'):
            existing_project = item
            break

    if existing_project:
        merged = {**existing_project, **project}
        projects = [merged if p is existing_project else p for p in projects]
    else:
        projects.append(project)

    return save_projects(projects)


def find_project_by_workspace(workspace: str) -> dict | None:
    for project in load_projects():
        if project.get('workspace') == workspace:
            return project
    return None


def find_project_by_repo(repo_url: str) -> dict | None:
    for project in load_projects():
        if project.get('repo_url') == repo_url:
            return project
    return None


def update_project_settings(workspace: str, settings: dict) -> dict | None:
    projects = load_projects()
    updated = None

    for index, project in enumerate(projects):
        if project.get('workspace') == workspace:
            merged = {**project, **settings}
            projects[index] = merged
            updated = merged
            break

    if updated is None:
        return None

    save_projects(projects)
    return updated
