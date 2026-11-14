from collections.abc import Callable
from typing import Any

import pytest
from pydantic import SecretStr

from src.config import AgentLLMOverrides, AgentName, LLMProvider, Settings
from src.llm import factory
from src.llm.factory import (
    DEFAULT_MODELS,
    LLMConfigurationError,
    chat_model_kwargs,
    resolve_llm_spec,
)

_TEST_KEYS = {
    "openai_api_key": SecretStr("sk-test"),
    "anthropic_api_key": SecretStr("sk-ant-test"),
    "google_api_key": SecretStr("google-test"),
    "inception_api_key": SecretStr("inception-test"),
}

Configure = Callable[..., Settings]


@pytest.fixture
def configure(monkeypatch: pytest.MonkeyPatch) -> Configure:
    """Point the factory at in-memory settings instead of .env / OS environment."""

    def _configure(
        agents: dict[AgentName, dict[str, Any]] | None = None, **values: Any
    ) -> Settings:
        settings = Settings.model_construct(**{**_TEST_KEYS, **values})
        overrides = {a: AgentLLMOverrides.model_construct(**v) for a, v in (agents or {}).items()}
        monkeypatch.setattr(factory, "get_settings", lambda: settings)
        monkeypatch.setattr(
            factory,
            "get_agent_llm_overrides",
            lambda agent: overrides.get(agent, AgentLLMOverrides.model_construct()),
        )
        return settings

    return _configure


# ── Resolution ───────────────────────────────────────────────────────────────


def test_blank_model_uses_provider_default(configure: Configure) -> None:
    configure(llm_provider=LLMProvider.INCEPTION)

    assert resolve_llm_spec().model == "mercury-3"


def test_agent_switching_provider_does_not_inherit_global_model(configure: Configure) -> None:
    configure(
        llm_provider=LLMProvider.ANTHROPIC,
        llm_model="claude-opus-5-5",
        agents={AgentName.SEO_AUDIT: {"provider": LLMProvider.OPENAI}},
    )

    assert resolve_llm_spec(AgentName.SEO_AUDIT).model == DEFAULT_MODELS[LLMProvider.OPENAI]
    assert resolve_llm_spec(AgentName.CONTENT_STRATEGY).model == "claude-opus-5-5"


def test_runtime_overrides_beat_agent_overrides(configure: Configure) -> None:
    configure(agents={AgentName.CONTENT_STRATEGY: {"reasoning": "low"}})

    spec = resolve_llm_spec(AgentName.CONTENT_STRATEGY, provider="gemini", reasoning="high")

    assert spec.provider is LLMProvider.GEMINI
    assert spec.model == DEFAULT_MODELS[LLMProvider.GEMINI]
    assert spec.reasoning == "high"


def test_unknown_provider_is_rejected(configure: Configure) -> None:
    configure()

    with pytest.raises(LLMConfigurationError, match="Unknown LLM provider"):
        resolve_llm_spec(provider="mistral")


def test_native_reasoning_value_must_match_provider(configure: Configure) -> None:
    configure(llm_provider=LLMProvider.GEMINI, llm_reasoning="instant")

    with pytest.raises(LLMConfigurationError, match="instant"):
        resolve_llm_spec()


# ── Provider kwargs ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        (LLMProvider.OPENAI, {"reasoning_effort": "none"}),
        (LLMProvider.INCEPTION, {"reasoning_effort": "instant"}),
        (LLMProvider.GEMINI, {"thinking_level": "low"}),
    ],
)
def test_portable_none_maps_to_native_value(
    configure: Configure, provider: LLMProvider, expected: dict[str, str]
) -> None:
    configure(llm_provider=provider, llm_reasoning="none")

    kwargs = chat_model_kwargs(resolve_llm_spec())

    assert expected.items() <= kwargs.items()


def test_anthropic_reasoning_enables_adaptive_thinking(configure: Configure) -> None:
    configure(llm_provider=LLMProvider.ANTHROPIC, llm_reasoning="high")

    kwargs = chat_model_kwargs(resolve_llm_spec())

    assert kwargs["thinking"] == {"type": "adaptive"}
    assert kwargs["effort"] == "high"


def test_anthropic_reasoning_none_leaves_thinking_off(configure: Configure) -> None:
    configure(llm_provider=LLMProvider.ANTHROPIC, llm_reasoning="none")

    kwargs = chat_model_kwargs(resolve_llm_spec())

    assert "thinking" not in kwargs
    assert "effort" not in kwargs


def test_anthropic_rejects_temperature_while_thinking(configure: Configure) -> None:
    configure(llm_provider=LLMProvider.ANTHROPIC, llm_reasoning="medium", llm_temperature=0.2)

    with pytest.raises(LLMConfigurationError, match="temperature"):
        chat_model_kwargs(resolve_llm_spec())


def test_default_reasoning_sends_no_reasoning_parameter(configure: Configure) -> None:
    configure(llm_provider=LLMProvider.OPENAI, llm_reasoning="default")

    assert "reasoning_effort" not in chat_model_kwargs(resolve_llm_spec())


def test_inception_uses_openai_compatible_chat_completions(configure: Configure) -> None:
    settings = configure(llm_provider=LLMProvider.INCEPTION)

    kwargs = chat_model_kwargs(resolve_llm_spec())

    assert kwargs["base_url"] == settings.inception_base_url
    assert kwargs["use_responses_api"] is False


def test_missing_api_key_fails_before_any_call(configure: Configure) -> None:
    configure(llm_provider=LLMProvider.OPENAI, openai_api_key=None)

    with pytest.raises(LLMConfigurationError, match="OPENAI_API_KEY"):
        chat_model_kwargs(resolve_llm_spec())
