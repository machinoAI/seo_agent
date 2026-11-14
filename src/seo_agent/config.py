"""Centralized application configuration.

All settings come from environment variables (and `.env` in local development).
Secrets use `SecretStr` so they stay masked in logs, reprs and tracebacks.

Everything runs locally by default: SQLite files under `data/`, no servers required.
Set DATABASE_URL to a PostgreSQL URL (and install the `postgres` extra) for production.
"""

import re
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_CONFIG = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    env_ignore_empty=True,  # blank values in .env fall back to the defaults below
    extra="ignore",
)


class Environment(StrEnum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


class LLMProvider(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    INCEPTION = "inception"  # Mercury models, OpenAI-compatible API


class AgentName(StrEnum):
    """The four specialized agents (design doc §4). Values are the env-var prefixes."""

    SEO_AUDIT = "seo_audit"
    KEYWORD_RESEARCH = "keyword_research"
    CONTENT_STRATEGY = "content_strategy"
    PERFORMANCE_REPORTING = "performance_reporting"


# One or more DNS labels + an alphabetic TLD (so bare IPs and "localhost" are rejected).
_HOSTNAME = re.compile(
    r"(?=.{1,253}$)"  # total length
    r"([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+"  # labels
    r"[a-z][a-z0-9-]{0,61}[a-z0-9]"  # TLD (alphabetic start, max 63 chars)
)


def normalize_site(value: str) -> str:
    """Normalize a site to a bare hostname: 'https://Machinoai.in/blog' -> 'machinoai.in'.

    Rejects IPs, localhost and malformed names. Full SSRF protection (private IP ranges,
    DNS rebinding, redirects — design doc §12.1) belongs in the domain-validation tool.
    """
    raw = value.strip()
    host = (urlsplit(raw if "://" in raw else f"//{raw}").hostname or "").rstrip(".").lower()
    if not _HOSTNAME.fullmatch(host):
        raise ValueError(f"'{value}' is not a valid public domain (example: machinoai.in)")
    return host


class Settings(BaseSettings):
    model_config = _ENV_CONFIG

    # ── Target website & outputs ────────────────────────────────────────────
    target_site: str = "machinoai.in"
    output_dir: Path = Path("data/output")  # tool results, time-partitioned

    # ── Application ─────────────────────────────────────────────────────────
    app_env: Environment = Environment.LOCAL
    app_name: str = "seo-agent"
    log_level: str = "INFO"
    log_json: bool = False

    # ── Database ────────────────────────────────────────────────────────────
    # Local default: a SQLite file (no server). Production: postgresql+psycopg://...
    database_url: SecretStr = SecretStr("sqlite+aiosqlite:///data/seo_agent.db")
    auto_migrate: bool = True  # apply Alembic migrations on startup (disable in production)

    # ── Crawler ─────────────────────────────────────────────────────────────
    crawler_user_agent: str = "SEOAgentBot/0.1"
    crawler_max_pages: int = Field(default=500, ge=1)
    crawler_max_depth: int = Field(default=5, ge=0)
    crawler_concurrency: int = Field(default=4, ge=1, le=32)
    crawler_delay_seconds: float = Field(default=0.2, ge=0)  # politeness pause per worker
    crawler_request_timeout_seconds: float = Field(default=20.0, gt=0)
    crawler_max_response_bytes: int = Field(default=5_000_000, ge=10_000)

    # ── Google data sources ─────────────────────────────────────────────────
    pagespeed_api_key: SecretStr | None = None  # optional; raises the PageSpeed quota
    pagespeed_max_urls: int = Field(default=5, ge=0)  # priority pages measured per run
    gsc_service_account_file: Path | None = None
    gsc_property: str | None = None  # blank = try sc-domain:<site>, then https://<site>/
    gsc_lookback_days: int = Field(default=28, ge=1, le=480)

    # ── API ─────────────────────────────────────────────────────────────────
    api_key: SecretStr | None = None  # if set, POST/GET /runs require the X-API-Key header

    # ── LLM defaults (used by every agent unless overridden) ────────────────
    llm_provider: LLMProvider = LLMProvider.ANTHROPIC
    llm_model: str | None = None  # None = the provider's default model
    llm_reasoning: str = "medium"  # none | low | medium | high, or a provider-native value
    llm_temperature: float | None = None  # None = provider default
    llm_max_tokens: int = 16_384  # includes thinking tokens on reasoning models
    llm_timeout_seconds: float = 120.0
    llm_max_retries: int = 2
    # Extra/overridden token prices, USD per 1M: {"model": [input, cached_input, output]}
    llm_prices: dict[str, list[float]] = Field(default_factory=dict)

    # ── LLM provider credentials ────────────────────────────────────────────
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None
    inception_api_key: SecretStr | None = None
    inception_base_url: str = "https://api.inceptionlabs.ai/v1"

    @field_validator("target_site")
    @classmethod
    def _normalize_target_site(cls, value: str) -> str:
        return normalize_site(value)

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.get_secret_value().startswith("sqlite")

    @property
    def sync_database_url(self) -> str:
        """Synchronous driver URL, used by Alembic migrations."""
        return self.database_url.get_secret_value().replace("+aiosqlite", "")

    @property
    def checkpoint_target(self) -> str:
        """Where LangGraph checkpoints live: a SQLite file path, or a libpq Postgres URI."""
        url = self.database_url.get_secret_value()
        if self.is_sqlite:
            db_path = Path(url.split(":///", 1)[1])
            return str(db_path.with_name("checkpoints.db"))
        return url.replace("postgresql+psycopg://", "postgresql://")


class AgentLLMOverrides(BaseSettings):
    """Optional per-agent LLM settings, read from `<AGENT>_LLM_*` env vars.

    Example: `CONTENT_STRATEGY_LLM_PROVIDER=openai`, `CONTENT_STRATEGY_LLM_REASONING=high`.
    Anything left blank inherits from the global `LLM_*` settings.
    """

    model_config = _ENV_CONFIG

    provider: LLMProvider | None = None
    model: str | None = None
    reasoning: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings (cached)."""
    return Settings()


@lru_cache
def get_agent_llm_overrides(agent: AgentName) -> AgentLLMOverrides:
    """Per-agent LLM overrides (cached), e.g. `SEO_AUDIT_LLM_*` for `AgentName.SEO_AUDIT`."""
    return AgentLLMOverrides(_env_prefix=f"{agent.value.upper()}_LLM_")
