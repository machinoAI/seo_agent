"""Database access for websites, workflow runs and agent results.

Callers own the transaction (`async with transaction() as session:`); functions here
only read and stage changes. Writes are idempotent where retries may repeat them.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from seo_agent.persistence.models import AgentResult, RunStatus, Website, WorkflowRun, utcnow


async def get_or_create_website(session: AsyncSession, domain: str) -> Website:
    website = await session.scalar(select(Website).where(Website.domain == domain))
    if website is None:
        website = Website(domain=domain)
        session.add(website)
        await session.flush()
    return website


async def create_run(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    website_id: uuid.UUID,
    output_dir: str,
    options: dict[str, Any],
    workflow_type: str = "initial",
) -> WorkflowRun:
    run = WorkflowRun(
        id=run_id,
        website_id=website_id,
        workflow_type=workflow_type,
        status=RunStatus.PENDING,
        output_dir=output_dir,
        options=options,
    )
    session.add(run)
    await session.flush()
    return run


async def get_run(session: AsyncSession, run_id: uuid.UUID) -> WorkflowRun | None:
    return await session.scalar(
        select(WorkflowRun)
        .where(WorkflowRun.id == run_id)
        .options(selectinload(WorkflowRun.agent_results), selectinload(WorkflowRun.website))
    )


async def get_previous_run(
    session: AsyncSession, *, website_domain: str, exclude_run_id: uuid.UUID
) -> WorkflowRun | None:
    """Most recent finished run for the same website (for history and comparisons)."""
    return await session.scalar(
        select(WorkflowRun)
        .join(Website, WorkflowRun.website_id == Website.id)
        .where(
            Website.domain == website_domain,
            WorkflowRun.id != exclude_run_id,
            WorkflowRun.status.in_([RunStatus.COMPLETED, RunStatus.PARTIAL]),
        )
        .order_by(WorkflowRun.started_at.desc())
        .limit(1)
    )


async def get_previous_agent_output(
    session: AsyncSession, *, website_domain: str, agent: str, exclude_run_id: uuid.UUID
) -> dict[str, Any] | None:
    """Latest successful output of `agent` from an earlier run of the same website."""
    output: dict[str, Any] | None = await session.scalar(
        select(AgentResult.output)
        .join(WorkflowRun, AgentResult.run_id == WorkflowRun.id)
        .join(Website, WorkflowRun.website_id == Website.id)
        .where(
            Website.domain == website_domain,
            AgentResult.agent == agent,
            AgentResult.status == "succeeded",
            AgentResult.run_id != exclude_run_id,
        )
        .order_by(AgentResult.completed_at.desc())
        .limit(1)
    )
    return output


async def update_run(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    status: RunStatus,
    error: str | None = None,
    summary: dict[str, Any] | None = None,
    report_path: str | None = None,
) -> None:
    run = await session.get(WorkflowRun, run_id)
    if run is None:
        raise LookupError(f"Workflow run {run_id} not found")
    run.status = status
    run.error = error
    if summary is not None:
        run.summary = summary
    if report_path is not None:
        run.report_path = report_path
    if status in (RunStatus.COMPLETED, RunStatus.PARTIAL, RunStatus.FAILED):
        run.completed_at = utcnow()


async def save_agent_result(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    agent: str,
    status: str,
    started_at: datetime,
    prompt_ref: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    reasoning: str | None = None,
    output: dict[str, Any] | None = None,
    output_path: str | None = None,
    error: str | None = None,
    usage: dict[str, Any] | None = None,
) -> None:
    """Insert or replace the result for (run, agent), so a retried node never duplicates."""
    row = await session.scalar(
        select(AgentResult).where(AgentResult.run_id == run_id, AgentResult.agent == agent)
    )
    if row is None:
        row = AgentResult(run_id=run_id, agent=agent)
        session.add(row)
    row.status = status
    row.prompt_ref = prompt_ref
    row.provider = provider
    row.model = model
    row.reasoning = reasoning
    row.output = output
    row.output_path = output_path
    row.error = error
    row.usage = usage
    row.started_at = started_at
    row.completed_at = utcnow()
