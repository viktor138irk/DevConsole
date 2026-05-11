from enum import Enum

from backend.config_store import get_setting


class TaskType(str, Enum):
    GENERAL = 'general'
    CODING = 'coding'
    SERVER = 'server'
    ANDROID = 'android'
    TEST = 'test'
    CHEAP = 'cheap'


DEFAULT_MODELS = {
    'default': 'gpt-5',
    'coding': 'gpt-5',
    'cheap': 'gpt-5-mini',
}


def get_model_profile() -> dict:
    return {
        'default': get_setting('OPENAI_MODEL_DEFAULT') or get_setting('OPENAI_MODEL') or DEFAULT_MODELS['default'],
        'coding': get_setting('OPENAI_MODEL_CODING') or DEFAULT_MODELS['coding'],
        'cheap': get_setting('OPENAI_MODEL_CHEAP') or DEFAULT_MODELS['cheap'],
    }


def choose_model(task_type: str | None = None, prompt: str = '') -> str:
    profile = get_model_profile()
    normalized_type = (task_type or '').strip().lower()
    text = prompt.lower()

    if normalized_type in {TaskType.CODING, TaskType.SERVER, TaskType.ANDROID, TaskType.TEST}:
        return profile['coding']

    if normalized_type == TaskType.CHEAP:
        return profile['cheap']

    coding_markers = [
        'код', 'ошибка', 'traceback', 'exception', 'pytest', 'php', 'python', 'fastapi',
        'android', 'flutter', 'gradle', 'apk', 'server', 'docker', 'nginx', 'systemd',
        'build', 'test', 'fix', 'refactor', 'repository', 'git', 'api', 'sql'
    ]
    cheap_markers = [
        'кратко', 'название', 'заголовок', 'переведи', 'summary', 'classify'
    ]

    if any(marker in text for marker in coding_markers):
        return profile['coding']

    if len(text) < 500 and any(marker in text for marker in cheap_markers):
        return profile['cheap']

    return profile['default']
