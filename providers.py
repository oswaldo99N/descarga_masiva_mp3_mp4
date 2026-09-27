"""Recognize supported media links before passing them to yt-dlp."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True)
class MediaLink:
    url: str
    provider: str
    has_playlist: bool
    playlist_only: bool = False
    dynamic_playlist: bool = False


class UnsupportedLink(ValueError):
    pass


def _matches_host(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains)


class YouTubeProvider:
    name = "YouTube"
    hosts = ("youtube.com", "youtu.be", "youtube-nocookie.com")

    def parse(self, url: str, path: str, query: dict) -> MediaLink:
        playlist_only = path.rstrip("/") == "/playlist"
        has_playlist = bool(query.get("list")) or playlist_only
        dynamic_playlist = any(value.startswith("RD") for value in query.get("list", []))
        if not path or path == "/":
            raise UnsupportedLink("Pega un enlace a un video o una playlist de YouTube.")
        return MediaLink(url=url, provider=self.name, has_playlist=has_playlist,
                         playlist_only=playlist_only, dynamic_playlist=dynamic_playlist)


@dataclass(frozen=True)
class SingleMediaProvider:
    name: str
    hosts: tuple[str, ...]
    path_patterns: tuple[str, ...]
    short_hosts: tuple[str, ...] = ()

    def parse(self, url: str, host: str, path: str, query: dict) -> MediaLink:
        if host in self.short_hosts:
            valid_path = bool(re.fullmatch(r"/[^/]+/?", path))
        else:
            valid_path = any(
                re.fullmatch(pattern, path, flags=re.IGNORECASE)
                for pattern in self.path_patterns
            )
        if not valid_path:
            raise UnsupportedLink(f"Pega un enlace directo a un video de {self.name}.")
        if (self.name == "Facebook" and path.rstrip("/").lower() in {"/watch", "/video.php"}
                and not query.get("v")):
            raise UnsupportedLink("El enlace de Facebook necesita un video concreto.")
        return MediaLink(url=url, provider=self.name, has_playlist=False)


PROVIDERS = (
    YouTubeProvider(),
    SingleMediaProvider(
        "Facebook", ("facebook.com", "fb.watch"),
        (r"/watch/?", r"/video\.php", r"/reel/[^/]+/?", r"/(?:[^/]+/)?videos/[^/]+/?",
         r"/share/(?:v|r)/[^/]+/?"),
        ("fb.watch",),
    ),
    SingleMediaProvider(
        "Instagram", ("instagram.com",),
        (r"/(?:p|reel|reels|tv)/[^/]+/?", r"/stories/[^/]+/[^/]+/?"),
    ),
    SingleMediaProvider(
        "X", ("x.com", "twitter.com", "t.co"),
        (r"/[^/]+/status/\d+(?:/(?:photo|video)/\d+)?/?",), ("t.co",),
    ),
    SingleMediaProvider(
        "TikTok", ("tiktok.com",),
        (r"/@[^/]+/video/\d+/?", r"/t/[^/]+/?"),
        ("vm.tiktok.com", "vt.tiktok.com"),
    ),
)


def parse_media_link(raw_url: str) -> MediaLink:
    url = raw_url.strip()
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        has_custom_port = parsed.port is not None
    except ValueError as exc:
        raise UnsupportedLink("El enlace no es válido.") from exc
    if (parsed.scheme not in {"http", "https"} or not host or
            parsed.username or parsed.password or has_custom_port):
        raise UnsupportedLink("Pega un enlace válido que empiece por https://.")
    query = parse_qs(parsed.query)
    for provider in PROVIDERS:
        if _matches_host(host, provider.hosts):
            if isinstance(provider, YouTubeProvider):
                return provider.parse(url, parsed.path, query)
            return provider.parse(url, host, parsed.path, query)
    raise UnsupportedLink("Plataforma no compatible. Usa YouTube, Facebook, Instagram, X o TikTok.")
