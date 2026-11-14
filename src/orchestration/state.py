"""Versioned LangGraph workflow state (design doc §6.4).

The state stays small and JSON-serializable so checkpoints are cheap: large data (crawl
results, agent outputs) lives in the run folder and is referenced by file path in
`artifacts`. Fields that several nodes append to use reducers.
"""

import operator
from enum import StrEnum
from typing import Annotated, Any, TypedDict

STATE_VERSION = 1


def merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Reducer: shallow-merge dict updates from nodes."""
    return {**left, **right}


class TaskStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowState(TypedDict, total=False):
    state_version: int
    run_id: str
    website_id: str
    site: str
    run_date: str
    output_dir: str
    options: dict[str, Any]  # max_pages, llm overrides {provider, model, reasoning}

    # Set by validate_site
    start_url: str
    allowed_hosts: list[str]
    # Set by seo_audit
    pages_crawled: int
    coverage: dict[str, Any]  # sitemap size vs pages fetched/analysed
    # Set by performance_reporting
    report_path: str
    cost: dict[str, Any]  # LLM token totals and estimated USD cost for the run

    sources: Annotated[dict[str, str], merge_dicts]  # data source -> status line for the report
    task_status: Annotated[dict[str, str], merge_dicts]
    artifacts: Annotated[dict[str, str], merge_dicts]  # name -> JSON file in the run folder
    data_gaps: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]
