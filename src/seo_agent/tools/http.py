"""Shared HTTP client for every tool that touches the network.

Safety (design doc §12.1):
  * only http/https on standard ports,
  * every hostname is resolved and must map to public addresses only (blocks loopback,
    private, link-local, reserved and other non-global ranges),
  * redirects are followed manually and every hop is re-validated,
  * an optional host allow-list keeps the crawler inside the target site,
  * response bodies are size-capped and every request times out.
Reliability (§9): bounded retries with exponential backoff and jitter for connection
errors, 429 and selected 5xx responses; Retry-After is honoured (capped).

Residual risk: DNS can change between the check and the connection (rebinding). Results
are cached per client, which narrows that window; outbound firewalling closes it fully.
"""

import asyncio
import ipaddress
import json
import random
import re
import socket
from dataclasses import dataclass, field
from typing import Any, Self
from urllib.parse import urljoin, urlsplit

import httpx

from seo_agent.config import Settings
from seo_agent.tools.base import ErrorKind, ToolFailure

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
MAX_RETRY_AFTER_SECONDS = 30.0
_CHARSET = re.compile(r"charset=([\w.:-]+)", re.I)


class FetchError(Exception):
    def __init__(self, code: str, message: str, *, transient: bool) -> None:
        super().__init__(message)
        self.code = code
        self.transient = transient

    def to_tool_failure(self) -> ToolFailure:
        kind = ErrorKind.TRANSIENT if self.transient else ErrorKind.PERMANENT
        return ToolFailure(self.code, str(self), kind)


