from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.config_store import (
    get_openai_model,
    has_openai_key,
    set_setting,
)
from backend.openai_client import OpenAIConfigurationError, ask_ai

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / 'frontend'

app = FastAPI(title='DevConsole', version='0.1.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

if FRONTEND_DIR.exists():
    app.mount('/assets', StaticFiles(directory=FRONTEND_DIR / 'assets'), name='assets')


class OpenAIConfigRequest(BaseModel):
    api_key: str
    model: str = 'gpt-5'


class PromptTestRequest(BaseModel):
    prompt: str
    task_type: str | None = None


@app.get('/')
async def root():
    index_file = FRONTEND_DIR / 'index.html'
    if index_file.exists():
        return FileResponse(index_file)

    return {
        'project': 'DevConsole',
        'version': '0.1.0',
        'status': 'running',
        'openai_configured': has_openai_key(),
    }


@app.get('/health')
async def health():
    return {
        'status': 'ok',
        'openai_configured': has_openai_key(),
    }


@app.get('/api/system/status')
async def system_status():
    return {
        'project': 'DevConsole',
        'version': '0.1.0',
        'status': 'running',
        'openai_configured': has_openai_key(),
        'openai_model': get_openai_model(),
    }


@app.get('/api/settings/openai')
async def openai_status():
    return {
        'configured': has_openai_key(),
        'model': get_openai_model(),
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


@app.post('/api/settings/openai/test')
async def test_openai_connection():
    try:
        result = await ask_ai('Reply with exactly: DevConsole AI connection OK', 'test')
    except OpenAIConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        'success': True,
        'model': result['model'],
        'answer': result['answer'],
    }
