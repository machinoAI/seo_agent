"""LangChain chat-model factory: one place that decides which LLM each agent uses.

Resolution order (later wins):
    1. Global defaults        LLM_PROVIDER, LLM_MODEL, LLM_REASONING, ...
    2. Per-agent overrides    <AGENT>_LLM_PROVIDER, <AGENT>_LLM_MODEL, ...
    3. Runtime overrides      get_chat_model(agent, provider=..., model=..., reasoning=...)

When a layer switches the provider without naming a model, that provider's default
model is used (a model name never carries over to a different provider).

Reasoning accepts portable levels (none | low | medium | high), mapped per provider,
any provider-native value (e.g. "xhigh", "max", "minimal", "instant"), or "default"
to send no reasoning parameter at all (use this for non-reasoning models).
"""

from functools import lru_cache
from typing import Any

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, ConfigDict, SecretStr, model_validator

from src.config import (
    AgentName,
    LLMProvider,
    Settings,
    get_agent_llm_overrides,
    get_settings,
)

DEFAULT_MODELS: dict[LLMProvider, str] = {
    LLMProvider.OPENAI: "gpt-5.5",
    LLMProvider.ANTHROPIC: "claude-sonnet-5-5",
    LLMProvider.GEMINI: "gemini-3.8-flash",
    LLMProvider.INCEPTION: "mercury-3",
}

PORTABLE_REASONING = frozenset({"default", "none", "low", "medium", "high"})

# Values each provider's API accepts natively. Support also varies by model;
# the provider API rejects a level the chosen model doesn't support.
NATIVE_REASONING: dict[LLMProvider, frozenset[str]] = {
    LLMProvider.OPENAI: frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "max"}),
    LLMProvider.ANTHROPIC: frozenset({"low", "medium", "high", "xhigh", "max"}),
    LLMProvider.GEMINI: frozenset({"minimal", "low", "medium", "high"}),
    LLMProvider.INCEPTION: frozenset({"instant", "low", "medium", "high"}),
}

# What the portable "none" level means per provider.
#   anthropic: None -> thinking is not enabled.
#   gemini:    Gemini 3+ can't switch thinking off; "low" is the lowest level all models accept.
_NONE_LEVEL: dict[LLMProvider, str | None] = {
    LLMProvider.OPENAI: "none",
    LLMProvider.ANTHROPIC: None,
    LLMProvider.GEMINI: "low",
    LLMProvider.INCEPTION: "instant",
}

_API_KEY_ENV = {
    LLMProvider.OPENAI: "OPENAI_API_KEY",
    LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
    LLMProvider.GEMINI: "GOOGLE_API_KEY",
    LLMProvider.INCEPTION: "INCEPTION_API_KEY",
}


class LLMConfigurationError(ValueError):
    """Invalid or incomplete LLM configuration (raised before any API call)."""


def _parse_provider(value: LLMProvider | str) -> LLMProvider:
    try:
        return LLMProvider(str(value).strip().lower())
    except ValueError:
        allowed = ", ".join(p.value for p in LLMProvider)
        raise LLMConfigurationError(
            f"Unknown LLM provider '{value}'. Use one of: {allowed}"
        ) from None


def _check_reasoning(provider: LLMProvider, reasoning: str) -> None:
    allowed = PORTABLE_REASONING | NATIVE_REASONING[provider]
    if reasoning not in allowed:
        raise LLMConfigurationError(
            f"Reasoning '{reasoning}' is not valid for provider '{provider}'. "
            f"Use one of: {', '.join(sorted(allowed))}"
        )


class LLMSpec(BaseModel):
    """Fully resolved, provider-specific LLM choice. Contains no secrets; safe to log."""

    model_config = ConfigDict(frozen=True)

    provider: LLMProvider
    model: str
    reasoning: str
    temperature: float | None = None
    max_tokens: int
    timeout_seconds: float
    max_retries: int

    @model_validator(mode="after")
    def _validate_reasoning(self) -> "LLMSpec":
        _check_reasoning(self.provider, self.reasoning)
        return self

    @property
    def native_reasoning(self) -> str | None:
        """Value sent to the provider API. None = send no reasoning/thinking parameter."""
        if self.reasoning == "default":
            return None
        if self.reasoning == "none":
            return _NONE_LEVEL[self.provider]
        return self.reasoning


# ── Resolution ───────────────────────────────────────────────────────────────


