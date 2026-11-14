"""API smoke tests against a throwaway SQLite database (no network, no LLM calls)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from src.persistence.database import get_engine, get_session_factory


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    for cached in (get_settings, get_engine, get_session_factory):
        cached.cache_clear()

    from src.main import create_app

    with TestClient(create_app()) as test_client:  # runs migrations in the lifespan
        yield test_client
    for cached in (get_settings, get_engine, get_session_factory):
        cached.cache_clear()


def test_health(client: TestClient) -> None:
    assert client.get("/health/live").json() == {"status": "ok"}
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["checks"]["database"] == "ok"


@pytest.mark.parametrize("site", ["localhost", "127.0.0.1", "not a domain"])
def test_invalid_sites_are_rejected(client: TestClient, site: str) -> None:
    response = client.post("/runs", json={"site": site})
    assert response.status_code == 422


def test_unknown_run_is_404(client: TestClient) -> None:
    response = client.get("/runs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
