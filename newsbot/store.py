"""Persistence utilities for news-digest-bot."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

DEFAULT_TZ = ZoneInfo("Europe/London")


def start_run_dir(base: str = "runs/") -> Path:
    """Create and return a timestamped run directory."""
    timestamp = datetime.now(DEFAULT_TZ).strftime("%Y%m%d_%H%M%S")
    run_dir = Path(base) / timestamp
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def write_text(path: Path, text: str) -> None:
    """Write text to a file, ensuring parent directories exist."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    """Write an iterable of dictionaries to JSON Lines format."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def save_manifest(path: Path, manifest: dict) -> None:
    """Save manifest data as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    """Write structured JSON payload to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def update_latest_digest(path: Path) -> None:
    """Copy the latest digest JSON to runs/latest.json for change tracking."""

    latest_path = path.parent.parent / "latest.json"
    try:
        shutil.copyfile(path, latest_path)
    except FileNotFoundError:  # pragma: no cover - best effort
        latest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, latest_path)
