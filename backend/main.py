from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.android_tools import build_android, find_apks, install_latest_apk, list_devices
from backend.config_store import (
    get_github_public_config,
    get_openai_model,
    has_openai_key,
    set_setting,
)
from backend.openai_client import OpenAIConfigurationError, ask_ai
from backend.project_analyzer import analyze_github_project
from backend.projects_api import router as projects_router
from backend.runtime_api import router as runtime_router
from backend.runtime_logs import add_log
from backend.shell_runner import run_command
from backend.workspace_api import router as workspace_router

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / 'frontend'

app = FastAPI(title='DevConsole', version='0.3.1')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(workspace_router)
app.include_router(projects_router)
app.include_router(runtime_router)

if FRONTEND_DIR.exists():
    app.mount('/assets', StaticFiles(directory=FRONTEND_DIR / 'assets'), name='assets')


class OpenAIConfigRequest(BaseModel):
    api_key: str
    model: str = 'gpt-5'


class GitHubConfigRequest(BaseModel):
    username: str
    token: str


class PromptTestRequest(BaseModel):
    prompt: str
    task_type: str | None = None


class ProjectAnalyzeRequest(BaseModel):
    repo_url: str


class WorkspaceRequest(BaseModel):
    workspace: str
    device: str | None = None


def _safe_workspace_file(workspace: str, file_path: str) -> Path:
    root = Path(workspace).resolve()
    target = Path(unquote(file_path)).resolve()
    if not root.exists():
        raise HTTPException(status_code=400, detail='Workspace path does not exist')
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail='File not found')
    if root not in target.parents and target != root:
        raise HTTPException(status_code=403, detail='File is outside workspace')
    if target.suffix.lower() != '.apk':
        raise HTTPException(status_code=403, detail='Only APK files are allowed')
    return target


def _apk_meta(path: str, workspace: str) -> dict:
    apk = Path(path).resolve()
    stat = apk.stat()
    return {
        'name': apk.name,
        'path': apk.as_posix(),
        'relative_path': apk.relative_to(Path(workspace).resolve()).as_posix(),
        'size_bytes': stat.st_size,
        'mtime': stat.st_mtime,
        'open_url': f'/api/android/apk/open?workspace={workspace}&path={apk.as_posix()}',
        'download_url': f'/api/android/apk/download?workspace={workspace}&path={apk.as_posix()}',
    }


@app.get('/')
async def root():
    return FileResponse(FRONTEND_DIR / 'index.html')


@app.get('/workspace.js')
async def workspace_js():
    return FileResponse(FRONTEND_DIR / 'workspace.js')


@app.get('/health')
async def health():
    return {
        'status': 'ok',
        'version': '0.3.1',
        'openai_configured': has_openai_key(),
    }


@app.get('/api/system/status')
async def system_status():
    return {
        'project': 'DevConsole',
        'version': '0.3.1',
        'status': 'running',
        'openai_configured': has_openai_key(),
        'openai_model': get_openai_model(),
        'github': get_github_public_config(),
    }


@app.post('/api/settings/openai')
async def save_openai_settings(payload: OpenAIConfigRequest):
    api_key = payload.api_key.strip()
    model = payload.model.strip() or 'gpt-5'

    if not api_key:
        raise HTTPException(status_code=400, detail='API key is empty')

    set_setting('OPENAI_API_KEY', api_key)
    set_setting('OPENAI_MODEL', model)

    add_log('OpenAI settings updated')

    return {
        'success': True,
        'message': 'OpenAI settings saved',
    }


@app.post('/api/settings/github')
async def save_github_settings(payload: GitHubConfigRequest):
    username = payload.username.strip()
    token = payload.token.strip()

    set_setting('GITHUB_USERNAME', username)

    if token:
        set_setting('GITHUB_TOKEN', token)

    add_log('GitHub credentials updated')

    return {
        'success': True,
        'github': get_github_public_config(),
    }


@app.post('/api/prompts/test')
async def test_prompt(payload: PromptTestRequest):
    prompt = payload.prompt.strip()

    if not prompt:
        raise HTTPException(status_code=400, detail='Prompt is empty')

    add_log('AI task started')

    try:
        result = await ask_ai(prompt, payload.task_type)
    except OpenAIConfigurationError as exc:
        add_log(f'AI configuration error: {exc}')
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    add_log('AI task completed')

    return {
        'success': True,
        'model': result['model'],
        'answer': result['answer'],
    }


@app.post('/api/projects/analyze')
async def analyze_project(payload: ProjectAnalyzeRequest):
    repo_url = payload.repo_url.strip()

    if not repo_url.startswith('http'):
        raise HTTPException(status_code=400, detail='Invalid repository URL')

    add_log(f'Analyzing project: {repo_url}')

    analysis = analyze_github_project(repo_url)

    add_log(f'Project analyzed: {analysis.detected_stack}')

    return {
        'success': True,
        'analysis': analysis.to_dict(),
    }


@app.post('/api/projects/install-dependencies')
async def install_dependencies(payload: ProjectAnalyzeRequest):
    analysis = analyze_github_project(payload.repo_url.strip())

    outputs = []

    add_log('Installing dependencies')

    for step in analysis.dependency_steps:
        add_log(f'Running: {step.command}')
        outputs.append(run_command(step.command, step.cwd, 1800))

    add_log('Dependencies installed')

    return {
        'success': True,
        'analysis': analysis.to_dict(),
        'outputs': outputs,
    }


@app.post('/api/android/devices')
async def android_devices():
    add_log('Refreshing Android devices')
    return list_devices()


@app.post('/api/android/build')
async def android_build(payload: WorkspaceRequest):
    add_log(f'Android build started: {payload.workspace}')

    result = build_android(payload.workspace)
    apks = find_apks(payload.workspace)

    add_log('Android build completed')

    return {
        'success': result['returncode'] == 0,
        'result': result,
        'apks': apks,
    }


@app.get('/api/android/apks')
async def android_apks(workspace: str):
    root = Path(workspace).resolve()
    if not root.exists():
        raise HTTPException(status_code=400, detail='Workspace path does not exist')
    flutter_apk_dir = root / 'build' / 'app' / 'outputs' / 'flutter-apk'
    apks = []
    if flutter_apk_dir.exists():
        apks = sorted(flutter_apk_dir.glob('*.apk'), key=lambda p: p.stat().st_mtime, reverse=True)
    return {
        'success': True,
        'directory': flutter_apk_dir.as_posix(),
        'apks': [_apk_meta(apk.as_posix(), root.as_posix()) for apk in apks],
    }


@app.get('/api/android/apk/open')
async def android_open_apk(workspace: str, path: str):
    apk = _safe_workspace_file(workspace, path)
    return FileResponse(apk, media_type='application/vnd.android.package-archive', filename=apk.name)


@app.get('/api/android/apk/download')
async def android_download_apk(workspace: str, path: str):
    apk = _safe_workspace_file(workspace, path)
    return FileResponse(apk, media_type='application/vnd.android.package-archive', filename=apk.name, headers={'Content-Disposition': f'attachment; filename="{apk.name}"'})


@app.post('/api/android/install-latest')
async def android_install_latest(payload: WorkspaceRequest):
    add_log(f'Installing APK to device: {payload.device}')

    result = install_latest_apk(payload.workspace)

    add_log('APK installation completed')

    return {
        'success': result['returncode'] == 0,
        'result': result,
        'device': payload.device,
    }
