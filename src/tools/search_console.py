"""T10 `get_search_performance`: Google Search Console Search Analytics (read-only).

Authenticates with a service account (GSC_SERVICE_ACCOUNT_FILE) that has been added as a
user on the Search Console property. Returns the current window and the previous window
of equal length so declines can be detected. Skipped cleanly when not configured.
"""

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from src.config import get_settings
from src.tools.base import (
    ErrorKind,
    ToolFailure,
    ToolOutput,
    ToolRequest,
    ToolStatus,
    recorded_tool,
)
from src.tools.http import FetchError, SafeHttpClient

SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
QUERY_URL = (
    "https://searchconsole.googleapis.com/webmasters/v3/sites/{property}/searchAnalytics/query"
)
SITES_URL = "https://searchconsole.googleapis.com/webmasters/v3/sites"
DATA_DELAY_DAYS = 3  # recent days are incomplete in Search Console


class SearchPerformanceRequest(ToolRequest):
    lookback_days: int = 28
    row_limit: int = 5000  # API maximum is 25,000 rows per request


def date_windows(today: date, lookback_days: int) -> dict[str, tuple[str, str]]:
    end = today - timedelta(days=DATA_DELAY_DAYS)
    start = end - timedelta(days=lookback_days - 1)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=lookback_days - 1)
    return {
        "current": (start.isoformat(), end.isoformat()),
        "previous": (prev_start.isoformat(), prev_end.isoformat()),
    }


def candidate_properties(site: str, configured: str | None) -> list[str]:
    """GSC_PROPERTY if set; otherwise the Domain property, then URL-prefix properties."""
    if configured:
        return [configured]
    bare = site.removeprefix("www.")
    return list(dict.fromkeys([f"sc-domain:{bare}", f"https://{site}/", f"https://www.{bare}/",
                               f"https://{bare}/"]))


async def check_access(site: str) -> dict[str, Any]:
    """Diagnostics for `seo-agent --check-sources`: which properties the account can read."""
    settings = get_settings()
    key_file = settings.gsc_service_account_file
    if key_file is None:
        return {"status": "not_configured", "detail": "GSC_SERVICE_ACCOUNT_FILE is blank."}
    if not key_file.exists():
        return {"status": "error", "detail": f"Service-account file not found: {key_file}"}
    try:
        account = json.loads(key_file.read_text(encoding="utf-8")).get("client_email")
        token = await asyncio.to_thread(_access_token, key_file)
    except Exception as exc:
        return {"status": "error", "detail": f"Authentication failed: {type(exc).__name__}: {exc}"}
    try:
        async with SafeHttpClient.from_settings(settings, timeout_seconds=30) as client:
            payload = await client.get_json(
                SITES_URL, headers={"Authorization": f"Bearer {token}"}
            )
    except FetchError as exc:
        return {"status": "error", "service_account": account, "detail": str(exc)}
    properties = [(e["siteUrl"], e.get("permissionLevel")) for e in payload.get("siteEntry", [])]
    readable = {url for url, _ in properties}
    match = next(
        (p for p in candidate_properties(site, settings.gsc_property) if p in readable), None
    )
    return {
        "status": "ok" if match else "no_access",
        "service_account": account,
        "properties": properties,
        "will_use": match,
    }


def _access_token(path: Path) -> str:
    """Blocking: exchange the service-account key for an access token."""
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_file(str(path), scopes=[SCOPE])
    credentials.refresh(Request())
    return str(credentials.token)


async def _query(
    client: SafeHttpClient, token: str, prop: str, window: tuple[str, str], row_limit: int
) -> list[dict[str, Any]]:
    payload = await client.get_json(
        QUERY_URL.format(property=quote(prop, safe="")),
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
        json_body={
            "startDate": window[0],
            "endDate": window[1],
            "dimensions": ["query", "page"],
            "rowLimit": row_limit,
        },
    )
    return list(payload.get("rows", []))


def merge_windows(
    current: list[dict[str, Any]], previous: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Flatten API rows and attach the previous window's numbers to each (query, page)."""
    before = {tuple(r["keys"]): r for r in previous}
    rows = []
    for row in current:
        query, page = row["keys"]
        prev = before.get((query, page))
        rows.append({
            "query": query,
            "page": page,
            "clicks": row.get("clicks", 0),
            "impressions": row.get("impressions", 0),
            "ctr": round(row.get("ctr", 0.0), 4),
            "position": round(row.get("position", 0.0), 1),
            "previous": None if prev is None else {
                "clicks": prev.get("clicks", 0),
                "impressions": prev.get("impressions", 0),
                "position": round(prev.get("position", 0.0), 1),
            },
        })
    return rows


@recorded_tool("get_search_performance")
async def get_search_performance(request: SearchPerformanceRequest) -> ToolOutput:
    settings = get_settings()
    key_file = settings.gsc_service_account_file
    if key_file is None:
        return ToolOutput(
            source="search_console",
            status=ToolStatus.SKIPPED,
            warnings=["Search Console is not configured (GSC_SERVICE_ACCOUNT_FILE is blank)."],
        )
    if not key_file.exists():
        raise ToolFailure("credentials_missing", f"Service-account file not found: {key_file}")

    try:
        token = await asyncio.to_thread(_access_token, key_file)
    except Exception as exc:
        raise ToolFailure(
            "auth_failed", f"Search Console authentication failed ({type(exc).__name__})"
        ) from exc

    properties = candidate_properties(request.site, settings.gsc_property)
    windows = date_windows(datetime.now(UTC).date(), request.lookback_days)

    async with SafeHttpClient.from_settings(settings, timeout_seconds=60) as client:
        for prop in properties:
            try:
                current = await _query(client, token, prop, windows["current"], request.row_limit)
                previous = await _query(client, token, prop, windows["previous"], request.row_limit)
                break
            except FetchError as exc:
                if exc.code in ("http_403", "http_404"):
                    continue  # no access to this property form; try the next one
                raise exc.to_tool_failure() from exc
        else:
            raise ToolFailure(
                "property_not_accessible",
                f"The service account cannot read any of {properties}. Add it as a user in "
                "Search Console or set GSC_PROPERTY.",
                ErrorKind.PERMANENT,
            )

    rows = merge_windows(current, previous)
    warnings = [] if rows else ["Search Console returned no rows for this window."]
    return ToolOutput(
        source="search_console",
        data={
            "property": prop,
            "window": windows["current"],
            "previous_window": windows["previous"],
            "row_limit": request.row_limit,
            "rows": rows,
            "totals": {
                "clicks": sum(r["clicks"] for r in rows),
                "impressions": sum(r["impressions"] for r in rows),
                "queries": len({r["query"] for r in rows}),
                "pages": len({r["page"] for r in rows}),
            },
        },
        warnings=warnings,
    )
