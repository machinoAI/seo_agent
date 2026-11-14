"""LLM token prices (USD per 1M tokens) and cost estimates for the report.

Prices are the providers' standard-tier list prices as of 2026-11-14 (official pricing
pages). Promotional prices switch to the regular price after their end date. Override or
add models with LLM_PRICES in .env, e.g. LLM_PRICES={"my-model": [1.0, 0.1, 5.0]}
(input, cached input, output). Costs are estimates: they exclude cache-write charges and
long-prompt surcharges, and providers bill from their own meters.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from seo_agent.config import get_settings

PRICES_AS_OF = "2026-11-14"


@dataclass(frozen=True)
class Price:
    input: float
    cached_input: float
    output: float


@dataclass(frozen=True)
class PriceEntry:
    price: Price
    promo_until: date | None = None  # last day of a promotional price
    regular: Price | None = None  # price after the promotion


def _p(i: float, c: float, o: float) -> Price:
    return Price(i, c, o)


PRICES: dict[str, PriceEntry] = {
    # OpenAI
    "gpt-6-astra": PriceEntry(_p(10.00, 1.00, 50.00)),
    "gpt-6.1-sol": PriceEntry(_p(2.00, 0.10, 10.00)),
    "gpt-6-sol": PriceEntry(_p(2.00, 0.20, 10.00)),
    "gpt-6.1-terra": PriceEntry(_p(1.00, 0.05, 5.00)),
    "gpt-6-luna": PriceEntry(_p(0.10, 0.01, 0.50)),
    "gpt-5.6-sol": PriceEntry(_p(4.00, 0.40, 20.00), date(2026, 11, 30), _p(5.00, 0.50, 30.00)),
    "gpt-5.6-terra": PriceEntry(_p(2.00, 0.20, 12.00)),
    "gpt-5.6-luna": PriceEntry(_p(0.20, 0.02, 1.20)),
    "gpt-5.5": PriceEntry(_p(5.00, 0.50, 30.00)),
    "gpt-5.4": PriceEntry(_p(2.50, 0.25, 15.00)),
    "gpt-5.4-mini": PriceEntry(_p(0.75, 0.075, 4.50)),
    # Anthropic
    "claude-opus-5-5": PriceEntry(_p(4.00, 0.20, 20.00)),
    "claude-sonnet-5-5": PriceEntry(_p(2.00, 0.10, 10.00)),
    "claude-haiku-5-5": PriceEntry(_p(0.10, 0.01, 0.50)),  # prompts up to 100K tokens
    "claude-fable-5-1": PriceEntry(_p(10.00, 0.25, 50.00)),
    # Google Gemini
    "gemini-4-argon": PriceEntry(_p(2.00, 0.10, 10.00), date(2026, 11, 30), _p(4.00, 0.20, 20.00)),
    "gemini-3.8-flash": PriceEntry(_p(0.75, 0.075, 3.75), date(2026, 12, 31), _p(1.50, 0.15, 7.50)),
    "gemini-3.6-flash": PriceEntry(_p(0.75, 0.075, 3.75), date(2026, 12, 31), _p(1.50, 0.15, 7.50)),
    "gemini-3.5-flash-lite": PriceEntry(_p(0.30, 0.03, 2.50)),
    "gemini-3.1-pro-preview": PriceEntry(_p(2.00, 0.20, 12.00)),  # prompts up to 200K tokens
    # Inception (Mercury)
    "mercury-3": PriceEntry(_p(0.10, 0.01, 0.35)),  # launch discount; regular 0.20 / 0.02 / 0.70
    "mercury-2.5": PriceEntry(_p(0.20, 0.02, 0.75)),
    "mercury-2": PriceEntry(_p(0.25, 0.025, 0.75)),
}


def price_for(model: str, on: date | None = None) -> tuple[Price, str] | None:
    """Price for `model` on a date, and where it came from ('override' or 'table')."""
    override = get_settings().llm_prices.get(model)
    if override and len(override) >= 2:
        # [input, cached_input, output] or [input, output] (cached billed as input)
        i, c, o = override[:3] if len(override) >= 3 else (override[0], override[0], override[1])
        return Price(i, c, o), "override"
    entry = PRICES.get(model) or next(
        (e for name, e in PRICES.items() if model.startswith(f"{name}-")), None  # snapshots
    )
    if entry is None:
        return None
    if entry.promo_until and entry.regular and on and on > entry.promo_until:
        return entry.regular, "table"
    return entry.price, "table"


def estimate_cost(model: str, usage: dict[str, Any], on: date | None = None) -> float | None:
    """USD cost of the recorded token usage, or None when the model's price is unknown."""
    found = price_for(model, on)
    if found is None:
        return None
    price, _ = found
    cached = min(usage.get("cached_input_tokens", 0), usage.get("input_tokens", 0))
    uncached = usage.get("input_tokens", 0) - cached
    cost = (
        uncached * price.input
        + cached * price.cached_input
        + usage.get("output_tokens", 0) * price.output
    ) / 1_000_000
    return round(cost, 6)
