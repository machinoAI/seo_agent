"""Submit a site for analysis and follow the run.

POST /runs validates the domain (syntax + public DNS, design doc §12.1), records the run
and starts the workflow in the background. GET /runs/{run_id} returns its progress.
"""

import asyncio
import hmac
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status

from seo_agent.api.schemas import AgentResultOut, RunCreate, RunCreated, RunDetail
from seo_agent.config import AgentName, get_settings, normalize_site
from seo_agent.llm import LLMConfigurationError, resolve_llm_spec
from seo_agent.observability.logging import get_logger
from seo_agent.orchestration.workflow import PreparedRun, execute_workflow, prepare_run
from seo_agent.persistence.database import transaction
from seo_agent.persistence.repositories import get_run
from seo_agent.tools.http import FetchError, SafeHttpClient

def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    """When API_KEY is set, every /runs call must send it in the X-API-Key header."""
    expected = get_settings().api_key
    if expected is None:
        return
    if x_api_key is None or not hmac.compare_digest(x_api_key, expected.get_secret_value()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid X-API-Key")


router = APIRouter(prefix="/runs", tags=["runs"], dependencies=[Depends(require_api_key)])
logger = get_logger(__name__)

MAX_CONCURRENT_RUNS = 2
_run_slots = asyncio.Semaphore(MAX_CONCURRENT_RUNS)


async def _execute(run: PreparedRun) -> None:
    async with _run_slots:
        try:
            await execute_workflow(run)
        except Exception:
            logger.exception("background_run_failed", run_id=str(run.run_id))


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def start_run(body: RunCreate, background: BackgroundTasks) -> RunCreated:
    try:
        site = normalize_site(body.site)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    llm = {"provider": body.provider, "model": body.model, "reasoning": body.reasoning}
    llm = {k: v for k, v in llm.items() if v is not None}
    try:
        for agent in AgentName:
            resolve_llm_spec(agent, **llm)
    except LLMConfigurationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    async with SafeHttpClient.from_settings(get_settings()) as client:
        try:
            await client.resolve_public(site)  # refuse private/unresolvable hosts up front
        except FetchError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    run = await prepare_run(site, {"max_pages": body.max_pages, "llm": llm})
    background.add_task(_execute, run)
    return RunCreated(run_id=run.run_id, site=site, status="pending", output_dir=run.output_dir)


@router.get("/{run_id}")
async def get_run_detail(run_id: uuid.UUID) -> RunDetail:
    async with transaction() as session:
        run = await get_run(session, run_id)
        if run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
        return RunDetail(
            run_id=run.id,
            site=run.website.domain,
            status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            output_dir=run.output_dir,
            report_path=run.report_path,
            summary=run.summary,
            error=run.error,
            agents=[
                AgentResultOut(
                    agent=r.agent,
                    status=r.status,
                    provider=r.provider,
                    model=r.model,
                    prompt_ref=r.prompt_ref,
                    output_path=r.output_path,
                    error=r.error,
                    completed_at=r.completed_at,
                )
                for r in run.agent_results
            ],
        )