def is_public_address(address: str) -> bool:
    """True only for globally routable unicast addresses."""
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int
    headers: dict[str, str]
    body: bytes
    truncated: bool
    elapsed_ms: int
    redirects: list[str] = field(default_factory=list)

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";")[0].strip().lower()

    @property
    def is_html(self) -> bool:
        return self.content_type in ("text/html", "application/xhtml+xml")

    def text(self) -> str:
        match = _CHARSET.search(self.headers.get("content-type", ""))
        charset = match.group(1) if match else "utf-8"
        try:
            return self.body.decode(charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


class SafeHttpClient:
    def __init__(
        self,
        *,
        user_agent: str,
        timeout_seconds: float,
        max_bytes: int,
        concurrency: int = 4,
        allowed_hosts: set[str] | None = None,
        max_attempts: int = 3,
    ) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            headers={"User-Agent": user_agent},
            limits=httpx.Limits(max_connections=max(concurrency * 2, 10)),
        )
        self._semaphore = asyncio.Semaphore(max(concurrency, 1))
        self._total_timeout = timeout_seconds * 2
        self._dns_cache: dict[str, list[str]] = {}
        self._allowed_hosts = allowed_hosts
        self._max_bytes = max_bytes
        self._max_attempts = max_attempts

    @classmethod
    def from_settings(
        cls, settings: Settings, *, allowed_hosts: set[str] | None = None, **overrides: Any
    ) -> Self:
        options: dict[str, Any] = {
            "user_agent": settings.crawler_user_agent,
            "timeout_seconds": settings.crawler_request_timeout_seconds,
            "max_bytes": settings.crawler_max_response_bytes,
            "concurrency": settings.crawler_concurrency,
            "allowed_hosts": allowed_hosts,
        }
        options.update(overrides)
        return cls(**options)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._client.aclose()

    # ── Safety checks ───────────────────────────────────────────────────────

    async def resolve_public(self, host: str) -> list[str]:
        """Resolve `host`; raise unless every address is public."""
        if host in self._dns_cache:
            return self._dns_cache[host]
        try:
            infos = await self._getaddrinfo(host)
        except (socket.gaierror, UnicodeError) as exc:  # UnicodeError: invalid IDNA label
            raise FetchError(
                "dns_resolution_failed", f"Cannot resolve {host}", transient=False
            ) from exc
        addresses = sorted({str(info[4][0]) for info in infos})
        if not addresses or not all(is_public_address(a) for a in addresses):
            raise FetchError(
                "blocked_address", f"{host} resolves to a non-public address", transient=False
            )
        self._dns_cache[host] = addresses
        return addresses

    async def _getaddrinfo(self, host: str) -> list[Any]:
        loop = asyncio.get_running_loop()
        return await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)

    async def _check_url(self, url: str) -> None:
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError as exc:  # malformed netloc or port
            raise FetchError("invalid_url", f"Malformed URL: {url[:200]}", transient=False) from exc
        if parts.scheme not in ("http", "https"):
            raise FetchError(
                "unsupported_scheme", f"Unsupported URL scheme: {url}", transient=False
            )
        host = (parts.hostname or "").lower()
        if not host:
            raise FetchError("invalid_url", f"URL has no host: {url}", transient=False)
        if port not in (None, 80, 443):
            raise FetchError("blocked_port", f"Non-standard port refused: {url}", transient=False)
        if self._allowed_hosts is not None and host not in self._allowed_hosts:
            raise FetchError(
                "out_of_scope", f"Host outside the crawl scope: {host}", transient=False
            )
        await self.resolve_public(host)

    # ── Requests ────────────────────────────────────────────────────────────

    async def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_body: Any = None,
        max_bytes: int | None = None,
        max_redirects: int = 5,
    ) -> FetchResult:
        """Request `url`, following and re-validating redirects. Raises FetchError."""
        loop = asyncio.get_running_loop()
        started = loop.time()
        redirects: list[str] = []
        current = url
        for _ in range(max_redirects + 1):
            await self._check_url(current)
            response, body, truncated = await self._send(
                method, current, params, headers, json_body, max_bytes or self._max_bytes
            )
            location = response.headers.get("location")
            if response.status_code in REDIRECT_STATUSES and location:
                previous_host = urlsplit(current).hostname
                current = urljoin(current, location)
                redirects.append(current)
                method, params, json_body = "GET", None, None
                if urlsplit(current).hostname != previous_host:
                    headers = None  # never forward credentials (e.g. Authorization) cross-host
                continue
            return FetchResult(
                url=url,
                final_url=current,
                status_code=response.status_code,
                headers={k.lower(): v for k, v in response.headers.items()},
                body=body,
                truncated=truncated,
                elapsed_ms=int((loop.time() - started) * 1000),
                redirects=redirects,
            )
        raise FetchError(
            "too_many_redirects", f"More than {max_redirects} redirects: {url}", transient=False
        )

    async def get_json(
        self,
        url: str,
        *,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_body: Any = None,
        max_bytes: int = 20_000_000,
    ) -> Any:
        """Call a JSON API. Non-2xx responses raise FetchError (429/5xx are transient)."""
        result = await self.fetch(
            url, method=method, params=params, headers=headers, json_body=json_body,
            max_bytes=max_bytes,
        )
        if not 200 <= result.status_code < 300:
            detail = result.text()[:300]
            raise FetchError(
                f"http_{result.status_code}",
                f"{urlsplit(url).netloc} returned {result.status_code}: {detail}",
                transient=result.status_code in RETRY_STATUSES,
            )
        try:
            return json.loads(result.body)
        except ValueError as exc:
            raise FetchError("invalid_json", f"Invalid JSON from {url}", transient=False) from exc

    async def _send(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None,
        headers: dict[str, str] | None,
        json_body: Any,
        max_bytes: int,
    ) -> tuple[httpx.Response, bytes, bool]:
        for attempt in range(1, self._max_attempts + 1):
            try:
                async with self._semaphore:
                    # Overall deadline: per-read timeouts alone let a slow drip run for ages.
                    async with asyncio.timeout(self._total_timeout), self._client.stream(
                        method, url, params=params, headers=headers, json=json_body
                    ) as response:
                        body, truncated = await _read_capped(response, max_bytes)
            except httpx.InvalidURL as exc:
                raise FetchError(
                    "invalid_url", f"Invalid URL: {url[:200]}", transient=False
                ) from exc
            except (httpx.TransportError, TimeoutError) as exc:  # connect/read errors, timeouts
                if attempt == self._max_attempts:
                    raise FetchError(
                        "network_error", f"{type(exc).__name__} for {url}", transient=True
                    ) from exc
                await asyncio.sleep(_backoff(attempt, None))
                continue
            if response.status_code in RETRY_STATUSES and attempt < self._max_attempts:
                await asyncio.sleep(_backoff(attempt, response.headers.get("retry-after")))
                continue
            return response, body, truncated
        raise AssertionError("unreachable")  # pragma: no cover


async def _read_capped(response: httpx.Response, max_bytes: int) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        if size + len(chunk) > max_bytes:
            chunks.append(chunk[: max_bytes - size])
            return b"".join(chunks), True
        chunks.append(chunk)
        size += len(chunk)
    return b"".join(chunks), False


def _backoff(attempt: int, retry_after: str | None) -> float:
    if retry_after and retry_after.strip().isdigit():
        return min(float(retry_after), MAX_RETRY_AFTER_SECONDS)
    return min(2 ** (attempt - 1), 8) + random.uniform(0, 0.5)  # noqa: S311 - jitter, not crypto
