"""Check GitHub Releases and fetch a verified desktop installer."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from app_paths import data_directory
from release_config import APP_VERSION, REPOSITORY


REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
VERSION_PATTERN = re.compile(r"v?(\d+)\.(\d+)\.(\d+)\Z")
SHA256_PATTERN = re.compile(r"sha256:([0-9a-fA-F]{64})\Z")
MAX_INSTALLER_BYTES = 2 * 1024 * 1024 * 1024


@dataclass(frozen=True)
class Release:
    version: str
    notes: str
    tag: str
    filename: str
    url: str
    sha256: str
    size: int


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.fullmatch(value)
    if not match:
        raise ValueError(f"Versión no válida: {value}")
    return tuple(map(int, match.groups()))


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"NexoDescargas/{APP_VERSION}",
    })


def installer_filename(version: str, *, system: str | None = None,
                       machine: str | None = None) -> str:
    system = system or sys.platform
    if system == "win32":
        return f"Nexo-Descargas-Setup-{version}.exe"
    if system == "darwin":
        machine = (machine or platform.machine()).lower()
        architecture = {"arm64": "arm64", "aarch64": "arm64",
                        "x86_64": "x64", "amd64": "x64"}.get(machine)
        if architecture:
            return f"Nexo-Descargas-{version}-macos-{architecture}.dmg"
    raise RuntimeError("No hay instalador disponible para este sistema.")


def check_for_update(repository: str = REPOSITORY, current_version: str = APP_VERSION,
                     *, system: str | None = None, machine: str | None = None) -> Release | None:
    if not repository:
        return None
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise ValueError("Configura el repositorio como usuario/proyecto.")
    owner, name = repository.split("/", 1)
    endpoint = f"https://api.github.com/repos/{quote(owner)}/{quote(name)}/releases/latest"
    with urllib.request.urlopen(_request(endpoint), timeout=15) as response:
        data = json.load(response)
    tag = data.get("tag_name", "")
    remote_version = _version_tuple(tag)
    if remote_version <= _version_tuple(current_version):
        return None
    version = tag.removeprefix("v")
    expected_name = installer_filename(version, system=system, machine=machine)
    for asset in data.get("assets", []):
        if asset.get("name") != expected_name:
            continue
        digest = SHA256_PATTERN.fullmatch(asset.get("digest") or "")
        size = asset.get("size")
        url = asset.get("browser_download_url") or ""
        expected_url = (f"https://github.com/{repository}/releases/download/"
                        f"{quote(tag, safe='')}/{quote(expected_name)}")
        if not digest or not isinstance(size, int) or not 0 < size <= MAX_INSTALLER_BYTES:
            raise ValueError("El instalador publicado no tiene SHA-256 o tamaño válido.")
        if url != expected_url:
            raise ValueError("La dirección del instalador no coincide con el repositorio.")
        return Release(version, data.get("body") or "", tag, expected_name, url,
                       digest.group(1).lower(), size)
    raise ValueError(f"La versión {tag} no incluye {expected_name}.")


def download_installer(release: Release, destination: Path | None = None) -> Path:
    target_dir = destination if destination is not None else data_directory() / "updates"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / release.filename
    if target.is_file() and target.stat().st_size == release.size:
        if _file_sha256(target) == release.sha256:
            return target
    temporary = target.with_suffix(".part")
    try:
        digest = hashlib.sha256()
        received = 0
        with urllib.request.urlopen(_request(release.url), timeout=30) as response:
            with temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    received += len(chunk)
                    if received > MAX_INSTALLER_BYTES or received > release.size:
                        raise ValueError("El instalador excede el tamaño publicado.")
                    digest.update(chunk)
                    output.write(chunk)
        if received != release.size or digest.hexdigest() != release.sha256:
            raise ValueError("La verificación SHA-256 del instalador falló.")
        os.replace(temporary, target)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
