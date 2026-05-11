from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.file_workspace import (
    WorkspaceSecurityError,
    build_tree,
    read_file,
    save_file,
)

router = APIRouter(prefix='/api/files', tags=['workspace'])


class FilePathRequest(BaseModel):
    path: str


class SaveFileRequest(BaseModel):
    path: str
    content: str


@router.post('/tree')
async def workspace_tree(payload: FilePathRequest):
    try:
        tree = build_tree(payload.path)
    except WorkspaceSecurityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        'success': True,
        'tree': tree,
    }


@router.post('/read')
async def workspace_read(payload: FilePathRequest):
    try:
        content = read_file(payload.path)
    except WorkspaceSecurityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        'success': True,
        'content': content,
    }


@router.post('/save')
async def workspace_save(payload: SaveFileRequest):
    try:
        result = save_file(payload.path, payload.content)
    except WorkspaceSecurityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return result
