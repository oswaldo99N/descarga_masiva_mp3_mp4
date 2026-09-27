"""Locations shared by source runs and the installed Windows application."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


APP_FOLDER = "NexoDescargas"


def resource_path(*parts: str) -> Path:
    """PyInstaller puts bundled data under _MEIPASS in one-folder builds."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root.joinpath(*parts)


def data_directory() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    root = Path(local) if local else Path.home() / "AppData" / "Local"
    return root / APP_FOLDER


def migrate_legacy_state(
    *, legacy_dir: Path | None = None, destination: Path | None = None,
) -> Path:
    """Copy old source-tree state once; never remove the user's original files."""
    source = legacy_dir or Path(__file__).resolve().parent / ".state"
    target = destination or data_directory()
    old_queue = source / "queue.json"
    new_queue = target / "queue.json"
    if old_queue.is_file() and not new_queue.exists():
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_queue, new_queue)
        old_archives = source / "archives"
        if old_archives.is_dir():
            new_archives = target / "archives"
            new_archives.mkdir(parents=True, exist_ok=True)
            for archive in old_archives.glob("*.txt"):
                destination_archive = new_archives / archive.name
                if not destination_archive.exists():
                    shutil.copy2(archive, destination_archive)
    return new_queue
