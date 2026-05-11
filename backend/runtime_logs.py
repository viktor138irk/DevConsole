from datetime import datetime
from collections import deque

MAX_LOGS = 500

runtime_logs = deque(maxlen=MAX_LOGS)


def add_log(message: str):
    runtime_logs.appendleft({
        'timestamp': datetime.utcnow().isoformat(),
        'message': message,
    })


def get_logs(limit: int = 100):
    return list(runtime_logs)[:limit]
