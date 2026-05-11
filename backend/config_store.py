import os
import sqlite3
from pathlib import Path
from typing import Optional

DATA_DIR = Path(os.getenv('DEVCONSOLE_DATA_DIR', '/var/lib/devconsole'))
DB_PATH = DATA_DIR / 'devconsole.db'


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )
    conn.commit()
    return conn


def set_setting(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            '''
            INSERT INTO settings(key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            ''',
            (key, value),
        )
        conn.commit()


def get_setting(key: str) -> Optional[str]:
    with _connect() as conn:
        row = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
        return row['value'] if row else None


def has_openai_key() -> bool:
    return bool(get_openai_key())


def get_openai_key() -> Optional[str]:
    return get_setting('OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY') or None


def get_openai_model() -> str:
    return get_setting('OPENAI_MODEL') or os.getenv('OPENAI_MODEL') or 'gpt-5'


def get_github_username() -> str:
    return get_setting('GITHUB_USERNAME') or os.getenv('GITHUB_USERNAME') or ''


def get_github_token() -> Optional[str]:
    return get_setting('GITHUB_TOKEN') or os.getenv('GITHUB_TOKEN') or None


def has_github_token() -> bool:
    return bool(get_github_token())


def get_github_public_config() -> dict:
    return {
        'username': get_github_username(),
        'token_set': has_github_token(),
    }


def get_proxy_config() -> dict:
    return {
        'enabled': (get_setting('PROXY_ENABLED') or os.getenv('PROXY_ENABLED') or '0') == '1',
        'host': get_setting('PROXY_HOST') or os.getenv('PROXY_HOST') or '',
        'port': get_setting('PROXY_PORT') or os.getenv('PROXY_PORT') or '',
        'username': get_setting('PROXY_USERNAME') or os.getenv('PROXY_USERNAME') or '',
        'password': get_setting('PROXY_PASSWORD') or os.getenv('PROXY_PASSWORD') or '',
    }


def get_proxy_public_config() -> dict:
    proxy = get_proxy_config()
    return {
        'enabled': proxy['enabled'],
        'host': proxy['host'],
        'port': proxy['port'],
        'username': proxy['username'],
        'password_set': bool(proxy['password']),
    }


def build_proxy_url() -> Optional[str]:
    proxy = get_proxy_config()

    if not proxy['enabled']:
        return None

    host = proxy['host'].strip()
    port = str(proxy['port']).strip()

    if not host or not port:
        return None

    username = proxy['username'].strip()
    password = proxy['password']

    auth = ''
    if username:
        auth = username
        if password:
            auth += f':{password}'
        auth += '@'

    return f'socks5://{auth}{host}:{port}'
