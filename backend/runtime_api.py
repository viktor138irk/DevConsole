from fastapi import APIRouter

from backend.runtime_logs import get_logs, add_log

router = APIRouter(prefix='/api/runtime', tags=['runtime'])


@router.get('/logs')
async def runtime_logs():
    return {
        'success': True,
        'logs': get_logs(),
    }


@router.post('/event')
async def runtime_event(payload: dict):
    message = payload.get('message', 'unknown runtime event')

    add_log(message)

    return {
        'success': True,
        'message': message,
    }
