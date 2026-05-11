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
