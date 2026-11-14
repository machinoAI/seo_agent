"""T08 `analyze_page_speed` + T09 field data, via the PageSpeed Insights API.

One API call returns both Lighthouse lab metrics and Chrome UX Report (CrUX) field data,
so no local Lighthouse/Chrome install is needed. Works without an API key at a low quota;
set PAGESPEED_API_KEY for regular use. Lab and field data are kept separate.
"""

from collections import Counter
from typing import Any, Literal

from seo_agent.config import get_settings
from seo_agent.tools.base import ToolOutput, ToolRequest, recorded_tool
from seo_agent.tools.http import FetchError, SafeHttpClient

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
PSI_TIMEOUT_SECONDS = 180.0

_LAB_AUDITS = {
    "lcp_ms": "largest-contentful-paint",
    "fcp_ms": "first-contentful-paint",
    "tbt_ms": "total-blocking-time",
    "cls": "cumulative-layout-shift",
    "speed_index_ms": "speed-index",
    "ttfb_ms": "server-response-time",
}
_FIELD_METRICS = {
    "lcp_ms": "LARGEST_CONTENTFUL_PAINT_MS",
    "inp_ms": "INTERACTION_TO_NEXT_PAINT",
    "cls": "CUMULATIVE_LAYOUT_SHIFT_SCORE",
    "fcp_ms": "FIRST_CONTENTFUL_PAINT_MS",
    "ttfb_ms": "EXPERIMENTAL_TIME_TO_FIRST_BYTE",
}


def select_priority_urls(crawl: dict[str, Any], limit: int) -> list[str]:
    """Homepage first, then the HTML pages with the most internal links pointing at them."""
    pages = [p for p in crawl.get("pages", []) if p.get("parsed")]
    inbound: Counter[str] = Counter()
    for page in pages:
        inbound.update(page.get("internal_links", []))
    ok = {p["url"] for p in pages}
    start = crawl.get("start_url")
    ranked = [start] if start in ok else []
    ranked += [u for u, _ in inbound.most_common() if u in ok and u not in ranked]
    ranked += [p["url"] for p in pages if p["url"] not in ranked]
    return ranked[:limit]


def _field(experience: dict[str, Any] | None) -> dict[str, Any] | None:
    if not experience or not experience.get("metrics"):
        return None
    metrics = experience["metrics"]
    values: dict[str, Any] = {}
    for name, key in _FIELD_METRICS.items():
        percentile = metrics.get(key, {}).get("percentile")
        if percentile is not None and name == "cls":
            percentile = percentile / 100  # CrUX reports CLS x100
        values[name] = percentile
    return {
        "scope": "origin" if experience.get("origin_fallback") else "url",
        "overall_category": experience.get("overall_category"),
        "p75": values,
    }


def extract_pagespeed(payload: dict[str, Any], url: str, strategy: str) -> dict[str, Any]:
    """Reduce a PageSpeed Insights response to lab metrics, field data and top savings."""
    lighthouse = payload.get("lighthouseResult", {})
    audits: dict[str, Any] = lighthouse.get("audits", {})
    score = lighthouse.get("categories", {}).get("performance", {}).get("score")

    lab: dict[str, Any] = {
        "performance_score": round(score * 100) if isinstance(score, int | float) else None
    }
    for name, audit_id in _LAB_AUDITS.items():
        value = audits.get(audit_id, {}).get("numericValue")
        lab[name] = round(value, 3) if isinstance(value, int | float) else None

    savings = []
    for audit_id, audit in audits.items():
        details = audit.get("details") or {}
        metric_savings = audit.get("metricSavings") or {}
        saved = details.get("overallSavingsMs") or max(
            (v for v in metric_savings.values() if isinstance(v, int | float)), default=0
        )
        if saved and saved > 0 and (audit.get("score") or 0) < 1:
            savings.append(
                {"id": audit_id, "title": audit.get("title"), "savings_ms": round(saved)}
            )
    savings.sort(key=lambda s: -s["savings_ms"])

    url_field = payload.get("loadingExperience")
    return {
        "url": url,
        "strategy": strategy,
        "analyzed_at": payload.get("analysisUTCTimestamp"),
        "lighthouse_version": lighthouse.get("lighthouseVersion"),
        "lab": lab,
        "field": None if (url_field or {}).get("origin_fallback") else _field(url_field),
        "origin_field": _field(payload.get("originLoadingExperience")),
        "top_savings": savings[:5],
    }


class PageSpeedRequest(ToolRequest):
    url: str
    strategy: Literal["mobile", "desktop"] = "mobile"


@recorded_tool("analyze_page_speed")
async def analyze_page_speed(request: PageSpeedRequest) -> ToolOutput:
    settings = get_settings()
    params: dict[str, Any] = {
        "url": request.url,
        "strategy": request.strategy,
        "category": "performance",
    }
    if settings.pagespeed_api_key:
        params["key"] = settings.pagespeed_api_key.get_secret_value()

    async with SafeHttpClient.from_settings(
        settings, timeout_seconds=PSI_TIMEOUT_SECONDS, max_attempts=2
    ) as client:
        try:
            payload = await client.get_json(PSI_ENDPOINT, params=params)
        except FetchError as exc:
            raise exc.to_tool_failure() from exc

    data = extract_pagespeed(payload, request.url, request.strategy)
    warnings = [] if data["field"] else ["No URL-level real-user (CrUX) data for this page."]
    return ToolOutput(source="pagespeed_insights", data=data, warnings=warnings)
