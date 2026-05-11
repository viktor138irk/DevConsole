from fastapi import APIRouter
from pydantic import BaseModel

from backend.projects_registry import load_projects, save_project

router = APIRouter(prefix='/api/projects', tags=['projects'])


class ProjectRegistryRequest(BaseModel):
    name: str
    repo_url: str
    workspace: str
    stack: str | None = None


@router.get('/list')
async def projects_list():
    return {
        'success': True,
        'projects': load_projects(),
    }


@router.post('/register')
async def register_project(payload: ProjectRegistryRequest):
    projects = save_project({
        'name': payload.name,
        'repo_url': payload.repo_url,
        'workspace': payload.workspace,
        'stack': payload.stack,
    })

    return {
        'success': True,
        'projects': projects,
    }
