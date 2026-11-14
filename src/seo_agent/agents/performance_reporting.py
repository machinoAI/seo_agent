"""Agent 4 — Performance and Reporting (design doc §4.5, §15).

Consolidates every agent's output, coverage, data-source status and the previous run
(if any) into a prioritized action plan and report, then renders `report.md` plus CSV
exports (action plan, URL-level findings, page inventory) with `generate_report`.
The Markdown report and CSVs are produced even if this agent's LLM step fails.
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
from seo_agent.config import AgentName
from seo_agent.orchestration.state import WorkflowState
from seo_agent.persistence.database import transaction
from seo_agent.persistence.output_store import read_result_data
from seo_agent.persistence.repositories import get_previous_run, get_run
from seo_agent.tools.reporting import ReportRequest, cost_summary, generate_report

NAME = AgentName.PERFORMANCE_REPORTING.value


class ReportPeriod(AgentSchema):
    start: str | None = None
    end: str | None = None
    compared_with: str | None = None


class ReportAlert(AgentSchema):
    type: str
    severity: Annotated[Literal["high", "medium", "low"], Lowered] = "medium"
    detail: str = ""


class ActionItem(AgentSchema):
    priority: Annotated[Literal["p1", "p2", "p3"], Lowered]
    action: str
    urls: list[str] = Field(default_factory=list)
    template: str | None = None
    owner: Annotated[Literal["developer", "content", "seo"], Lowered] = "developer"
    effort: Annotated[Literal["small", "medium", "large"], Lowered] = "medium"
    impact: Annotated[Literal["high", "medium", "low"], Lowered] = "medium"
    why: str = ""
    done_when: str = ""
    source: str = ""


class ReportOutput(AgentSchema):
    report_type: Annotated[Literal["baseline", "weekly", "monthly"], Lowered] = "baseline"
    period: ReportPeriod = Field(default_factory=ReportPeriod)
    is_complete: bool = False
    executive_summary: str
    action_plan: list[ActionItem] = Field(default_factory=list)
    sections: dict[str, str] = Field(default_factory=dict)
    alerts: list[ReportAlert] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)


def _pick(items: list[dict[str, Any]], keys: tuple[str, ...], limit: int) -> list[dict[str, Any]]:
    return [{k: item.get(k) for k in keys} for item in items[:limit]]


async def _agent_rows(run_id: Any) -> list[dict[str, Any]]:
    async with transaction() as session:
        run = await get_run(session, run_id)
    if run is None:
        return []
    return [
        {"agent": r.agent, "status": r.status, "provider": r.provider, "model": r.model,
         "reasoning": r.reasoning, "prompt_ref": r.prompt_ref, "usage": r.usage or {}}
        for r in run.agent_results
    ]


@guarded_node(NAME)
async def node(state: WorkflowState) -> dict[str, Any]:
    args = tool_args(state)
    artifacts = state.get("artifacts", {})
    audit = load_agent_output(state, AgentName.SEO_AUDIT)
    keywords = load_agent_output(state, AgentName.KEYWORD_RESEARCH)
    content = load_agent_output(state, AgentName.CONTENT_STRATEGY)
    technical_path = artifacts.get("technical_seo")
    technical = read_result_data(technical_path) if technical_path else None

    async with transaction() as session:
        previous = await get_previous_run(
            session, website_domain=state["site"], exclude_run_id=args["run_id"]
        )
    if previous is not None:
        report_type = "weekly"
        compared = f"This run against the previous run on {previous.started_at.date().isoformat()}."
        history: Any = {
            "previous_run_id": str(previous.id),
            "previous_run_date": previous.started_at.date().isoformat(),
            "previous_summary": previous.summary,
        }
    else:
        report_type = "baseline"
        compared = "No previous run; this report is the baseline."
        history = "No previous run; this is the first report for this site."

    evidence = {
        "run": {"task_status": state.get("task_status", {})},
        "coverage": state.get("coverage"),
        "data_sources": state.get("sources", {}),
        "template_health": (technical or {}).get("section_health", [])[:15],
        "seo_audit": audit and {
            "summary": audit.get("summary"),
            "findings": _pick(audit.get("findings", []),
                              ("issue_type", "severity", "status", "affected_count",
                               "example_urls", "evidence", "recommended_action", "owner",
                               "effort", "done_when"), 30),
            "performance": audit.get("performance", [])[:10],
        },
        "keyword_research": keywords and {
            "summary": keywords.get("summary"),
            "opportunities": _pick(keywords.get("opportunities", []),
                                   ("keyword", "category", "score", "confidence", "target_url",
                                    "metrics", "recommended_action"), 20),
            "cannibalization": keywords.get("cannibalization", [])[:10],
        },
        "content_strategy": content and {
            "summary": content.get("summary"),
            "recommendations": _pick(content.get("recommendations", []),
                                     ("action", "target_url", "target_keyword", "proposed_title",
                                      "priority", "effort", "expected_opportunity",
                                      "success_criteria"), 10),
        },
        "history": history,
        "data_gaps": state.get("data_gaps", []),
        "errors": state.get("errors", []),
    }
    outcome = await run_agent(
        AgentName.PERFORMANCE_REPORTING,
        state,
        evidence=evidence,
        schema=ReportOutput,
        prompt_vars={"report_type": report_type, "comparison_window": compared},
    )

    agents = await _agent_rows(args["run_id"])
    report = await asyncio.to_thread(generate_report, ReportRequest(
        **args,
        output_dir=state["output_dir"],
        run_date=state["run_date"],
        report=outcome.output,
        audit=audit,
        keywords=keywords,
        content=content,
        agents=agents,
        coverage=state.get("coverage") or {},
        sources=state.get("sources", {}),
        data_gaps=[*state.get("data_gaps", []), *state.get("errors", [])],
        crawl_path=artifacts.get("crawl"),
        technical_path=artifacts.get("technical_seo"),
    ))
    return {
        "task_status": {NAME: outcome.status.value},
        "artifacts": {NAME: outcome.output_path, "report": report.output_path},
        "report_path": (report.data or {}).get("report_path", ""),
        "cost": cost_summary(agents),
        "errors": [f"{NAME}: {outcome.error}"] if outcome.error else [],
    }
