"""Agent 2 — Keyword and Trend Research (design doc §4.3, §10).

Tools: get_search_performance (when configured) → score_keyword_opportunities and
extract_site_topics. No trend source is configured yet, so trends are reported as
unavailable instead of being guessed.
"""

import asyncio
from typing import Annotated, Any, Literal

from pydantic import Field

from seo_agent.agents.base import (
    AgentSchema,
    Lowered,
    guarded_node,
    load_agent_output,
    run_agent,
    tool_args,
)
from seo_agent.config import AgentName, get_settings
from seo_agent.orchestration.state import WorkflowState
from seo_agent.tools.base import ToolStatus
from seo_agent.tools.keywords import ScoreRequest, TopicsRequest, extract_site_topics
from seo_agent.tools.keywords import score_keyword_opportunities
from seo_agent.tools.search_console import SearchPerformanceRequest, get_search_performance

NAME = AgentName.KEYWORD_RESEARCH.value
NO_TREND_SOURCE = "No trend data source is configured; trend analysis is unavailable."

Intent = Annotated[
    Literal["informational", "commercial", "transactional", "navigational"], Lowered
]
Category = Annotated[
    Literal["optimize_existing", "create_new", "expand_cluster", "investigate_decline",
            "monitor_trend", "deprioritize"],
    Lowered,
]
Confidence = Annotated[Literal["low", "medium", "high"], Lowered]


class KeywordMetrics(AgentSchema):
    impressions: float | None = None
    clicks: float | None = None
    ctr: float | None = None
    avg_position: float | None = None
    measurement_window: str | list[str] | None = None
    source: str | None = None


class KeywordTrend(AgentSchema):
    direction: Annotated[Literal["rising", "stable", "falling", "unknown"], Lowered] = "unknown"
    source: str | None = None


class KeywordOpportunity(AgentSchema):
    keyword: str
    intent: Intent
    category: Category
    target_url: str | None = None
    metrics: KeywordMetrics = Field(default_factory=KeywordMetrics)
    trend: KeywordTrend = Field(default_factory=KeywordTrend)
    score: float | None = None
    score_version: str | None = None
    confidence: Confidence = "low"
    rationale: str = ""
    recommended_action: str = ""


class CannibalizationFix(AgentSchema):
    query: str
    keep_url: str
    other_urls: list[str] = Field(default_factory=list)
    action: str = ""


class KeywordResearchOutput(AgentSchema):
    summary: str
    market_assumption: str = ""
    opportunities: list[KeywordOpportunity] = Field(default_factory=list)
    cannibalization: list[CannibalizationFix] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)


@guarded_node(NAME)
async def node(state: WorkflowState) -> dict[str, Any]:
    settings = get_settings()
    args = tool_args(state)
    artifacts: dict[str, str] = {}
    gaps = [NO_TREND_SOURCE]

    search = await get_search_performance(
        SearchPerformanceRequest(**args, lookback_days=settings.gsc_lookback_days)
    )
    artifacts["search_console"] = search.output_path
    if search.status is ToolStatus.SKIPPED:
        gaps.append("Search Console not configured: impressions, clicks, CTR and positions "
                    "are unavailable.")
    elif search.status is ToolStatus.FAILED and search.error:
        gaps.append(f"Search Console failed: {search.error.message}")

    scored = await asyncio.to_thread(
        score_keyword_opportunities, ScoreRequest(**args, search_path=search.output_path)
    )
    artifacts["keyword_scores"] = scored.output_path
    topics = await asyncio.to_thread(
        extract_site_topics, TopicsRequest(**args, crawl_path=state["artifacts"]["crawl"])
    )
    artifacts["site_topics"] = topics.output_path

    search_data = search.data or {}
    scored_data = scored.data or {}
    audit = load_agent_output(state, AgentName.SEO_AUDIT)
    evidence = {
        "search_console": {
            "status": search.status.value,
            "property": search_data.get("property"),
            "window": search_data.get("window"),
            "previous_window": search_data.get("previous_window"),
            "totals": search_data.get("totals"),
        },
        "scoring": {
            "scoring_version": scored_data.get("scoring_version"),
            "weights": scored_data.get("weights"),
        },
        "quick_wins": scored_data.get("quick_wins", []),
        "cannibalization": scored_data.get("cannibalization", []),
        "declining_pages": scored_data.get("declining_pages", []),
        "top_pages": scored_data.get("top_pages", []),
        "scored_queries": scored_data.get("opportunities", [])[:100],
        "site_topics": (topics.data or {}).get("topics", []),
        "audit_summary": audit.get("summary") if audit else None,
        "trend_data": NO_TREND_SOURCE,
    }
    search_note = (
        f"Available: property {search_data.get('property')}, window "
        f"{'/'.join(search_data.get('window') or [])}."
        if search.status is ToolStatus.SUCCESS
        else "Search Console data is not available for this run."
    )
    outcome = await run_agent(
        AgentName.KEYWORD_RESEARCH,
        state,
        evidence=evidence,
        schema=KeywordResearchOutput,
        prompt_vars={"search_console": search_note},
    )
    artifacts[NAME] = outcome.output_path
    if search.status is ToolStatus.SUCCESS:
        totals = search_data.get("totals") or {}
        gsc_note = (f"connected ({search_data.get('property')}, "
                    f"{'/'.join(search_data.get('window') or [])}: {totals.get('clicks')} clicks, "
                    f"{totals.get('impressions')} impressions)")
    elif search.status is ToolStatus.SKIPPED:
        gsc_note = "not configured (keyword metrics unavailable)"
    else:
        gsc_note = f"failed: {search.error.message if search.error else 'unknown error'}"
    return {
        "task_status": {NAME: outcome.status.value},
        "artifacts": artifacts,
        "sources": {"Search Console": gsc_note},
        "data_gaps": gaps,
        "errors": [f"{NAME}: {outcome.error}"] if outcome.error else [],
    }
