"""Structured logging.

JSON output in staging/production (LOG_JSON=true), readable console output locally.
Workflow identifiers (site, run_id, agent, tool) are attached with `bind_context(...)`
and appear on every log line. Values under sensitive keys are redacted.
"""

import logging
import re
import sys
from typing import Any

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

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


def configure_logging(level: str = "INFO", json_output: bool = False) -> None:
    """Configure structlog and route stdlib logging (uvicorn, httpx, ...) through it."""
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _redact_sensitive,
    ]
    output: list[Processor] = (
        [structlog.processors.format_exc_info, structlog.processors.JSONRenderer()]
        if json_output
        else [structlog.dev.ConsoleRenderer()]
    )
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, *output],
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # Third-party request logs are noisy at INFO (one line per crawled URL).
    for noisy in ("httpx", "httpcore", "aiosqlite"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> Any:
    return structlog.stdlib.get_logger(name)


def bind_context(**values: Any) -> None:
    """Attach identifiers to all subsequent log lines in this context (task)."""
    structlog.contextvars.bind_contextvars(**values)
