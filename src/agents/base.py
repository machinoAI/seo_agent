"""Shared agent runtime.

Each agent node: (1) runs its tools deterministically (every call recorded), (2) passes
the compact evidence to its LLM with the agent's YAML prompt, (3) validates the JSON
reply against a Pydantic schema — retrying once with a correction prompt (doc §4.4),
and (4) saves the result to the run folder and the database.
"""

import asyncio
import functools
import json
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import BaseModel, BeforeValidator, ConfigDict, ValidationError

from src.config import AgentName
from src.llm import LLMSpec, create_chat_model, resolve_llm_spec
from src.llm.pricing import PRICES_AS_OF, estimate_cost, price_for
from src.observability.logging import bind_context, get_logger
from src.orchestration.state import TaskStatus, WorkflowState
from src.persistence.database import transaction
from src.persistence.output_store import get_output_store, read_recorded
from src.persistence.repositories import save_agent_result
from src.prompts import load_prompt, render_snippet

logger = get_logger(__name__)

MAX_ATTEMPTS = 2  # first reply + one correction
MAX_EVIDENCE_CHARS = 60_000
_FENCED = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)

NodeFn = Callable[[WorkflowState], Awaitable[dict[str, Any]]]


class AgentOutputError(ValueError):
    """The model did not return valid JSON for the agent's schema."""


def _lower(value: Any) -> Any:
    return value.strip().lower() if isinstance(value, str) else value


# Use in output schemas so "High" / " high " validate as "high".
Lowered = BeforeValidator(_lower)


class AgentSchema(BaseModel):
    """Base for agent output schemas: tolerate extra keys, validate the ones we use."""

    model_config = ConfigDict(extra="ignore")


@dataclass
class AgentOutcome:
    status: TaskStatus
    output: dict[str, Any] | None
    output_path: str
    error: str | None


# ── Helpers ──────────────────────────────────────────────────────────────────


def tool_args(state: WorkflowState) -> dict[str, Any]:
    """Common ToolRequest fields for this run."""
    return {"run_id": uuid.UUID(state["run_id"]), "site": state["site"]}


def message_text(message: BaseMessage) -> str:
    """Text of a chat reply, ignoring thinking/reasoning blocks."""
    content = message.content
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts)


def extract_json(text: str) -> Any:
    """Parse the JSON object in a reply, tolerating code fences or stray prose."""
    for candidate in [*(m.group(1) for m in _FENCED.finditer(text)), text]:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(candidate[start : end + 1])
            except ValueError:
                continue
    raise AgentOutputError("No JSON object found in the reply.")


def compact_json(evidence: Any, max_chars: int = MAX_EVIDENCE_CHARS) -> str:
    text = json.dumps(evidence, ensure_ascii=False, default=str, separators=(",", ":"))
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + " …[evidence truncated to fit the model context]"


def load_agent_output(state: WorkflowState, agent: AgentName) -> dict[str, Any] | None:
    """Validated output of an earlier agent in this run, or None if it failed/was skipped."""
    path = state.get("artifacts", {}).get(agent.value)
    if not path:
        return None
    output = read_recorded(path).get("output")
    return output if isinstance(output, dict) else None


def guarded_node(name: str) -> Callable[[NodeFn], NodeFn]:
    """Never let one step crash the run: unexpected errors mark the step failed."""

    def decorator(fn: NodeFn) -> NodeFn:
        @functools.wraps(fn)
        async def wrapper(state: WorkflowState) -> dict[str, Any]:
            bind_context(run_id=state.get("run_id"), site=state.get("site"), step=name)
            logger.info("step_started")
            try:
                update = await fn(state)
            except Exception as exc:
                logger.exception("step_crashed")
                return {
                    "task_status": {name: TaskStatus.FAILED.value},
                    "errors": [f"{name}: {type(exc).__name__}: {str(exc)[:300]}"],
                }
            logger.info("step_finished", status=update.get("task_status", {}).get(name))
            return update

        return wrapper

    return decorator


# ── LLM call with validation ─────────────────────────────────────────────────


