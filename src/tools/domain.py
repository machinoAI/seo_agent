"""T01 `validate_domain`: check the target site is public, reachable and in scope."""

from urllib.parse import urlsplit

from src.config import get_settings
from src.tools.base import ToolOutput, ToolRequest, recorded_tool
from src.tools.http import FetchError, FetchResult, SafeHttpClient


def site_hosts(site: str) -> set[str]:
    """Hosts that belong to the site: the domain and its www / non-www twin."""
    bare = site.removeprefix("www.")
    return {bare, f"www.{bare}"}


@recorded_tool("validate_domain")
async def validate_domain(request: ToolRequest) -> ToolOutput:
    """Resolve the domain (public IPs only) and load the homepage over HTTPS, then HTTP."""
    settings = get_settings()
    async with SafeHttpClient.from_settings(settings) as client:
        try:
            addresses = await client.resolve_public(request.site)
        except FetchError as exc:
            raise exc.to_tool_failure() from exc

        home: FetchResult | None = None
        last_error: FetchError | None = None
        for scheme in ("https", "http"):
            try:
                home = await client.fetch(f"{scheme}://{request.site}/")
                break
            except FetchError as exc:
                last_error = exc
        if home is None:
            assert last_error is not None
            raise last_error.to_tool_failure() from last_error

    final_host = (urlsplit(home.final_url).hostname or "").lower()
    allowed = site_hosts(request.site)
    warnings: list[str] = []
    if final_host not in allowed:
        warnings.append(
            f"Homepage redirects to another domain ({final_host}); crawl stays on {request.site}."
        )
    if home.status_code >= 400:
        warnings.append(f"Homepage returned HTTP {home.status_code}.")

    return ToolOutput(
        source="dns+http",
        data={
            "site": request.site,
            "addresses": addresses,
            "home_url": home.url,
            "final_url": home.final_url,
            "status_code": home.status_code,
            "https": home.final_url.startswith("https://"),
            "redirects": home.redirects,
            "allowed_hosts": sorted(allowed),
            "start_url": home.final_url if final_host in allowed else home.url,
        },
        warnings=warnings,
    )
