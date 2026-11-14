"""LLM layer: provider-agnostic LangChain chat models for every agent.

Supported providers: OpenAI, Anthropic, Google Gemini, Inception (Mercury).
Configure via `LLM_*` and `<AGENT>_LLM_*` in `.env`; see `factory.py` for the rules.
"""

from seo_agent.llm.factory import (
    DEFAULT_MODELS,
    LLMConfigurationError,
    LLMSpec,
    create_chat_model,
    get_chat_model,
    resolve_llm_spec,
)

__all__ = [
    "DEFAULT_MODELS",
    "LLMConfigurationError",
    "LLMSpec",
    "create_chat_model",
    "get_chat_model",
    "resolve_llm_spec",
]
