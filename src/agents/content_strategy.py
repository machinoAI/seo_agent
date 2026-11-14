"""Agent 3 — Content Strategy (design doc §4.4).

Tools: match_topics_to_pages (lexical v1) over the crawl inventory. Inputs: keyword
opportunities (or site topics when those are missing) and the top audit findings.
"""

import asyncio
from typing import Annotated, Any, Literal

from pydantic import Field

from src.agents.base import (
    AgentSchema,
    Lowered,
    guarded_node,
    load_agent_output,
    run_agent,
    tool_args,
)
from src.agents.keyword_research import Confidence, Intent
from src.config import AgentName
from src.orchestration.state import WorkflowState
from src.persistence.database import transaction
from src.persistence.output_store import read_result_data
from src.persistence.repositories import get_previous_agent_output
from src.tools.content import MatchRequest, match_topics_to_pages

NAME = AgentName.CONTENT_STRATEGY.value
MAX_TOPICS = 30
MAX_INVENTORY = 150


class InternalLink(AgentSchema):
    from_url: str
    anchor_text: str = ""


class ContentRecommendation(AgentSchema):
    action: Annotated[Literal["update", "create", "consolidate", "investigate"], Lowered]
    target_url: str | None = None
    target_keyword: str
    search_intent: Intent
    evidence: list[str] = Field(default_factory=list)
    proposed_title: str = ""
    outline: list[str] = Field(default_factory=list)
    questions_to_answer: list[str] = Field(default_factory=list)
    internal_links: list[InternalLink] = Field(default_factory=list)
    structured_data: list[str] = Field(default_factory=list)
    expected_opportunity: str = ""
    confidence: Confidence = "low"
    effort: Annotated[Literal["small", "medium", "large"], Lowered] = "medium"
    priority: Annotated[Literal["p1", "p2", "p3"], Lowered] = "p2"
    validation_checklist: list[str] = Field(default_factory=list)
    success_criteria: str = ""
    measurement_window_days: int | None = None


class ContentStrategyOutput(AgentSchema):
    summary: str
    recommendations: list[ContentRecommendation] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)


def _topics(state: WorkflowState) -> list[str]:
    keywords = load_agent_output(state, AgentName.KEYWORD_RESEARCH) or {}
    topics = [
        o["keyword"] for o in keywords.get("opportunities", [])
        if o.get("category") != "deprioritize"
    ]
    if len(topics) < 5 and (path := state.get("artifacts", {}).get("site_topics")):
        site_topics = read_result_data(path) or {}
        topics += [t["phrase"] for t in site_topics.get("topics", [])]
    return list(dict.fromkeys(topics))[:MAX_TOPICS]


def _inventory(crawl_path: str) -> list[dict[str, Any]]:
    crawl = read_result_data(crawl_path) or {}
    return [
        {
            "url": p["url"],
            "title": p.get("title"),
            "h1": (p.get("h1") or [None])[0],
            "word_count": p.get("word_count"),
            "structured_data": p.get("structured_data_types"),
        }
        for p in crawl.get("pages", [])
        if p.get("parsed")
    ][:MAX_INVENTORY]


@guarded_node(NAME)
async def node(state: WorkflowState) -> dict[str, Any]:
    args = tool_args(state)
    crawl_path = state["artifacts"]["crawl"]
    topics = _topics(state)
    gaps: list[str] = []
    if not topics:
        gaps.append("No keyword opportunities or site topics to plan content around.")

    matches = await asyncio.to_thread(
        match_topics_to_pages, MatchRequest(**args, crawl_path=crawl_path, topics=topics)
    )
    audit = load_agent_output(state, AgentName.SEO_AUDIT) or {}
    keywords = load_agent_output(state, AgentName.KEYWORD_RESEARCH)

    async with transaction() as session:
        previous = await get_previous_agent_output(
            session, website_domain=state["site"], agent=NAME, exclude_run_id=args["run_id"]
        )
    active = [
        f"{r.get('action')}: {r.get('proposed_title') or r.get('target_keyword')}"
        for r in (previous or {}).get("recommendations", [])
    ]

    evidence = {
        "keyword_opportunities": (keywords or {}).get("opportunities", [])[:25],
        "page_matches": (matches.data or {}).get("matches", []),
        "page_inventory": _inventory(crawl_path),
        "technical_findings": [
            {k: f.get(k) for k in ("issue_type", "severity", "affected_count", "example_urls")}
            for f in audit.get("findings", [])[:15]
        ],
    }
    outcome = await run_agent(
        AgentName.CONTENT_STRATEGY,
        state,
        evidence=evidence,
        schema=ContentStrategyOutput,
        prompt_vars={"active_recommendations": "\n".join(active)} if active else None,
    )
    return {
        "task_status": {NAME: outcome.status.value},
        "artifacts": {"page_matches": matches.output_path, NAME: outcome.output_path},
        "data_gaps": gaps,
        "errors": [f"{NAME}: {outcome.error}"] if outcome.error else [],
    }
