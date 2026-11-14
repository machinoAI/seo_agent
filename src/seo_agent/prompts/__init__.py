"""Agent prompts: one versioned YAML file per agent, prompt text in XML-tagged style.

File layout (`<agent_name>.yaml`):
    name, version, description
    variables:  {name: {description, default?}}   # every placeholder must be declared
    system:     XML-tagged system prompt
    user:       XML-tagged user/task prompt

Placeholders use `$name` / `${name}` (string.Template), so JSON examples and XML need no
escaping. Usage:

    prompt = load_prompt(AgentName.SEO_AUDIT)
    messages = prompt.render(site="machinoai.in", run_date="2026-11-05")
    get_chat_model(AgentName.SEO_AUDIT).invoke(messages)
"""

from functools import lru_cache
from importlib import resources
from string import Template
from typing import Any

import yaml
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from seo_agent.config import AgentName


class PromptError(ValueError):
    """A prompt file is invalid, or rendering is missing/has unknown variables."""


class PromptVariable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    description: str
    default: str | None = None


class AgentPrompt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    version: int = Field(ge=1)
    description: str
    variables: dict[str, PromptVariable] = Field(default_factory=dict)
    system: str
    user: str

    @model_validator(mode="after")
    def _placeholders_match_declared_variables(self) -> "AgentPrompt":
        used = set(Template(self.system).get_identifiers())
        used |= set(Template(self.user).get_identifiers())
        undeclared = used - self.variables.keys()
        unused = self.variables.keys() - used
        if undeclared or unused:
            raise PromptError(
                f"Prompt '{self.name}': undeclared placeholders {sorted(undeclared)}, "
                f"declared but unused variables {sorted(unused)}"
            )
        return self

    @property
    def ref(self) -> str:
        """Stable identifier to record alongside outputs, e.g. 'seo_audit@v1'."""
        return f"{self.name}@v{self.version}"

    def render(self, **values: str) -> list[BaseMessage]:
        """Fill the placeholders and return LangChain messages (system + user)."""
        unknown = values.keys() - self.variables.keys()
        if unknown:
            raise PromptError(f"Prompt '{self.name}': unknown variables {sorted(unknown)}")

        merged = {k: v.default for k, v in self.variables.items() if v.default is not None}
        merged.update(values)
        missing = self.variables.keys() - merged.keys()
        if missing:
            raise PromptError(f"Prompt '{self.name}': missing variables {sorted(missing)}")

        return [
            SystemMessage(content=Template(self.system).substitute(merged)),
            HumanMessage(content=Template(self.user).substitute(merged)),
        ]


class PromptSnippet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    description: str
    variables: list[str] = Field(default_factory=list)
    text: str

    @model_validator(mode="after")
    def _placeholders_match_declared_variables(self) -> "PromptSnippet":
        used = set(Template(self.text).get_identifiers())
        if used != set(self.variables):
            raise PromptError(f"Snippet placeholders {sorted(used)} != variables {self.variables}")
        return self


class SharedPrompts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    version: int = Field(ge=1)
    description: str
    snippets: dict[str, PromptSnippet]


def _read_yaml(filename: str) -> Any:
    try:
        text = resources.files(__name__).joinpath(filename).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise PromptError(f"Prompt file not found: {filename}") from None
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PromptError(f"{filename} is not valid YAML: {exc}") from exc


@lru_cache
def load_shared_prompts() -> SharedPrompts:
    try:
        return SharedPrompts.model_validate(_read_yaml("shared.yaml"))
    except ValidationError as exc:
        raise PromptError(f"shared.yaml is invalid: {exc}") from exc


def render_snippet(name: str, **values: str) -> str:
    """Render a shared snippet, e.g. render_snippet("output_correction", error="...")."""
    snippet = load_shared_prompts().snippets.get(name)
    if snippet is None:
        raise PromptError(f"Unknown prompt snippet '{name}'")
    if set(values) != set(snippet.variables):
        raise PromptError(f"Snippet '{name}' needs exactly {snippet.variables}")
    return Template(snippet.text).substitute(values)


@lru_cache
def load_prompt(agent: AgentName | str) -> AgentPrompt:
    """Load and validate `<agent>.yaml` from this package (cached)."""
    name = AgentName(agent).value
    try:
        prompt = AgentPrompt.model_validate(_read_yaml(f"{name}.yaml"))
    except ValidationError as exc:
        raise PromptError(f"{name}.yaml is invalid: {exc}") from exc
    if prompt.name != name:
        raise PromptError(f"{name}.yaml declares name '{prompt.name}'")
    return prompt
