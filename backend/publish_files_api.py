from pathlib import Path
import shutil

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.runtime_logs import add_log

router = APIRouter(prefix='/api/publish-files', tags=['publish-files'])

ALLOWED_TARGETS: dict[str, dict] = {
    'firebase_android': {
        'label': 'Firebase Android config',
        'filename': 'google-services.json',
        'relative_path': 'android/app/google-services.json',
        'extensions': {'.json'},
    },
    'firebase_ios': {
        'label': 'Firebase iOS config',
        'filename': 'GoogleService-Info.plist',
        'relative_path': 'ios/Runner/GoogleService-Info.plist',
        'extensions': {'.plist'},
    },
    'android_release_key': {
        'label': 'Android release keystore',
        'filename': 'release-key.jks',
        'relative_path': 'android/app/release-key.jks',
        'extensions': {'.jks', '.keystore'},
    },
    'android_key_properties': {
        'label': 'Android key properties',
        'filename': 'key.properties',
        'relative_path': 'android/key.properties',
        'extensions': {'.properties'},
    },
    'play_store_service_account': {
        'label': 'Google Play service account',
        'filename': 'play-service-account.json',
        'relative_path': 'android/play-service-account.json',
        'extensions': {'.json'},
    },
    'publish_extra': {
        'label': 'Extra publish file',
        'filename': None,
        'relative_path': 'publish-files',
        'extensions': {'.json', '.plist', '.jks', '.keystore', '.properties', '.pem', '.p12', '.mobileprovision'},
        'directory': True,
    },
}


def _safe_workspace(workspace: str) -> Path:
    path = Path(workspace).resolve()
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=400, detail='Workspace path does not exist')
    return path


def _safe_destination(workspace: Path, relative_path: str) -> Path:
    destination = (workspace / relative_path).resolve()
    try:
        destination.relative_to(workspace)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='Invalid destination path') from exc
    return destination


@router.get('/targets')
async def publish_file_targets():
    return {
        'success': True,
        'targets': [
            {
                'id': target_id,
                'label': config['label'],
                'filename': config.get('filename'),
                'relative_path': config['relative_path'],
                'extensions': sorted(config['extensions']),
                'directory': bool(config.get('directory')),
            }
            for target_id, config in ALLOWED_TARGETS.items()
        ],
    }


@router.post('/upload')
async def upload_publish_file(
    workspace: str = Form(...),
    target: str = Form(...),
    file: UploadFile = File(...),
):
    config = ALLOWED_TARGETS.get(target)
    if not config:
        raise HTTPException(status_code=400, detail='Unknown publish file target')

    source_name = Path(file.filename or '').name
    source_ext = Path(source_name).suffix.lower()

    if source_ext not in config['extensions']:
        raise HTTPException(
            status_code=400,
            detail=f'Unsupported file extension for {config["label"]}',
        )

    workspace_path = _safe_workspace(workspace)

    if config.get('directory'):
        directory = _safe_destination(workspace_path, config['relative_path'])
        directory.mkdir(parents=True, exist_ok=True)
        destination = (directory / source_name).resolve()
        try:
            destination.relative_to(directory)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail='Invalid upload filename') from exc
    else:
        destination = _safe_destination(workspace_path, config['relative_path'])
        destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open('wb') as output:
        shutil.copyfileobj(file.file, output)

    add_log(f'Publish file uploaded: {config["label"]} -> {destination}')

    return {
        'success': True,
        'target': target,
        'label': config['label'],
        'path': destination.as_posix(),
        'relative_path': destination.relative_to(workspace_path).as_posix(),
    }
