from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.projects_registry import (
    find_project_by_workspace,
    load_projects,
    save_project,
    update_project_settings,
)
from backend.pubspec_tools import read_pubspec_version

router = APIRouter(prefix='/api/projects', tags=['projects'])


class ProjectRegistryRequest(BaseModel):
    name: str
    repo_url: str
    workspace: str
    stack: str | None = None


class ProjectSettingsRequest(BaseModel):
    workspace: str
    settings: dict


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


@router.get('/settings')
async def project_settings(workspace: str):
    project = find_project_by_workspace(workspace)
    if not project:
        raise HTTPException(status_code=404, detail='Project not found')

    return {
        'success': True,
        'project': project,
    }


@router.get('/pubspec-version')
async def project_pubspec_version(workspace: str):
    project = find_project_by_workspace(workspace)
    if not project:
        raise HTTPException(status_code=404, detail='Project not found')

    result = read_pubspec_version(workspace)
    if not result:
        raise HTTPException(status_code=404, detail='pubspec.yaml version not found')

    return result


@router.post('/settings')
async def save_project_settings(payload: ProjectSettingsRequest):
    project = update_project_settings(payload.workspace, payload.settings)
    if not project:
        raise HTTPException(status_code=404, detail='Project not found')

    return {
        'success': True,
        'project': project,
    }
