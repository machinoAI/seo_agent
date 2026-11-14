from datetime import date
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from seo_agent.agents.base import add_usage
from seo_agent.config import Settings
from seo_agent.llm import pricing
from seo_agent.tools.reporting import cost_summary, render_markdown


@pytest.fixture(autouse=True)
def no_price_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings.model_construct(llm_prices={})
    monkeypatch.setattr(pricing, "get_settings", lambda: settings)


def test_cost_uses_input_cached_and_output_prices() -> None:
    usage = {"input_tokens": 1_000_000, "cached_input_tokens": 200_000, "output_tokens": 100_000}
    # gpt-6-luna: 0.10 input, 0.01 cached, 0.50 output per 1M tokens
    assert pricing.estimate_cost("gpt-6-luna", usage) == pytest.approx(0.08 + 0.002 + 0.05)


def test_promotional_price_ends_on_its_date() -> None:
    usage = {"input_tokens": 1_000_000, "output_tokens": 0}
    assert pricing.estimate_cost("gpt-5.6-sol", usage, date(2026, 11, 30)) == 4.0
    assert pricing.estimate_cost("gpt-5.6-sol", usage, date(2026, 12, 1)) == 5.0


def test_unknown_model_has_no_price_but_override_adds_one(monkeypatch: pytest.MonkeyPatch) -> None:
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    assert pricing.estimate_cost("my-model", usage) is None

    settings = Settings.model_construct(llm_prices={"my-model": [1.0, 2.0]})
    monkeypatch.setattr(pricing, "get_settings", lambda: settings)
    assert pricing.estimate_cost("my-model", usage) == 3.0


def test_dated_snapshot_uses_base_model_price() -> None:
    assert pricing.price_for("gpt-6-luna-2026-10-01") == pricing.price_for("gpt-6-luna")


def test_add_usage_sums_langchain_usage_metadata() -> None:
    totals: dict[str, int] = {}
    reply: Any = AIMessage(content="{}")
    reply.usage_metadata = {
        "input_tokens": 1200, "output_tokens": 300,
        "input_token_details": {"cache_read": 200},
        "output_token_details": {"reasoning": 120},
    }
    add_usage(totals, reply)
    add_usage(totals, AIMessage(content="no usage reported"))

    assert totals == {"llm_calls": 2, "input_tokens": 1200, "output_tokens": 300,
                      "cached_input_tokens": 200, "reasoning_tokens": 120}


AGENTS = [
    {"agent": "seo_audit", "status": "succeeded", "model": "gpt-6-luna",
     "usage": {"llm_calls": 1, "input_tokens": 40_000, "output_tokens": 6_000, "cost_usd": 0.007}},
    {"agent": "content_strategy", "status": "succeeded", "model": "gpt-6-luna",
     "usage": {"llm_calls": 2, "input_tokens": 30_000, "output_tokens": 9_000, "cost_usd": 0.0075}},
]


def test_cost_summary_and_report_show_total_on_top_and_per_agent() -> None:
    totals = cost_summary(AGENTS)
    assert totals["llm_calls"] == 3
    assert totals["cost_usd"] == 0.0145

    markdown = render_markdown(
        site="machinoai.in", run_id="r1", run_date="2026-11-14", report=None, audit=None,
        keywords=None, content=None, agents=AGENTS, data_gaps=[],
    )
    top = markdown.split("## Executive summary")[0]
    assert "**Cost:** **$0.0145** estimated LLM spend · 3 calls on gpt-6-luna" in top
    assert "70,000 input tokens" in top
    run_details = markdown.split("## Run details")[1]
    assert "| seo_audit |" in run_details and "$0.0070" in run_details
    assert "| **Total** |" in run_details and "**$0.0145**" in run_details
