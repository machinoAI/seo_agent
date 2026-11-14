"""Standard tool contract (design doc §5.3) and automatic result recording.

Every tool in this package must:
  1. take a `ToolRequest` subclass (tool-specific parameters go on the subclass),
  2. return a `ToolOutput` (data + source + warnings),
  3. be decorated with `@recorded_tool("tool_name")`.

The decorator times the call, converts failures into a `ToolResult` with a retry
classification, and saves request + result as JSON under
`OUTPUT_DIR/<site>/<YYYY-MM-DD>/run_<run_id>/` (see `persistence/output_store.py`).
Nothing a tool returns is lost, including failures.

    class CrawlRequest(ToolRequest):
        max_pages: int = 100

    @recorded_tool("crawl_website")
    async def crawl_website(request: CrawlRequest) -> ToolOutput:
        ...
        return ToolOutput(data=pages, source="crawler")
"""

import asyncio
import functools
import inspect
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from seo_agent.config import normalize_site
from seo_agent.persistence.output_store import OutputStore, get_output_store

logger = logging.getLogger(__name__)

_TOOL_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")


class ToolStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"  # usable data, but some of it is missing
    FAILED = "failed"
    SKIPPED = "skipped"  # e.g. integration not configured


class ErrorKind(StrEnum):
    """Failure classes from design doc §9.1. Only TRANSIENT failures are retried."""

    TRANSIENT = "transient"
    PERMANENT = "permanent"
    DATA_QUALITY = "data_quality"


class ToolError(BaseModel):
    code: str
    message: str
    kind: ErrorKind


class ToolFailure(Exception):  # noqa: N818 - reads naturally at raise sites
    """Raise inside a tool to report a classified failure."""

    def __init__(self, code: str, message: str, kind: ErrorKind = ErrorKind.PERMANENT) -> None:
        super().__init__(message)
        self.error = ToolError(code=code, message=message, kind=kind)


class ToolRequest(BaseModel):
    """Base input for every tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    site: str
    website_id: UUID | None = None  # set once website records exist in PostgreSQL

    @field_validator("site")
    @classmethod
    def _normalize_site(cls, value: str) -> str:
        return normalize_site(value)


class ToolOutput(BaseModel):
    """What a tool function returns; the decorator wraps it into a `ToolResult`."""

    data: Any = None
    source: str
    status: ToolStatus = ToolStatus.SUCCESS
    warnings: list[str] = Field(default_factory=list)


class ToolResult(BaseModel):
    """Standard result of every tool call, as stored on disk and returned to agents."""

    tool: str
    status: ToolStatus
    data: Any = None
    source: str
    started_at: datetime
    completed_at: datetime
    warnings: list[str] = Field(default_factory=list)
    error: ToolError | None = None
    output_path: str | None = None  # where this result was recorded

    @computed_field  # type: ignore[prop-decorator]
    @property
    def retryable(self) -> bool:
        return self.error is not None and self.error.kind is ErrorKind.TRANSIENT


ToolFn = Callable[[Any], Awaitable[ToolOutput]] | Callable[[Any], ToolOutput]


def _now() -> datetime:
    return datetime.now(UTC)


def _error_from(exc: Exception, tool: str) -> ToolError:
    if isinstance(exc, ToolFailure):
        return exc.error
    # Unexpected error: keep internals out of the result (it may reach an LLM); log them.
    logger.exception("Unexpected error in tool %s", tool)
    return ToolError(
        code="unexpected_error",
        message=f"{type(exc).__name__} in {tool}",
        kind=ErrorKind.PERMANENT,
    )


def _build_result(
    tool: str, started_at: datetime, output: ToolOutput | None, error: ToolError | None
) -> ToolResult:
    if output is None:
        return ToolResult(
            tool=tool,
            status=ToolStatus.FAILED,
            source=tool,
            started_at=started_at,
            completed_at=_now(),
            error=error,
        )
    return ToolResult(
        tool=tool,
        status=output.status,
        data=output.data,
        source=output.source,
        started_at=started_at,
        completed_at=_now(),
        warnings=output.warnings,
    )


def _record(store: OutputStore, request: ToolRequest, result: ToolResult) -> ToolResult:
    path = store.save(
        site=request.site,
        run_id=request.run_id,
        tool=result.tool,
        request_id=request.request_id,
        status=result.status.value,
        recorded_at=result.completed_at,
        payload={
            "tool": result.tool,
            "request": request.model_dump(mode="json"),
            "result": result.model_dump(mode="json", exclude={"output_path"}),
        },
    )
    return result.model_copy(update={"output_path": str(path)})


def recorded_tool(
    name: str, *, store: OutputStore | None = None
) -> Callable[[ToolFn], Callable[[Any], Any]]:
    """Wrap a sync or async tool so every call returns a recorded `ToolResult`."""
    if not _TOOL_NAME.fullmatch(name):
        raise ValueError(f"Invalid tool name '{name}': use lowercase letters, digits and _")

    def decorator(fn: ToolFn) -> Callable[[Any], Any]:
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(request: ToolRequest) -> ToolResult:
                started_at = _now()
                output: ToolOutput | None = None
                error: ToolError | None = None
                try:
                    output = await fn(request)
                except Exception as exc:  # CancelledError is not an Exception: it propagates
                    error = _error_from(exc, name)
                result = _build_result(name, started_at, output, error)
                return await asyncio.to_thread(
                    _record, store or get_output_store(), request, result
                )

            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(request: ToolRequest) -> ToolResult:
            started_at = _now()
            output: ToolOutput | None = None
            error: ToolError | None = None
            try:
                output = fn(request)  # type: ignore[assignment]
            except Exception as exc:
                error = _error_from(exc, name)
            result = _build_result(name, started_at, output, error)
            return _record(store or get_output_store(), request, result)

        return sync_wrapper

    return decorator
