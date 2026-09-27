"""Download logic independent of the desktop interface."""

from __future__ import annotations

import re
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app_paths import resource_path
from providers import MediaLink


class DownloadCancelled(Exception):
    pass


@dataclass(frozen=True)
class DownloadOptions:
    link: MediaLink
    folder: Path
    scope: str  # "single" or "playlist"
    kind: str  # "audio" or "video"
    quality: str  # "best", "1080", "720", "480"
    audio_format: str  # "original" or "mp3"
    browser: str = "none"  # none, chrome, edge, firefox
    embed_metadata: bool = False
    save_thumbnail: bool = False
    subtitle_mode: str = "none"  # none, sidecar, embed
    subtitle_language: str = "es"  # es, en
    video_container: str = "auto"  # auto, mp4, mkv
    archive_path: Path | None = None


@dataclass(frozen=True)
class Progress:
    title: str
    percent: float | None
    completed: int
    total: int | None
    status: str


@dataclass(frozen=True)
class DownloadResult:
    transferred: int
    errors: int
    last_error: str | None


@dataclass(frozen=True)
class MediaPreview:
    title: str
    count: int | None
    heights: tuple[int, ...] = ()
    mp4_heights: tuple[int, ...] = ()


ANSI_PATTERN = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def clean_error(message: str) -> str:
    return ANSI_PATTERN.sub("", message).removeprefix("ERROR: ").strip()


class QuietLogger:
    def debug(self, _message: str) -> None:
        pass

    def warning(self, _message: str) -> None:
        pass

    def error(self, _message: str) -> None:
        pass


def ffmpeg_directory() -> Path | None:
    bundled = resource_path("bin", "ffmpeg")
    if (bundled / "ffmpeg.exe").is_file() and (bundled / "ffprobe.exe").is_file():
        return bundled
    bundled = resource_path(".tools", "ffmpeg")
    if (bundled / "ffmpeg.exe").is_file() and (bundled / "ffprobe.exe").is_file():
        return bundled
    return None


def node_executable() -> Path | None:
    bundled = resource_path("bin", "node", "node.exe")
    return bundled if bundled.is_file() else None


def require_dependencies(options: DownloadOptions) -> None:
    try:
        import yt_dlp  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Falta yt-dlp. Ejecuta instalar.ps1 para instalar las dependencias."
        ) from exc
    if not ffmpeg_directory() and (not shutil.which("ffmpeg") or not shutil.which("ffprobe")):
        raise RuntimeError(
            "Faltan FFmpeg y FFprobe. Instálalos y vuelve a abrir la aplicación."
        )
    if (options.link.provider == "YouTube" and
            not shutil.which("deno") and not node_executable() and not shutil.which("node")):
        raise RuntimeError("Falta Node.js o Deno, necesario para descargar desde YouTube.")


def javascript_options(link: MediaLink) -> dict:
    """Enable the installed runtime explicitly for yt-dlp's YouTube extractor."""
    if link.provider != "YouTube":
        return {}
    runtimes = {}
    if shutil.which("deno"):
        runtimes["deno"] = {}
    if node_executable():
        runtimes["node"] = {"path": str(node_executable())}
    elif shutil.which("node"):
        runtimes["node"] = {}
    return {"js_runtimes": runtimes}


def format_selector(options: DownloadOptions) -> str:
    if options.kind == "audio":
        return "bestaudio" if options.link.provider == "YouTube" else "bestaudio/best"
    if options.quality != "best":
        height = int(options.quality)
        if not 144 <= height <= 4320:
            raise ValueError("Calidad de video no válida")
        limit = f"[height<={height}]"
    else:
        limit = ""
    if options.video_container == "mp4":
        return f"bv[ext=mp4]{limit}+ba[ext=m4a]/b[ext=mp4]{limit}"
    if options.video_container not in {"auto", "mkv"}:
        raise ValueError("Contenedor de video no válido")
    if options.quality == "best":
        return "bv*+ba/b"
    return f"bv*[height<={height}]+ba/b[height<={height}]"


