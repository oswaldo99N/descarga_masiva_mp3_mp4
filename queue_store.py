"""Persistent download queue and history. No browser cookies are stored here."""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from app_paths import migrate_legacy_state
from downloader import DownloadOptions
from providers import parse_media_link


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class QueueItem:
    task_id: str
    options: DownloadOptions
    title: str
    status: str
    created_at: str
    updated_at: str
    transferred: int = 0
    errors: int = 0
    last_error: str = ""
    attempts: int = 0


def _options_data(options: DownloadOptions) -> dict:
    return {
        "url": options.link.url,
        "folder": str(options.folder),
        "scope": options.scope,
        "kind": options.kind,
        "quality": options.quality,
        "audio_format": options.audio_format,
        "browser": options.browser,
        "embed_metadata": options.embed_metadata,
        "save_thumbnail": options.save_thumbnail,
        "subtitle_mode": options.subtitle_mode,
        "subtitle_language": options.subtitle_language,
        "video_container": options.video_container,
    }


def _options_from_data(data: dict) -> DownloadOptions:
    return DownloadOptions(
        link=parse_media_link(data["url"]),
        folder=Path(data["folder"]),
        scope=data["scope"],
        kind=data["kind"],
        quality=data["quality"],
        audio_format=data["audio_format"],
        browser=data.get("browser", "none"),
        embed_metadata=data.get("embed_metadata", False),
        save_thumbnail=data.get("save_thumbnail", False),
        subtitle_mode=data.get("subtitle_mode", "none"),
        subtitle_language=data.get("subtitle_language", "es"),
        video_container=data.get("video_container", "auto"),
    )


class QueueStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else migrate_legacy_state()
        self.archive_dir = self.path.parent / "archives"
        self._lock = threading.RLock()
        self._items: list[QueueItem] = []
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("version") != 1:
            raise ValueError("La versión del historial no es compatible.")
        for row in data.get("items", []):
            item = QueueItem(
                task_id=row["task_id"],
                options=_options_from_data(row["options"]),
                title=row["title"],
                status="paused" if row["status"] == "running" else row["status"],
                created_at=row["created_at"],
                updated_at=row.get("updated_at", row["created_at"]),
                transferred=row.get("transferred", 0),
                errors=row.get("errors", 0),
                last_error=row.get("last_error", ""),
                attempts=row.get("attempts", 0),
            )
            self._items.append(item)
        if any(row["status"] == "running" for row in data.get("items", [])):
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for item in self._items:
            rows.append({
                "task_id": item.task_id,
                "options": _options_data(item.options),
                "title": item.title,
                "status": item.status,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
                "transferred": item.transferred,
                "errors": item.errors,
                "last_error": item.last_error,
                "attempts": item.attempts,
            })
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"version": 1, "items": rows}, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        os.replace(temporary, self.path)

    def snapshot(self) -> list[QueueItem]:
        with self._lock:
            return [replace(item) for item in self._items]

    def get(self, task_id: str) -> QueueItem | None:
        with self._lock:
            return next((replace(item) for item in self._items if item.task_id == task_id), None)

    def add_or_requeue(self, options: DownloadOptions, title: str) -> tuple[QueueItem, bool]:
        fingerprint = _options_data(options)
        with self._lock:
            for item in self._items:
                if _options_data(item.options) == fingerprint:
                    if item.status not in {"pending", "running"}:
                        item.status = "pending"
                        item.updated_at = _now()
                        item.last_error = ""
                        self._save()
                    return replace(item), False
            timestamp = _now()
            item = QueueItem(uuid.uuid4().hex, options, title or options.link.url,
                             "pending", timestamp, timestamp)
            self._items.append(item)
            self._save()
            return replace(item), True

    def next_pending(self) -> QueueItem | None:
        with self._lock:
            for item in self._items:
                if item.status == "pending":
                    item.status = "running"
                    item.updated_at = _now()
                    item.attempts += 1
                    self._save()
                    return replace(item)
        return None

    def update(self, task_id: str, **changes) -> QueueItem:
        with self._lock:
            item = next(item for item in self._items if item.task_id == task_id)
            for key, value in changes.items():
                setattr(item, key, value)
            item.updated_at = _now()
            self._save()
            return replace(item)

    def resume_paused(self) -> int:
        with self._lock:
            count = 0
            for item in self._items:
                if item.status == "paused":
                    item.status = "pending"
                    item.updated_at = _now()
                    count += 1
            if count:
                self._save()
            return count

    def remove(self, task_id: str) -> bool:
        with self._lock:
            for index, item in enumerate(self._items):
                if item.task_id == task_id and item.status != "running":
                    self._items.pop(index)
                    self._save()
                    return True
        return False

    def archive_path(self, task_id: str) -> Path:
        return self.archive_dir / f"{task_id}.txt"
