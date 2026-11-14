"""The LangGraph workflow (design doc §6) and its checkpointer.

    validate_site ─┬─ site unreachable ─────────────────────────────► END
                   └─► seo_audit ─┬─ no pages crawled ─► skip_downstream ─┐
                                  └─► keyword_research ─► content_strategy ┴─►
                                      performance_reporting ─► END

Every node marks itself succeeded/failed/skipped and the run continues where
dependencies allow. Checkpoints go to a local SQLite file (or PostgreSQL in production),
so an interrupted run can be resumed with the same run id.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from seo_agent.agents import content_strategy, keyword_research, performance_reporting, seo_audit
from seo_agent.agents.base import guarded_node
from seo_agent.config import get_settings
from seo_agent.orchestration.state import TaskStatus, WorkflowState
from seo_agent.tools.base import ToolRequest, ToolStatus
from seo_agent.tools.domain import validate_domain

VALIDATE = "validate_site"


@guarded_node(VALIDATE)
async def validate_site(state: WorkflowState) -> dict[str, Any]:
    request = ToolRequest(run_id=uuid.UUID(state["run_id"]), site=state["site"])
    result = await validate_domain(request)
    artifacts = {VALIDATE: result.output_path or ""}
    if result.status is not ToolStatus.SUCCESS or not result.data:
        message = result.error.message if result.error else "unknown error"
        return {
            "task_status": {VALIDATE: TaskStatus.FAILED.value},
            "artifacts": artifacts,
            "errors": [f"Site validation failed: {message}"],
        }
    return {
        "task_status": {VALIDATE: TaskStatus.SUCCEEDED.value},
        "artifacts": artifacts,
        "start_url": result.data["start_url"],
        "allowed_hosts": result.data["allowed_hosts"],
    }


def _after_validation(state: WorkflowState) -> str:
    ok = state.get("task_status", {}).get(VALIDATE) == TaskStatus.SUCCEEDED.value
    return "continue" if ok else "stop"


def _after_audit(state: WorkflowState) -> str:
    if state.get("pages_crawled", 0) > 0 and "crawl" in state.get("artifacts", {}):
        return "continue"
    return "report"


async def _skip_downstream(state: WorkflowState) -> dict[str, Any]:
    """Recorded when no pages could be crawled: keyword and content steps can't run."""
    return {
        "task_status": {
            keyword_research.NAME: TaskStatus.SKIPPED.value,
            content_strategy.NAME: TaskStatus.SKIPPED.value,
        },
        "data_gaps": ["No pages were crawled, so keyword and content analysis were skipped."],
    }


def build_graph() -> StateGraph:
    graph = StateGraph(WorkflowState)
    graph.add_node(VALIDATE, validate_site)
    graph.add_node(seo_audit.NAME, seo_audit.node)
    graph.add_node(keyword_research.NAME, keyword_research.node)
    graph.add_node(content_strategy.NAME, content_strategy.node)
    graph.add_node("skip_downstream", _skip_downstream)
    graph.add_node(performance_reporting.NAME, performance_reporting.node)

    graph.add_edge(START, VALIDATE)
    graph.add_conditional_edges(
        VALIDATE, _after_validation, {"continue": seo_audit.NAME, "stop": END}
    )
    graph.add_conditional_edges(
        seo_audit.NAME,
        _after_audit,
        {"continue": keyword_research.NAME, "report": "skip_downstream"},
    )
    graph.add_edge(keyword_research.NAME, content_strategy.NAME)
    graph.add_edge(content_strategy.NAME, performance_reporting.NAME)
    graph.add_edge("skip_downstream", performance_reporting.NAME)
    graph.add_edge(performance_reporting.NAME, END)
    return graph


@asynccontextmanager
async def open_checkpointer() -> AsyncIterator["BaseCheckpointSaver[Any]"]:
    """SQLite checkpoints locally (no server); PostgreSQL when DATABASE_URL points there."""
    settings = get_settings()
    target = settings.checkpoint_target
    if settings.is_sqlite:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        Path(target).parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(target) as saver:
            yield saver
        return
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    except ImportError as exc:  # pragma: no cover - depends on installed extras
        raise RuntimeError(
            'A PostgreSQL DATABASE_URL needs the driver: pip install -e ".[postgres]"'
        ) from exc
    async with AsyncPostgresSaver.from_conn_string(target) as saver:
        await saver.setup()
        yield saver
