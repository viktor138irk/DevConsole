from pathlib import Path
import os

DATA_DIR = Path(os.getenv('DEVCONSOLE_DATA_DIR', '/var/lib/devconsole'))
PROJECTS_DIR = DATA_DIR / 'projects'


class WorkspaceSecurityError(Exception):
    pass


def ensure_workspace(path: str) -> Path:
    workspace = Path(path).resolve()

    try:
        workspace.relative_to(PROJECTS_DIR.resolve())
    except ValueError as exc:
        raise WorkspaceSecurityError(
            'Workspace path is outside projects directory'
        ) from exc

    return workspace


def build_tree(path: str, max_depth: int = 3):
    workspace = ensure_workspace(path)

    def scan(directory: Path, depth: int = 0):
        if depth > max_depth:
            return []

        result = []

        for item in sorted(directory.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
            if item.name.startswith('.'):
                continue

            node = {
                'name': item.name,
                'path': item.as_posix(),
                'type': 'directory' if item.is_dir() else 'file',
            }

            if item.is_dir():
                node['children'] = scan(item, depth + 1)

            result.append(node)

        return result

    return scan(workspace)


def read_file(path: str):
    file_path = ensure_workspace(path)

    if file_path.is_dir():
        raise WorkspaceSecurityError('Cannot read directory')

    return file_path.read_text(encoding='utf-8', errors='ignore')


def save_file(path: str, content: str):
    file_path = ensure_workspace(path)

    if file_path.is_dir():
        raise WorkspaceSecurityError('Cannot save directory')

    file_path.write_text(content, encoding='utf-8')

    return {
        'success': True,
        'path': file_path.as_posix(),
        'size': len(content),
    }
