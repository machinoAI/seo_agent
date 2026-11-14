"""Run lifecycle shared by the CLI runner and the API: create, execute, resume."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

from seo_agent.observability.logging import bind_context, get_logger
from seo_agent.orchestration.graph import VALIDATE, build_graph, open_checkpointer
from seo_agent.orchestration.state import STATE_VERSION, TaskStatus, WorkflowState
from seo_agent.persistence.database import transaction
from seo_agent.persistence.models import RunStatus
from seo_agent.persistence.output_store import get_output_store
from seo_agent.persistence.repositories import (
    create_run,
    get_or_create_website,
    get_run,
    update_run,
)

logger = get_logger(__name__)
RECURSION_LIMIT = 30


@dataclass
class PreparedRun:
    run_id: uuid.UUID
    website_id: uuid.UUID
    site: str
    output_dir: str
    options: dict[str, Any]


async def prepare_run(site: str, options: dict[str, Any] | None = None) -> PreparedRun:
    """Create the website (if new), a pending run record and the run's output folder."""
    run_id = uuid.uuid4()
    options = {k: v for k, v in (options or {}).items() if v not in (None, {}, [])}
    run_dir = get_output_store().run_dir(site, run_id, datetime.now(UTC))
    run_dir.mkdir(parents=True, exist_ok=True)
    for attempt in (1, 2):
        try:
            async with transaction() as session:
                website = await get_or_create_website(session, site)
                await create_run(
                    session, run_id=run_id, website_id=website.id, output_dir=str(run_dir),
                    options=options,
                )
                website_id = website.id
            break
        except IntegrityError:
            if attempt == 2:
                raise
            # Another request created the same website at the same moment; it exists now.
    return PreparedRun(run_id, website_id, site, str(run_dir), options)


async def load_run(run_id: uuid.UUID) -> PreparedRun:
    """Look up an existing run (for --resume)."""
    async with transaction() as session:
        run = await get_run(session, run_id)
        if run is None:
            raise LookupError(f"Run {run_id} not found")
        return PreparedRun(
            run.id, run.website_id, run.website.domain, run.output_dir or "", run.options or {}
        )


def _final_status(task_status: dict[str, str]) -> RunStatus:
    if task_status.get(VALIDATE) != TaskStatus.SUCCEEDED.value:
        return RunStatus.FAILED
    if all(s == TaskStatus.SUCCEEDED.value for s in task_status.values()):
        return RunStatus.COMPLETED
    return RunStatus.PARTIAL


async def execute_workflow(run: PreparedRun, *, resume: bool = False) -> WorkflowState:
    """Run (or resume) the LangGraph workflow and record the outcome on the run."""
    bind_context(run_id=str(run.run_id), site=run.site)
    initial: WorkflowState = {
        "state_version": STATE_VERSION,
        "run_id": str(run.run_id),
        "website_id": str(run.website_id),
        "site": run.site,
        "run_date": datetime.now(UTC).date().isoformat(),
        "output_dir": run.output_dir,
        "options": run.options,
        "task_status": {},
        "sources": {},
        "artifacts": {},
        "data_gaps": [],
        "errors": [],
    }
    config: dict[str, Any] = {
        "configurable": {"thread_id": str(run.run_id)},
        "recursion_limit": RECURSION_LIMIT,
    }

    async with transaction() as session:
        await update_run(session, run.run_id, status=RunStatus.RUNNING)
    try:
        async with open_checkpointer() as checkpointer:
            graph = build_graph().compile(checkpointer=checkpointer)
            graph_input: WorkflowState | None = initial
            if resume and (await graph.aget_state(config)).values:
                graph_input = None  # continue from the last checkpoint
            final: WorkflowState = await graph.ainvoke(graph_input, config)
    except BaseException as exc:  # includes Ctrl+C: the run can be resumed later
        async with transaction() as session:
            await update_run(
                session, run.run_id, status=RunStatus.FAILED,
                error=f"{type(exc).__name__}: {str(exc)[:500]} (resume with --resume)",
            )
        raise

    task_status = final.get("task_status", {})
    status = _final_status(task_status)
    summary = {
        "task_status": task_status,
        "pages_crawled": final.get("pages_crawled"),
        "cost": final.get("cost"),
        "data_gaps": final.get("data_gaps", []),
        "errors": final.get("errors", []),
    }
    async with transaction() as session:
        await update_run(
            session,
            run.run_id,
            status=status,
            summary=summary,
            report_path=final.get("report_path") or None,
            error="; ".join(final.get("errors", []))[:2000] or None,
        )
    logger.info("run_finished", status=status.value)
    return final
