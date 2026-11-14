"""Structured logging for the whole application.

Where logs go:
  * console (stderr): readable lines locally, JSON when LOG_JSON=true (production)
  * LOG_FILE (default data/logs/seo_agent.log): JSON lines, rotated at 10 MB, 5 files kept
  * <run folder>/run.log: JSON lines of one run only (see `run_log`)

Every line has timestamp, level, logger and event, plus the context bound with
`bind_context` (run_id, site, step) and the event's own fields (tool, url, attempt, …).
Values under sensitive keys (api_key, token, password, authorization, …) are redacted,
and HTTP logs never include query strings.
"""

import logging
import logging.handlers
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

LOG_FILE_MAX_BYTES = 10_000_000
LOG_FILE_BACKUPS = 5

# Matches e.g. "password", "access_token", "anthropic_api_key" — but not "tokens_used".
_SENSITIVE_KEY = re.compile(
    r"(?:.*_)?(password|passwd|secret|token|api_key|apikey|authorization|cookie|dsn)", re.I
)
_REDACTED = "***REDACTED***"


def _redact_sensitive(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    for key in event_dict:
        if _SENSITIVE_KEY.fullmatch(key):
            event_dict[key] = _REDACTED
    return event_dict


_SHARED: list[Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    _redact_sensitive,
]


def _formatter(json_output: bool) -> logging.Formatter:
    renderer: list[Processor] = (
        [structlog.processors.format_exc_info, structlog.processors.JSONRenderer()]
        if json_output
        else [structlog.dev.ConsoleRenderer()]
    )
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_SHARED,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, *renderer],
    )


def configure_logging(
    level: str = "INFO", json_output: bool = False, log_file: Path | None = None
) -> None:
    """Configure structlog and route all stdlib logging (uvicorn, httpx, …) through it."""
    structlog.configure(
        processors=[*_SHARED, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(_formatter(json_output))
    handlers: list[logging.Handler] = [console]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        rotating = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=LOG_FILE_MAX_BYTES, backupCount=LOG_FILE_BACKUPS, encoding="utf-8"
        )
        rotating.setFormatter(_formatter(json_output=True))
        handlers.append(rotating)

    root = logging.getLogger()
    root.handlers = handlers
    root.setLevel(level.upper())
    # Send uvicorn's own loggers through the same handlers instead of its defaults.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
    # Third-party request logs are noisy at INFO (one line per crawled URL).
    for noisy in ("httpx", "httpcore", "aiosqlite"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


class _RunFilter(logging.Filter):
    """Keep only records logged while `run_id` is bound (concurrent API runs stay apart)."""

    def __init__(self, run_id: str) -> None:
        super().__init__()
        self.run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:
        return structlog.contextvars.get_contextvars().get("run_id") == self.run_id


@contextmanager
def run_log(path: Path, run_id: str) -> Iterator[Path]:
    """Also write this run's log lines (JSON) to `path` while the block runs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(_formatter(json_output=True))
    handler.addFilter(_RunFilter(run_id))
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield path
    finally:
        root.removeHandler(handler)
        handler.close()


def get_logger(name: str | None = None) -> Any:
    return structlog.stdlib.get_logger(name)


def bind_context(**values: Any) -> None:
    """Attach identifiers to all subsequent log lines in this context (task)."""
    structlog.contextvars.bind_contextvars(**values)
