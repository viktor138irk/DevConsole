from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.config_store import (
    get_openai_model,
    has_openai_key,
    set_setting,
)

app = FastAPI(title='DevConsole', version='0.1.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


class OpenAIConfigRequest(BaseModel):
    api_key: str
    model: str = 'gpt-5'


@app.get('/')
async def root():
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


@app.get('/api/settings/openai')
async def openai_status():
    return {
        'configured': has_openai_key(),
        'model': get_openai_model(),
    }


@app.post('/api/settings/openai')
async def save_openai_settings(payload: OpenAIConfigRequest):
    set_setting('OPENAI_API_KEY', payload.api_key.strip())
    set_setting('OPENAI_MODEL', payload.model.strip())

    return {
        'success': True,
        'message': 'OpenAI settings saved',
    }
