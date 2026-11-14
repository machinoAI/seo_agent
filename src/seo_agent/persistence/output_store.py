"""Time-partitioned JSON store for tool results.

Layout (all times UTC):
    <OUTPUT_DIR>/<site>/<YYYY-MM-DD>/run_<run_id>/<HHMMSS_ffffff>_<tool>_<request8>.json
    <OUTPUT_DIR>/<site>/<YYYY-MM-DD>/run_<run_id>/manifest.jsonl     one line per tool call

Each JSON file holds the tool request and its full result. Files are written atomically
(temp file + rename), so readers never see half-written output. This is the local
file-system backend; an object-storage backend can implement the same `save()` later.
"""

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

from seo_agent.config import get_settings


class OutputStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def run_dir(self, site: str, run_id: UUID, when: datetime) -> Path:
        """Folder for one run's outputs.

        Dated by the day the run started: once the folder exists it is reused, so a run
        that crosses midnight (or is resumed later) keeps all its files together.
        """
        existing = sorted((self.root / site).glob(f"*/run_{run_id}"))
        directory = existing[0] if existing else (
            self.root / site / f"{when.astimezone(UTC):%Y-%m-%d}" / f"run_{run_id}"
        )
        # site/tool names are validated upstream; this guards against path traversal anyway
        if not directory.resolve().is_relative_to(self.root.resolve()):
            raise ValueError(f"Refusing to write outside the output root: {directory}")
        return directory

    def save(
        self,
        *,
        site: str,
        run_id: UUID,
        tool: str,
        request_id: UUID,
        status: str,
        recorded_at: datetime,
        payload: Mapping[str, Any],
    ) -> Path:
        """Write one tool call's request and result, and append it to the run manifest."""
        when = recorded_at.astimezone(UTC)
        directory = self.run_dir(site, run_id, when)
        directory.mkdir(parents=True, exist_ok=True)

        path = directory / f"{when:%H%M%S_%f}_{tool}_{str(request_id)[:8]}.json"
        _atomic_write(path, json.dumps(payload, indent=2, ensure_ascii=False, default=str))

        entry = {
            "recorded_at": when.isoformat(),
            "tool": tool,
            "status": status,
            "request_id": str(request_id),
            "file": path.name,
        }
        with (directory / "manifest.jsonl").open("a", encoding="utf-8") as manifest:
            manifest.write(json.dumps(entry) + "\n")
        return path


def read_recorded(path: str | Path) -> dict[str, Any]:
    """Load a recorded tool call (`{"tool", "request", "result"}`) from its JSON file."""
    record: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    return record


def read_result_data(path: str | Path) -> Any:
    """Shortcut for the `result.data` of a recorded tool call."""
    return read_recorded(path)["result"].get("data")


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


@lru_cache
def get_output_store() -> OutputStore:
    """Process-wide store rooted at OUTPUT_DIR (cached)."""
    return OutputStore(get_settings().output_dir)
