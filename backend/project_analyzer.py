import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.parse import urlparse

DATA_DIR = Path(os.getenv('DEVCONSOLE_DATA_DIR', '/var/lib/devconsole'))
PROJECTS_DIR = DATA_DIR / 'projects'


@dataclass
class DependencyStep:
    title: str
    command: str
    cwd: str
    safe: bool = True


@dataclass
class ProjectAnalysis:
    repo_url: str
    workspace: str
    detected_stack: list[str]
    files_found: list[str]
    dependency_steps: list[DependencyStep]
    notes: list[str]

    def to_dict(self) -> dict:
        data = asdict(self)
        data['dependency_steps'] = [asdict(step) for step in self.dependency_steps]
        return data


def _slug_from_repo_url(repo_url: str) -> str:
    parsed = urlparse(repo_url)
    path = parsed.path.strip('/').replace('.git', '')
    slug = re.sub(r'[^a-zA-Z0-9_.-]+', '-', path)
    return slug or 'project'


def clone_or_update_project(repo_url: str) -> Path:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = _slug_from_repo_url(repo_url)
    workspace = PROJECTS_DIR / slug

    if (workspace / '.git').exists():
        subprocess.run(['git', '-C', str(workspace), 'fetch', '--all'], check=True)
        subprocess.run(['git', '-C', str(workspace), 'pull', '--ff-only'], check=False)
    else:
        if workspace.exists():
            shutil.rmtree(workspace)
        subprocess.run(['git', 'clone', repo_url, str(workspace)], check=True)

    return workspace


def _exists(root: Path, relative: str) -> bool:
    return (root / relative).exists()


def _find_files(root: Path, names: set[str], limit: int = 80) -> list[Path]:
    result: list[Path] = []
    ignored_dirs = {'.git', 'node_modules', 'vendor', '.venv', 'venv', 'build', 'dist', '.dart_tool', '.gradle'}

    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        for file in files:
            if file in names:
                result.append(Path(current) / file)
                if len(result) >= limit:
                    return result
    return result


def analyze_workspace(repo_url: str, workspace: Path) -> ProjectAnalysis:
    detected_stack: list[str] = []
    files_found: list[str] = []
    steps: list[DependencyStep] = []
    notes: list[str] = []

    marker_files = _find_files(
        workspace,
        {
            'package.json', 'requirements.txt', 'pyproject.toml', 'Pipfile',
            'composer.json', 'pubspec.yaml', 'build.gradle', 'build.gradle.kts',
            'settings.gradle', 'settings.gradle.kts', 'Dockerfile', 'docker-compose.yml',
            'docker-compose.yaml', 'go.mod', 'Cargo.toml'
        }
    )

    for marker in marker_files:
        relative = marker.relative_to(workspace).as_posix()
        files_found.append(relative)
        cwd = marker.parent.as_posix()

        if marker.name == 'package.json':
            detected_stack.append('Node.js')
            package_lock = marker.parent / 'package-lock.json'
            yarn_lock = marker.parent / 'yarn.lock'
            pnpm_lock = marker.parent / 'pnpm-lock.yaml'
            if pnpm_lock.exists():
                steps.append(DependencyStep('Install Node dependencies with pnpm', 'corepack enable && pnpm install', cwd))
            elif yarn_lock.exists():
                steps.append(DependencyStep('Install Node dependencies with yarn', 'corepack enable && yarn install', cwd))
            elif package_lock.exists():
                steps.append(DependencyStep('Install Node dependencies with npm ci', 'npm ci', cwd))
            else:
                steps.append(DependencyStep('Install Node dependencies with npm', 'npm install', cwd))

        elif marker.name == 'requirements.txt':
            detected_stack.append('Python')
            steps.append(DependencyStep('Create Python virtualenv', 'python3 -m venv .venv', cwd))
            steps.append(DependencyStep('Install Python requirements', '.venv/bin/pip install --upgrade pip && .venv/bin/pip install -r requirements.txt', cwd))

        elif marker.name == 'pyproject.toml':
            detected_stack.append('Python')
            steps.append(DependencyStep('Install Python project', 'python3 -m venv .venv && .venv/bin/pip install --upgrade pip && .venv/bin/pip install -e .', cwd))

        elif marker.name == 'composer.json':
            detected_stack.append('PHP/Composer')
            steps.append(DependencyStep('Install PHP Composer dependencies', 'composer install', cwd))

        elif marker.name == 'pubspec.yaml':
            detected_stack.append('Flutter/Dart')
            steps.append(DependencyStep('Install Flutter/Dart dependencies', 'flutter pub get', cwd))

        elif marker.name in {'build.gradle', 'build.gradle.kts'}:
            detected_stack.append('Gradle/Android')
            gradlew = marker.parent / 'gradlew'
            command = './gradlew tasks' if gradlew.exists() else 'gradle tasks'
            steps.append(DependencyStep('Prepare Gradle project', command, cwd))

        elif marker.name in {'docker-compose.yml', 'docker-compose.yaml'}:
            detected_stack.append('Docker Compose')
            steps.append(DependencyStep('Pull Docker Compose images', 'docker compose pull', cwd))

        elif marker.name == 'Dockerfile':
            detected_stack.append('Docker')
            image_name = _slug_from_repo_url(repo_url).replace('/', '-').lower()
            steps.append(DependencyStep('Build Docker image', f'docker build -t {image_name}:dev .', cwd))

        elif marker.name == 'go.mod':
            detected_stack.append('Go')
            steps.append(DependencyStep('Download Go modules', 'go mod download', cwd))

        elif marker.name == 'Cargo.toml':
            detected_stack.append('Rust')
            steps.append(DependencyStep('Fetch Cargo dependencies', 'cargo fetch', cwd))

    if not files_found:
        notes.append('No known dependency manifest found. AI/manual analysis required.')

    unique_stack = list(dict.fromkeys(detected_stack))
    unique_files = list(dict.fromkeys(files_found))

    return ProjectAnalysis(
        repo_url=repo_url,
        workspace=workspace.as_posix(),
        detected_stack=unique_stack,
        files_found=unique_files,
        dependency_steps=steps,
        notes=notes,
    )


def analyze_github_project(repo_url: str) -> ProjectAnalysis:
    workspace = clone_or_update_project(repo_url)
    return analyze_workspace(repo_url, workspace)