def build_ydl_options(
    options: DownloadOptions,
    progress_hook: Callable[[dict], None] | None = None,
    postprocessor_hook: Callable[[dict], None] | None = None,
) -> dict:
    playlist = options.scope == "playlist"
    settings = {
        "format": format_selector(options),
        "paths": {"home": str(options.folder)},
        "outtmpl": {
            "default": (
                "%(playlist_title,playlist)s/%(playlist_index)03d - %(title).180B [%(id)s].%(ext)s"
                if playlist
                else "%(title).180B [%(id)s].%(ext)s"
            )
        },
        "noplaylist": not playlist,
        "ignoreerrors": "only_download" if playlist else False,
        "windowsfilenames": True,
        "continuedl": True,
        "overwrites": False,
        "progress_hooks": [progress_hook] if progress_hook else [],
        "postprocessor_hooks": [postprocessor_hook] if postprocessor_hook else [],
        "quiet": True,
        "no_warnings": True,
        "color": "no_color",
        **javascript_options(options.link),
    }
    if options.archive_path:
        settings["download_archive"] = str(options.archive_path)
    if options.browser != "none":
        if options.browser not in {"chrome", "edge", "firefox"}:
            raise ValueError("Navegador no válido")
        settings["cookiesfrombrowser"] = (options.browser, None, None, None)
    if ffmpeg_directory():
        settings["ffmpeg_location"] = str(ffmpeg_directory())
    postprocessors = []
    if options.kind == "audio":
        if options.audio_format == "mp3":
            postprocessors.append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            })
        elif options.link.provider != "YouTube":
            # Other sites often have only a video+audio file. Extract audio,
            # copying its codec where possible instead of re-encoding it.
            postprocessors.append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": "best",
            })
    elif options.video_container in {"mp4", "mkv"}:
        settings["merge_output_format"] = options.video_container
        postprocessors.append({
            "key": "FFmpegVideoRemuxer",
            "preferedformat": options.video_container,
        })
    if options.kind == "video" and options.subtitle_mode != "none":
        if options.subtitle_mode not in {"sidecar", "embed"}:
            raise ValueError("Opción de subtítulos no válida")
        if options.subtitle_language not in {"es", "en"}:
            raise ValueError("Idioma de subtítulos no válido")
        settings.update({
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": [f"{options.subtitle_language}.*"],
            "subtitlesformat": "srt/vtt/best",
        })
        postprocessors.insert(0, {
            "key": "FFmpegSubtitlesConvertor",
            "format": "srt",
            "when": "before_dl",
        })
        if options.subtitle_mode == "embed":
            if options.video_container == "auto":
                raise ValueError("Elige MP4 o MKV para incrustar subtítulos.")
            postprocessors.append({"key": "FFmpegEmbedSubtitle", "already_have_subtitle": True})
    if options.embed_metadata:
        postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True,
                               "add_chapters": True, "add_infojson": False})
    if options.save_thumbnail:
        settings["writethumbnail"] = True
        # Original audio may be WebM. Keep its image as a separate file;
        # MP3 has broad support for embedded artwork.
        if options.kind == "audio" and options.audio_format == "mp3":
            postprocessors.append({"key": "EmbedThumbnail", "already_have_thumbnail": True})
    if postprocessors:
        settings["postprocessors"] = postprocessors
    return settings


def _item_title(info: dict) -> str:
    return info.get("title") or info.get("id") or "Archivo"


