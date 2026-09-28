"""JSON log lines for production (`LOG_FORMAT=json`, the default with `DJANGO_ENV=production`).

One object per line with `time`, `level`, `logger`, `message`, the request id of the current request (the
same `X-Request-ID` nginx logs and Django echoes), the exception (`exc_info`) and any `extra={...}` fields.
Loaded by `logging.config` before the Django apps, so it must not import models.
"""

import json
import logging
from datetime import UTC, datetime

from apps.core.context import current_request_id

# Attributes every LogRecord has; anything else on the record came from `extra=` and is added to the line.
_RESERVED = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = current_request_id()
        if request_id:
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        for key, value in vars(record).items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)
