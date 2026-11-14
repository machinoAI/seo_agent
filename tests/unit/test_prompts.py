import xml.etree.ElementTree as ET

import pytest

from src.config import AgentName
from src.prompts import AgentPrompt, PromptError, load_prompt, render_snippet


@pytest.mark.parametrize("agent", list(AgentName))
def test_every_agent_has_a_valid_prompt(agent: AgentName) -> None:
    prompt = load_prompt(agent)

    assert prompt.name == agent.value
    assert prompt.version >= 1


@pytest.mark.parametrize("agent", list(AgentName))
def test_prompt_text_is_well_formed_xml(agent: AgentName) -> None:
    prompt = load_prompt(agent)

    for part in (prompt.system, prompt.user):
        ET.fromstring(f"<prompt>{part}</prompt>")  # raises ParseError if malformed


def test_render_fills_placeholders_and_defaults() -> None:
    messages = load_prompt(AgentName.SEO_AUDIT).render(
        site="machinoai.in", run_date="2026-11-05", evidence='{"findings": []}'
    )

    system, user = (str(m.content) for m in messages)
    assert "<site>machinoai.in</site>" in system
    assert "baseline" in system  # default for previous_audit
    assert "$" not in system + user
    assert '{"findings": []}' in user


def test_shared_correction_snippet_renders_as_xml() -> None:
    text = render_snippet("output_correction", error="missing field: summary")

    ET.fromstring(text)
    assert "missing field: summary" in text
    with pytest.raises(PromptError):
        render_snippet("output_correction")


def test_render_rejects_missing_and_unknown_variables() -> None:
    prompt = load_prompt(AgentName.SEO_AUDIT)

    with pytest.raises(PromptError, match="missing"):
        prompt.render(site="machinoai.in")
    with pytest.raises(PromptError, match="unknown"):
        prompt.render(site="machinoai.in", run_date="2026-11-05", colour="blue")


def test_undeclared_placeholder_is_rejected() -> None:
    with pytest.raises(ValueError, match="undeclared"):
        AgentPrompt(
            name="x",
            version=1,
            description="x",
            variables={},
            system="<role>${site}</role>",
            user="<task>go</task>",
        )