def inspect_media(link: MediaLink, scope: str, browser: str = "none") -> MediaPreview:
    import yt_dlp

    settings = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": scope == "playlist",
        "noplaylist": scope != "playlist",
        "color": "no_color",
        "logger": QuietLogger(),
        **javascript_options(link),
    }
    if browser != "none":
        if browser not in {"chrome", "edge", "firefox"}:
            raise ValueError("Navegador no válido")
        settings["cookiesfrombrowser"] = (browser, None, None, None)
    with yt_dlp.YoutubeDL(settings) as ydl:
        info = ydl.extract_info(link.url, download=False)
    if not info:
        raise RuntimeError("No se pudo leer el enlace.")
    entries = info.get("entries")
    if entries is not None:
        entries = list(entries)
        return MediaPreview(_item_title(info), len(entries))
    heights = set()
    mp4_heights = set()
    for media_format in info.get("formats") or []:
        height = media_format.get("height")
        if media_format.get("vcodec") != "none" and isinstance(height, int) and height > 0:
            heights.add(height)
            if media_format.get("ext") == "mp4":
                mp4_heights.add(height)
    if not heights and isinstance(info.get("height"), int):
        heights.add(info["height"])
        if info.get("ext") == "mp4":
            mp4_heights.add(info["height"])
    return MediaPreview(_item_title(info), 1, tuple(sorted(heights, reverse=True)),
                        tuple(sorted(mp4_heights, reverse=True)))


def inspect_link(link: MediaLink, scope: str) -> tuple[str, int | None]:
    """Compatibility helper for callers that only need title and count."""
    preview = inspect_media(link, scope)
    return preview.title, preview.count


def download(
    options: DownloadOptions,
    emit: Callable[[Progress], None],
    cancel: threading.Event,
) -> DownloadResult:
    require_dependencies(options)
    import yt_dlp

    options.folder.mkdir(parents=True, exist_ok=True)
    if options.archive_path:
        options.archive_path.parent.mkdir(parents=True, exist_ok=True)
    completed = 0
    total = None
    current_title = "Preparando descarga"
    counted_ids: set[str] = set()
    errors: list[str] = []

    class DownloadLogger:
        def debug(self, _message: str) -> None:
            pass

        def warning(self, _message: str) -> None:
            pass

        def error(self, message: str) -> None:
            cleaned = clean_error(message)
            errors.append(cleaned)
            emit(Progress(cleaned, None, completed, total,
                          "Elemento omitido; continuando…"))

    def on_progress(data: dict) -> None:
        nonlocal completed, current_title, total
        if cancel.is_set():
            raise DownloadCancelled()
        info = data.get("info_dict") or {}
        current_title = _item_title(info)
        if info.get("playlist_count") and not options.link.dynamic_playlist:
            total = info["playlist_count"]
        downloaded = data.get("downloaded_bytes") or 0
        expected = data.get("total_bytes") or data.get("total_bytes_estimate")
        percent = min(100.0, downloaded * 100 / expected) if expected else None
        status = data.get("status", "downloading")
        if status == "finished":
            item_id = info.get("id") or data.get("filename") or current_title
            if item_id not in counted_ids:
                counted_ids.add(item_id)
                completed += 1
            emit(Progress(current_title, 100, completed, total, "Procesando archivo"))
        else:
            emit(Progress(current_title, percent, completed, total, "Descargando"))

    def on_postprocess(data: dict) -> None:
        if cancel.is_set():
            raise DownloadCancelled()
        if data.get("status") == "started":
            emit(Progress(current_title, None, completed, total, "Procesando archivo"))

    settings = build_ydl_options(options, on_progress, on_postprocess)
    settings["logger"] = DownloadLogger()
    def check_cancel(_info: dict, *, incomplete: bool) -> None:
        if cancel.is_set():
            raise DownloadCancelled()

    settings["match_filter"] = check_cancel
    with yt_dlp.YoutubeDL(settings) as ydl:
        if cancel.is_set():
            raise DownloadCancelled()
        result = ydl.download([options.link.url])
        if result and options.scope != "playlist":
            raise RuntimeError("Una o más descargas fallaron.")
        if result and not errors:
            errors.append("La playlist terminó con errores no detallados.")
    if cancel.is_set():
        raise DownloadCancelled()
    return DownloadResult(completed, len(errors), errors[-1] if errors else None)
