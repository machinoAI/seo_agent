"""Request and response models for the HTTP API."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from seo_agent.config import LLMProvider


class RunCreate(BaseModel):
    site: str = Field(examples=["machinoai.in"], description="Domain or URL to analyse")
    max_pages: int | None = Field(default=None, ge=1, le=5000, description="Crawl page budget")
    provider: LLMProvider | None = Field(default=None, description="LLM provider for this run")
    model: str | None = Field(default=None, description="LLM model for this run")
    reasoning: str | None = Field(default=None, description="none | low | medium | high | ...")


class RunCreated(BaseModel):
    run_id: uuid.UUID
    site: str
    status: str
    output_dir: str


class AgentResultOut(BaseModel):
    agent: str
    status: str
    provider: str | None
    model: str | None
    prompt_ref: str | None
    output_path: str | None
    error: str | None
    completed_at: datetime | None


class RunDetail(BaseModel):
    run_id: uuid.UUID
    site: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    output_dir: str | None
    report_path: str | None
    summary: dict[str, Any] | None
    error: str | None
    agents: list[AgentResultOut]
