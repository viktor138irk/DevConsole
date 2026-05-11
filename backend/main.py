from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.android_tools import build_android, find_apks, install_latest_apk, list_devices
from backend.config_store import (
    get_openai_model,
    has_openai_key,
    set_setting,
)
from backend.openai_client import OpenAIConfigurationError, ask_ai
from backend.project_analyzer import analyze_github_project
from backend.shell_runner import run_command
from backend.workspace_api import router as workspace_router

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / 'frontend'

app = FastAPI(title='DevConsole', version='0.2.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(workspace_router)

if FRONTEND_DIR.exists():
    app.mount('/assets', StaticFiles(directory=FRONTEND_DIR / 'assets'), name='assets')


class OpenAIConfigRequest(BaseModel):
    api_key: str
    model: str = 'gpt-5'


class PromptTestRequest(BaseModel):
    prompt: str
    task_type: str | None = None


class ProjectAnalyzeRequest(BaseModel):
    repo_url: str


class WorkspaceRequest(BaseModel):
    workspace: str
    device: str | None = None


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
        'version': '0.2.0',
        'openai_configured': has_openai_key(),
    }


@app.get('/api/system/status')
async def system_status():
    return {
        'project': 'DevConsole',
        'version': '0.2.0',
        'status': 'running',
        'openai_configured': has_openai_key(),
        'openai_model': get_openai_model(),
    }


@app.post('/api/settings/openai')
async def save_openai_settings(payload: OpenAIConfigRequest):
    api_key = payload.api_key.strip()
    model = payload.model.strip() or 'gpt-5'

    if not api_key:
        raise HTTPException(status_code=400, detail='API key is empty')

    set_setting('OPENAI_API_KEY', api_key)
    set_setting('OPENAI_MODEL', model)

    return {
        'success': True,
        'message': 'OpenAI settings saved',
    }


@app.post('/api/prompts/test')
async def test_prompt(payload: PromptTestRequest):
    prompt = payload.prompt.strip()

    if not prompt:
        raise HTTPException(status_code=400, detail='Prompt is empty')

    try:
        result = await ask_ai(prompt, payload.task_type)
    except OpenAIConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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

    analysis = analyze_github_project(repo_url)

    return {
        'success': True,
        'analysis': analysis.to_dict(),
    }


@app.post('/api/projects/install-dependencies')
async def install_dependencies(payload: ProjectAnalyzeRequest):
    analysis = analyze_github_project(payload.repo_url.strip())

    outputs = []

    for step in analysis.dependency_steps:
        outputs.append(run_command(step.command, step.cwd, 1800))

    return {
        'success': True,
        'analysis': analysis.to_dict(),
        'outputs': outputs,
    }


@app.post('/api/android/devices')
async def android_devices():
    return list_devices()


@app.post('/api/android/build')
async def android_build(payload: WorkspaceRequest):
    result = build_android(payload.workspace)
    apks = find_apks(payload.workspace)

    return {
        'success': result['returncode'] == 0,
        'result': result,
        'apks': apks,
    }


@app.post('/api/android/install-latest')
async def android_install_latest(payload: WorkspaceRequest):
    result = install_latest_apk(payload.workspace)

    return {
        'success': result['returncode'] == 0,
        'result': result,
        'device': payload.device,
    }
