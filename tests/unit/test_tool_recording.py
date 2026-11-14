import json
from pathlib import Path
from uuid import uuid4

import pytest

from seo_agent.persistence.output_store import OutputStore
from seo_agent.tools.base import (
    ErrorKind,
    ToolFailure,
    ToolOutput,
    ToolRequest,
    ToolStatus,
    recorded_tool,
)


class EchoRequest(ToolRequest):
    text: str


@pytest.fixture
def store(tmp_path: Path) -> OutputStore:
    return OutputStore(tmp_path)


def _request() -> EchoRequest:
    return EchoRequest(run_id=uuid4(), site="https://www.Machinoai.in/blog", text="hi")


async def test_async_tool_result_is_saved_in_time_partitioned_folder(
    store: OutputStore, tmp_path: Path
) -> None:
    @recorded_tool("echo", store=store)
    async def echo(request: EchoRequest) -> ToolOutput:
        return ToolOutput(data={"echo": request.text}, source="test")

    request = _request()
    result = await echo(request)

    assert result.status is ToolStatus.SUCCESS
    path = Path(result.output_path or "")
    date = result.completed_at.strftime("%Y-%m-%d")
    assert path.parent == tmp_path / "www.machinoai.in" / date / f"run_{request.run_id}"
    assert path.name.endswith(f"_echo_{str(request.request_id)[:8]}.json")

    saved = json.loads(path.read_text())
    assert saved["request"]["text"] == "hi"
    assert saved["result"]["data"] == {"echo": "hi"}

    manifest = (path.parent / "manifest.jsonl").read_text().splitlines()
    assert json.loads(manifest[0])["file"] == path.name


def test_sync_tool_failure_is_recorded_with_retry_classification(store: OutputStore) -> None:
    @recorded_tool("flaky", store=store)
    def flaky(request: EchoRequest) -> ToolOutput:
        raise ToolFailure("http_429", "rate limited", ErrorKind.TRANSIENT)

    result = flaky(_request())

    assert result.status is ToolStatus.FAILED
    assert result.retryable is True
    assert json.loads(Path(result.output_path or "").read_text())["result"]["status"] == "failed"


def test_unexpected_exception_does_not_leak_details(store: OutputStore) -> None:
    @recorded_tool("broken", store=store)
    def broken(request: EchoRequest) -> ToolOutput:
        raise RuntimeError("secret internal detail")

    result = broken(_request())

    assert result.error is not None
    assert result.error.code == "unexpected_error"
    assert "secret" not in result.error.message
    assert result.retryable is False


def test_run_folder_keeps_its_start_date(store: OutputStore, tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    run_id = uuid4()
    start = datetime(2026, 11, 14, 23, 59, tzinfo=UTC)
    first = store.run_dir("machinoai.in", run_id, start)
    first.mkdir(parents=True)

    later = store.run_dir("machinoai.in", run_id, start + timedelta(days=1))

    assert later == first == tmp_path / "machinoai.in" / "2026-11-14" / f"run_{run_id}"


def test_invalid_tool_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid tool name"):
        recorded_tool("../escape")