def add_usage(totals: dict[str, int], message: BaseMessage) -> None:
    """Add one reply's token usage (LangChain `usage_metadata`) to running totals."""
    meta = getattr(message, "usage_metadata", None) or {}
    totals["llm_calls"] = totals.get("llm_calls", 0) + 1
    totals["input_tokens"] = totals.get("input_tokens", 0) + int(meta.get("input_tokens", 0))
    totals["output_tokens"] = totals.get("output_tokens", 0) + int(meta.get("output_tokens", 0))
    cached = (meta.get("input_token_details") or {}).get("cache_read", 0) or 0
    reasoning = (meta.get("output_token_details") or {}).get("reasoning", 0) or 0
    totals["cached_input_tokens"] = totals.get("cached_input_tokens", 0) + int(cached)
    totals["reasoning_tokens"] = totals.get("reasoning_tokens", 0) + int(reasoning)


async def _invoke_validated(
    model: BaseChatModel,
    messages: list[BaseMessage],
    schema: type[BaseModel],
    usage: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Call the model, validate the JSON reply; one correction retry. Token usage of every
    call (including failed attempts) is added to `usage`."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        reply = await model.ainvoke(messages)
        if usage is not None:
            add_usage(usage, reply)
        try:
            parsed = schema.model_validate(extract_json(message_text(reply)))
            return parsed.model_dump(mode="json")
        except (AgentOutputError, ValidationError) as exc:
            if attempt == MAX_ATTEMPTS:
                raise AgentOutputError(f"Invalid output after {attempt} attempts: {exc}") from exc
            logger.warning("agent_output_invalid", attempt=attempt, error=str(exc)[:300])
            correction = render_snippet("output_correction", error=str(exc)[:2000])
            messages = [*messages, reply, HumanMessage(content=correction)]
    raise AssertionError("unreachable")  # pragma: no cover


async def run_agent(
    agent: AgentName,
    state: WorkflowState,
    *,
    evidence: dict[str, Any],
    schema: type[BaseModel],
    prompt_vars: dict[str, str] | None = None,
) -> AgentOutcome:
    """Run one agent's LLM step, then persist the outcome (file + database)."""
    started_at = datetime.now(UTC)
    prompt = load_prompt(agent)
    spec: LLMSpec | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    tokens: dict[str, int] = {}
    try:
        overrides = state.get("options", {}).get("llm", {})
        spec = resolve_llm_spec(agent, **overrides)
        messages = prompt.render(
            site=state["site"],
            run_date=state["run_date"],
            evidence=compact_json(evidence),
            **(prompt_vars or {}),
        )
        output = await _invoke_validated(create_chat_model(spec), messages, schema, tokens)
    except Exception as exc:
        logger.exception("agent_failed", agent=agent.value)
        error = f"{type(exc).__name__}: {str(exc)[:500]}"

    status = TaskStatus.SUCCEEDED if output is not None else TaskStatus.FAILED
    completed_at = datetime.now(UTC)
    llm = spec.model_dump(mode="json") if spec else None
    usage: dict[str, Any] = {**tokens}
    if spec and tokens.get("llm_calls"):
        usage["cost_usd"] = estimate_cost(spec.model, tokens, completed_at.date())
        price = price_for(spec.model, completed_at.date())
        usage["price_source"] = f"{price[1]} ({PRICES_AS_OF})" if price else "unknown model"
    payload = {
        "agent": agent.value,
        "status": status.value,
        "prompt_ref": prompt.ref,
        "llm": llm,
        "usage": usage,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "evidence_chars": len(compact_json(evidence, max_chars=10**9)),
        "output": output,
        "error": error,
    }
    path = await asyncio.to_thread(
        get_output_store().save,
        site=state["site"],
        run_id=uuid.UUID(state["run_id"]),
        tool=f"agent_{agent.value}",
        request_id=uuid.uuid4(),
        status=status.value,
        recorded_at=completed_at,
        payload=payload,
    )
    async with transaction() as session:
        await save_agent_result(
            session,
            run_id=uuid.UUID(state["run_id"]),
            agent=agent.value,
            status=status.value,
            started_at=started_at,
            prompt_ref=prompt.ref,
            provider=spec.provider.value if spec else None,
            model=spec.model if spec else None,
            reasoning=spec.reasoning if spec else None,
            output=output,
            output_path=str(path),
            error=error,
            usage=usage or None,
        )
    return AgentOutcome(status=status, output=output, output_path=str(path), error=error)
