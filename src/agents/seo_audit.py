"""Agent 1 — SEO Audit (design doc §4.2).

Tools: discover_site_urls → crawl_website → analyze_technical_seo → analyze_page_speed
(priority pages). The LLM then reviews, prioritizes and explains the findings.
"""

import asyncio
from collections import defaultdict
from typing import Annotated, Any, Literal

from pydantic import Field

from src.agents.base import AgentSchema, Lowered, guarded_node, run_agent, tool_args
from src.config import AgentName, get_settings
from src.orchestration.state import WorkflowState
from src.persistence.database import transaction
from src.persistence.output_store import read_result_data
from src.persistence.repositories import get_previous_agent_output
from src.tools.base import ToolStatus
from src.tools.crawling import (
    CrawlRequest,
    DiscoverRequest,
    crawl_website,
    discover_site_urls,
    stratified_sample,
)
from src.tools.performance import PageSpeedRequest, analyze_page_speed
from src.tools.performance import select_priority_urls
from src.tools.technical_seo import TechnicalAuditRequest, analyze_technical_seo

NAME = AgentName.SEO_AUDIT.value


# ── Output schema (mirrors prompts/seo_audit.yaml) ───────────────────────────


class AuditFinding(AgentSchema):
    issue_type: str
    severity: Annotated[Literal["critical", "high", "medium", "low"], Lowered]
    status: Annotated[Literal["new", "unchanged", "resolved"], Lowered] = "new"
    affected_count: int = 0
    example_urls: list[str] = Field(default_factory=list)
    evidence: str = ""
    source_tool: str | None = None
    observed_at: str | None = None
    recommended_action: str = ""
    owner: Annotated[Literal["developer", "content", "seo"], Lowered] = "developer"
    effort: Annotated[Literal["small", "medium", "large"], Lowered] = "medium"
    done_when: str = ""


class PerformanceEntry(AgentSchema):
    url: str
    measurement: Annotated[Literal["lab", "field"], Lowered]
    metrics: dict[str, Any] = Field(default_factory=dict)
    source_tool: str | None = None
    observed_at: str | None = None


class SeoAuditOutput(AgentSchema):
    summary: str
    pages_crawled: int = 0
    findings: list[AuditFinding] = Field(default_factory=list)
    performance: list[PerformanceEntry] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)


# ── Node ─────────────────────────────────────────────────────────────────────


def _previous_audit_summary(output: dict[str, Any] | None) -> str | None:
    if not output:
        return None
    lines = [f"Summary: {output.get('summary', '')}"]
    lines += [
        f"- {f.get('issue_type')} ({f.get('severity')}, {f.get('affected_count')} pages)"
        for f in output.get("findings", [])[:30]
    ]
    return "\n".join(lines)


