"""Retry policy (max 2 tries, then move on) and production logging behaviour."""

import contextlib
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from src.observability.logging import bind_context, run_log
from src.tools import http as http_module
from src.tools.crawling import _crawl_page
from src.tools.http import FetchError, SafeHttpClient, _log_url


class FakeResponse:
    def __init__(self, status_code: int, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.headers = httpx.Headers(headers or {}) if hasattr(httpx, "Headers") else (
            headers or {})

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        yield b"<html></html>"


def _client(monkeypatch: pytest.MonkeyPatch, outcomes: list[Any]) -> tuple[SafeHttpClient, list]:
    """Client whose requests return/raise the given outcomes in order; records each try."""
    client = SafeHttpClient(user_agent="test", timeout_seconds=5, max_bytes=10_000,
                            max_attempts=2)
    tries: list[str] = []

    async def public_dns(host: str) -> list[tuple[Any, ...]]:
        return [(None, None, None, "", ("93.184.216.34", 0))]

    @contextlib.asynccontextmanager
    async def stream(method: str, url: str, **_: Any) -> AsyncIterator[FakeResponse]:
        tries.append(url)
        outcome = outcomes[len(tries) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        yield outcome

    monkeypatch.setattr(client, "_getaddrinfo", public_dns)
    monkeypatch.setattr(client._client, "stream", stream)
    monkeypatch.setattr(http_module, "_backoff", lambda attempt, retry_after: 0)
    return client, tries


async def test_network_error_is_tried_twice_then_given_up(monkeypatch: pytest.MonkeyPatch) -> None:
    error = httpx.TransportError("connection reset")
    client, tries = _client(monkeypatch, [error, error, error])

    with pytest.raises(FetchError) as info:
        await client.fetch("https://machinoai.in/jobs")

    assert len(tries) == 2  # one try + one retry, never a third
    assert info.value.code == "network_error"
    assert info.value.transient is True


async def test_503_is_retried_once_then_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    client, tries = _client(monkeypatch, [FakeResponse(503), FakeResponse(503)])

    result = await client.fetch("https://machinoai.in/topic/ai")

    assert len(tries) == 2
    assert result.status_code == 503


async def test_success_on_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    client, tries = _client(monkeypatch, [FakeResponse(429), FakeResponse(200)])

    result = await client.fetch("https://machinoai.in/")

    assert len(tries) == 2
    assert result.status_code == 200


async def test_failed_page_is_recorded_and_crawl_moves_on() -> None:
    class AlwaysFails:
        async def fetch(self, url: str) -> Any:
            raise FetchError("network_error", "ReadTimeout", transient=True)

    client: Any = AlwaysFails()
    page = await _crawl_page(client, "https://machinoai.in/slow", 1, {"machinoai.in"})

    assert page == {"url": "https://machinoai.in/slow", "depth": 1, "status_code": None,
                    "error": "network_error"}


def test_logged_urls_never_include_query_strings() -> None:
    url = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=x&key=SECRET"
    assert _log_url(url) == "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def test_run_log_keeps_only_its_own_run(tmp_path: Path) -> None:
    logger = logging.getLogger("test.run_log")
    logger.setLevel(logging.INFO)
    path = tmp_path / "run.log"

    with run_log(path, "run-a"):
        bind_context(run_id="run-a")
        logger.info("mine")
        bind_context(run_id="run-b")
        logger.info("other run")
    bind_context(run_id="run-a")
    logger.info("after the run")

    text = path.read_text()
    assert "mine" in text
    assert "other run" not in text
    assert "after the run" not in text
