from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import BaseModel

from src.agents.base import (
    AgentOutputError,
    _invoke_validated,
    extract_json,
    message_text,
)


class Schema(BaseModel):
    summary: str
    count: int


@pytest.mark.parametrize(
    "text",
    [
        '{"summary": "ok", "count": 1}',
        'Here you go:\n```json\n{"summary": "ok", "count": 1}\n```\nThanks',
        'Sure. {"summary": "ok", "count": 1} Let me know.',
    ],
)
def test_extract_json_tolerates_fences_and_prose(text: str) -> None:
    assert extract_json(text) == {"summary": "ok", "count": 1}


def test_extract_json_without_object_raises() -> None:
    with pytest.raises(AgentOutputError):
        extract_json("no json here")


def test_message_text_skips_thinking_blocks() -> None:
    message = AIMessage(content=[
        {"type": "thinking", "thinking": "hmm"},
        {"type": "text", "text": '{"a": 1}'},
    ])
    assert message_text(message) == '{"a": 1}'


class FakeModel:
    """Returns queued replies and records the messages it was sent."""

    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.calls: list[list[BaseMessage]] = []

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        self.calls.append(messages)
        return AIMessage(content=self.replies.pop(0))


async def test_invalid_reply_gets_one_correction_round() -> None:
    model: Any = FakeModel(['{"summary": "x"}', '{"summary": "x", "count": 2}'])

    output = await _invoke_validated(model, [], Schema)

    assert output == {"summary": "x", "count": 2}
    assert len(model.calls) == 2
    assert "<correction>" in str(model.calls[1][-1].content)


async def test_still_invalid_after_correction_fails() -> None:
    model: Any = FakeModel(["nope", "still nope"])

    with pytest.raises(AgentOutputError, match="2 attempts"):
        await _invoke_validated(model, [], Schema)