@guarded_node(NAME)
async def node(state: WorkflowState) -> dict[str, Any]:
    settings = get_settings()
    args = tool_args(state)
    max_pages = state.get("options", {}).get("max_pages") or settings.crawler_max_pages
    artifacts: dict[str, str] = {}
    gaps: list[str] = []

    discovery = await discover_site_urls(DiscoverRequest(
        **args, start_url=state["start_url"], allowed_hosts=state["allowed_hosts"],
    ))
    artifacts["discovery"] = discovery.output_path
    discovery_data = discovery.data or {}
    if discovery.status is ToolStatus.FAILED:
        # robots.txt rules are unknown: crawling now could ignore them, so stop here.
        reason = discovery.error.message if discovery.error else "unknown error"
        return {
            "task_status": {NAME: "failed"},
            "artifacts": artifacts,
            "pages_crawled": 0,
            "data_gaps": [f"URL discovery failed ({reason}); crawl skipped to respect robots.txt."],
            "errors": [f"{NAME}: discovery failed: {reason}"],
        }

    crawl = await crawl_website(CrawlRequest(
        **args,
        start_url=state["start_url"],
        allowed_hosts=state["allowed_hosts"],
        # Spread the page budget across every section/template of the sitemap.
        seed_urls=stratified_sample(discovery_data.get("urls", []), max_pages - 1),
        robots_txt=discovery_data.get("robots_txt", ""),
        max_pages=max_pages,
        max_depth=settings.crawler_max_depth,
    ))
    artifacts["crawl"] = crawl.output_path
    crawl_data = crawl.data or {}
    stats = crawl_data.get("stats", {})
    if crawl.status is ToolStatus.FAILED:
        gaps.append(f"Crawl failed: {crawl.error.message if crawl.error else 'unknown error'}")

    technical = await asyncio.to_thread(analyze_technical_seo, TechnicalAuditRequest(
        **args,
        crawl_path=crawl.output_path,
        discovery_path=discovery.output_path if discovery.status is ToolStatus.SUCCESS else None,
        validation_path=state.get("artifacts", {}).get("validate_site"),
    ))
    artifacts["technical_seo"] = technical.output_path
    technical_data = technical.data or {}

    performance = []
    psi_failures: dict[str, list[str]] = defaultdict(list)
    for url in select_priority_urls(crawl_data, settings.pagespeed_max_urls):
        result = await analyze_page_speed(PageSpeedRequest(**args, url=url))
        if result.status is ToolStatus.SUCCESS:
            performance.append({**result.data, "observed_at": result.completed_at.isoformat()})
        else:
            psi_failures[result.error.code if result.error else "unknown"].append(url)
    for code, urls in psi_failures.items():
        hint = " (no PAGESPEED_API_KEY: anonymous quota)" if not settings.pagespeed_api_key else ""
        gaps.append(f"PageSpeed failed ({code}){hint} for {len(urls)} page(s): {', '.join(urls)}")

    html_pages = int(stats.get("html_pages", 0))
    sitemap_total = int(discovery_data.get("url_count") or 0)
    coverage = {
        "sitemap_urls": sitemap_total,
        "pages_fetched": stats.get("pages_fetched", 0),
        "html_pages_analyzed": html_pages,
        "error_pages": stats.get("pages_fetched", 0) - html_pages,
        "share_of_sitemap": (
            f"{100 * stats.get('pages_fetched', 0) / sitemap_total:.1f}%" if sitemap_total else None
        ),
        "sitemap_urls_by_template": discovery_data.get("url_count_by_template"),
        "sampling": "homepage + sitemap URLs spread evenly across URL templates",
        "crawl_health": stats.get("crawl_health"),
    }

    async with transaction() as session:
        previous = await get_previous_agent_output(
            session, website_domain=state["site"], agent=NAME, exclude_run_id=args["run_id"]
        )

    prompt_vars = {
        "crawl_limits": (
            f"Up to {max_pages} pages, link depth {settings.crawler_max_depth}, "
            f"{settings.crawler_concurrency} parallel requests, robots.txt respected."
        )
    }
    if summary := _previous_audit_summary(previous):
        prompt_vars["previous_audit"] = summary

    findings = [
        {**f, "affected": f.get("affected", [])[:15]}  # full lists stay in the tool output
        for f in technical_data.get("findings", [])[:60]
    ]
    evidence = {
        "coverage": coverage,
        "homepage": {
            k: v for k, v in (_validation_data(state) or {}).items()
            if k in ("home_url", "final_url", "redirects", "status_code", "https")
        },
        "robots_and_sitemaps": {
            "robots": discovery_data.get("robots"),
            "sitemaps": discovery_data.get("sitemaps"),
        },
        "crawler_access": technical_data.get("crawler_access"),
        "section_health": technical_data.get("section_health", []),
        "findings": findings,
        "performance": performance,
        "tool_warnings": [*discovery.warnings, *crawl.warnings, *technical.warnings],
    }
    outcome = await run_agent(
        AgentName.SEO_AUDIT,
        state,
        evidence=evidence,
        schema=SeoAuditOutput,
        prompt_vars=prompt_vars,
    )
    artifacts[NAME] = outcome.output_path
    measured = f"{len(performance)} of {len(performance) + sum(map(len, psi_failures.values()))}"
    psi_note = f"{measured} priority pages measured"
    if psi_failures:
        psi_note += f" ({', '.join(psi_failures)}"
        psi_note += "; no PAGESPEED_API_KEY)" if not settings.pagespeed_api_key else ")"
    return {
        "task_status": {NAME: outcome.status.value},
        "artifacts": artifacts,
        "pages_crawled": html_pages,
        "coverage": coverage,
        "sources": {"PageSpeed": psi_note},
        "data_gaps": gaps,
        "errors": [f"{NAME}: {outcome.error}"] if outcome.error else [],
    }


def _validation_data(state: WorkflowState) -> dict[str, Any] | None:
    path = state.get("artifacts", {}).get("validate_site")
    return read_result_data(path) if path else None
