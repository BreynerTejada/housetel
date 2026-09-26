"""Console logging (settings.LOGGING): every record reaches the console exactly once.

Django's default config gives the `django` logger its own console handler (DEBUG only) while our root logger
has another one, so each `django.request` warning (4xx/5xx, including 500 tracebacks) was printed twice.
"""

import logging

import pytest


def console_handlers_for(logger_name: str) -> list[logging.Handler]:
    """Plain StreamHandlers a record from `logger_name` passes through (pytest's capture handlers are
    StreamHandler subclasses and are ignored)."""
    handlers = []
    logger = logging.getLogger(logger_name)
    while logger is not None:
        handlers += [handler for handler in logger.handlers if type(handler) is logging.StreamHandler]
        if not logger.propagate:
            break
        logger = logger.parent
    return handlers


@pytest.mark.parametrize("name", ["django.request", "django.security.csrf", "housetel.signals", "apps.core"])
def test_each_record_is_written_to_the_console_once(name):
    assert len(console_handlers_for(name)) == 1