def resolve_llm_spec(
    agent: AgentName | None = None,
    *,
    provider: LLMProvider | str | None = None,
    model: str | None = None,
    reasoning: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> LLMSpec:
    """Merge global settings, per-agent overrides and runtime overrides into an `LLMSpec`."""
    settings = get_settings()
    resolved: dict[str, Any] = {
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "reasoning": settings.llm_reasoning,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
    }

    layers: list[dict[str, Any]] = []
    if agent is not None:
        layers.append(get_agent_llm_overrides(agent).model_dump(exclude_none=True))
    runtime = {
        "provider": provider,
        "model": model,
        "reasoning": reasoning,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    layers.append({k: v for k, v in runtime.items() if v is not None})

    for layer in layers:
        if "provider" in layer:
            layer["provider"] = _parse_provider(layer["provider"])
            if layer["provider"] != resolved["provider"]:
                resolved["model"] = None  # a model name never carries over to another provider
        resolved.update(layer)

    resolved_provider: LLMProvider = resolved["provider"]
    resolved_reasoning = str(resolved["reasoning"]).strip().lower()
    _check_reasoning(resolved_provider, resolved_reasoning)  # clear error before building

    return LLMSpec(
        provider=resolved_provider,
        model=resolved["model"] or DEFAULT_MODELS[resolved_provider],
        reasoning=resolved_reasoning,
        temperature=resolved["temperature"],
        max_tokens=resolved["max_tokens"],
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )


# ── Provider-specific constructor arguments ─────────────────────────────────


def _require_key(settings: Settings, provider: LLMProvider) -> SecretStr:
    key: SecretStr | None = getattr(settings, _API_KEY_ENV[provider].lower())
    if key is None:
        raise LLMConfigurationError(
            f"{_API_KEY_ENV[provider]} is not set but provider '{provider}' is selected."
        )
    return key


def chat_model_kwargs(spec: LLMSpec, settings: Settings | None = None) -> dict[str, Any]:
    """Constructor arguments for the provider's LangChain chat model class."""
    settings = settings or get_settings()
    api_key = _require_key(settings, spec.provider)
    effort = spec.native_reasoning
    common: dict[str, Any] = {
        "model": spec.model,
        "max_tokens": spec.max_tokens,
        "timeout": spec.timeout_seconds,
        "max_retries": spec.max_retries,
    }
    if spec.temperature is not None:
        common["temperature"] = spec.temperature

    kwargs: dict[str, Any]
    match spec.provider:
        case LLMProvider.OPENAI:
            kwargs = {**common, "api_key": api_key}
            if effort is not None:
                kwargs["reasoning_effort"] = effort

        case LLMProvider.INCEPTION:
            # OpenAI-compatible endpoint. Pin Chat Completions: Inception has no Responses API.
            kwargs = {
                **common,
                "api_key": api_key,
                "base_url": settings.inception_base_url,
                "use_responses_api": False,
            }
            if effort is not None:
                kwargs["reasoning_effort"] = effort

        case LLMProvider.ANTHROPIC:
            kwargs = {**common, "api_key": api_key}
            if effort is not None:
                if spec.temperature is not None:
                    raise LLMConfigurationError(
                        "Anthropic does not accept a custom temperature while thinking is on. "
                        "Leave the temperature blank or set reasoning to 'none'."
                    )
                kwargs["thinking"] = {"type": "adaptive"}
                kwargs["effort"] = effort  # sent as output_config.effort

        case LLMProvider.GEMINI:
            kwargs = {**common, "google_api_key": api_key}
            if effort is not None:
                kwargs["thinking_level"] = effort

        case _:
            raise LLMConfigurationError(f"Unsupported provider: {spec.provider}")

    return kwargs


def _chat_model_class(provider: LLMProvider) -> type[BaseChatModel]:
    """Import provider classes lazily so unused providers cost nothing at startup."""
    match provider:
        case LLMProvider.OPENAI | LLMProvider.INCEPTION:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI
        case LLMProvider.ANTHROPIC:
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic
        case LLMProvider.GEMINI:
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI
    raise LLMConfigurationError(f"Unsupported provider: {provider}")


# ── Public entry points ──────────────────────────────────────────────────────


@lru_cache(maxsize=32)
def create_chat_model(spec: LLMSpec) -> BaseChatModel:
    """Build (and cache) the chat model for a resolved spec. Clients are reused per spec."""
    return _chat_model_class(spec.provider)(**chat_model_kwargs(spec))


def get_chat_model(
    agent: AgentName | None = None,
    *,
    provider: LLMProvider | str | None = None,
    model: str | None = None,
    reasoning: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> BaseChatModel:
    """Return the LangChain chat model for an agent.

    Examples:
        get_chat_model(AgentName.SEO_AUDIT)                          # from .env
        get_chat_model(AgentName.CONTENT_STRATEGY, reasoning="high")  # more thinking
        get_chat_model(provider="inception", reasoning="instant")     # fast, no agent
    """
    spec = resolve_llm_spec(
        agent,
        provider=provider,
        model=model,
        reasoning=reasoning,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return create_chat_model(spec)
