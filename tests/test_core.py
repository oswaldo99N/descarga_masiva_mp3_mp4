from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from downloader import (DownloadOptions, build_ydl_options, clean_error, download,
                        format_selector, inspect_media, require_dependencies)
from providers import UnsupportedLink, parse_media_link


class LinkTests(unittest.TestCase):
    def test_video_with_playlist_can_be_used_both_ways(self):
        link = parse_media_link("https://www.youtube.com/watch?v=abc123&list=PLxyz")
        self.assertTrue(link.has_playlist)
        self.assertFalse(link.playlist_only)

    def test_playlist_only_link(self):
        link = parse_media_link("https://music.youtube.com/playlist?list=PLxyz")
        self.assertTrue(link.playlist_only)

    def test_mix_is_dynamic(self):
        link = parse_media_link("https://www.youtube.com/watch?v=abc123&list=RDxyz")
        self.assertTrue(link.dynamic_playlist)

    def test_other_host_is_rejected(self):
        for url in ("https://youtube.com.evil.test/watch?v=1", "file:///etc/passwd",
                    "https://facebook.com.evil.test/reel/123"):
            with self.subTest(url=url), self.assertRaises(UnsupportedLink):
                parse_media_link(url)

    def test_supported_platform_video_links(self):
        urls = {
            "Facebook": ("https://www.facebook.com/watch/?v=123456789",
                         "https://www.facebook.com/reel/123456789",
                         "https://www.facebook.com/video.php?v=123456789",
                         "https://fb.watch/abc123/"),
            "Instagram": ("https://www.instagram.com/reel/ABC123/",
                          "https://www.instagram.com/p/ABC123/"),
            "X": ("https://x.com/someone/status/123456789",
                  "https://x.com/someone/status/123456789/video/1",
                  "https://twitter.com/i/status/123456789"),
            "TikTok": ("https://www.tiktok.com/@someone/video/123456789",
                       "https://vm.tiktok.com/abc123/"),
        }
        for provider, links in urls.items():
            for url in links:
                with self.subTest(url=url):
                    result = parse_media_link(url)
                    self.assertEqual(result.provider, provider)
                    self.assertFalse(result.has_playlist)

    def test_profiles_are_not_accidentally_downloaded(self):
        for url in ("https://www.facebook.com/someone",
                    "https://www.instagram.com/someone/",
                    "https://x.com/someone",
                    "https://www.tiktok.com/@someone"):
            with self.subTest(url=url), self.assertRaises(UnsupportedLink):
                parse_media_link(url)


class DownloadOptionTests(unittest.TestCase):
    def setUp(self):
        self.link = parse_media_link("https://youtu.be/abc123")

    def options(self, **overrides):
        values = dict(link=self.link, folder=Path("downloads"), scope="single",
                      kind="video", quality="best", audio_format="original")
        values.update(overrides)
        return DownloadOptions(**values)

    def test_single_and_playlist_use_different_output_paths(self):
        single = build_ydl_options(self.options())
        playlist = build_ydl_options(self.options(scope="playlist"))
        self.assertTrue(single["noplaylist"])
        self.assertFalse(playlist["noplaylist"])
        self.assertEqual(playlist["ignoreerrors"], "only_download")
        self.assertFalse(single["ignoreerrors"])
        self.assertNotIn("playlist_index", single["outtmpl"]["default"])
        self.assertIn("playlist_index", playlist["outtmpl"]["default"])

    def test_audio_conversion_only_for_mp3(self):
        original = build_ydl_options(self.options(kind="audio"))
        mp3 = build_ydl_options(self.options(kind="audio", audio_format="mp3"))
        self.assertEqual(format_selector(self.options(kind="audio")), "bestaudio")
        self.assertNotIn("postprocessors", original)
        self.assertEqual(mp3["postprocessors"][0]["preferredcodec"], "mp3")

    def test_other_sites_extract_audio_from_video_when_needed(self):
        facebook = parse_media_link("https://www.facebook.com/reel/123456789")
        settings = build_ydl_options(self.options(link=facebook, kind="audio"))
        self.assertEqual(settings["format"], "bestaudio/best")
        self.assertEqual(settings["postprocessors"][0]["preferredcodec"], "best")
        self.assertNotIn("js_runtimes", settings)

    def test_node_is_required_only_for_youtube(self):
        facebook = parse_media_link("https://www.facebook.com/reel/123456789")
        with patch.dict(sys.modules, {"yt_dlp": SimpleNamespace()}), \
             patch("downloader.ffmpeg_directory", return_value=Path("ffmpeg")), \
             patch("downloader.shutil.which", return_value=None):
            require_dependencies(self.options(link=facebook))
            with self.assertRaisesRegex(RuntimeError, "Node.js o Deno"):
                require_dependencies(self.options())

    def test_mp4_subtitles_metadata_and_archive_options(self):
        options = self.options(
            quality="1080", video_container="mp4", browser="edge",
            subtitle_mode="embed", subtitle_language="es", embed_metadata=True,
            save_thumbnail=True, archive_path=Path("archive.txt"),
        )
        settings = build_ydl_options(options)
        self.assertIn("[ext=mp4]", settings["format"])
        self.assertIn("[height<=1080]", settings["format"])
        self.assertEqual(settings["merge_output_format"], "mp4")
        self.assertEqual(settings["cookiesfrombrowser"], ("edge", None, None, None))
        self.assertEqual(settings["download_archive"], "archive.txt")
        self.assertEqual(settings["subtitleslangs"], ["es.*"])
        self.assertTrue(settings["writethumbnail"])
        self.assertEqual(
            [postprocessor["key"] for postprocessor in settings["postprocessors"]],
            ["FFmpegSubtitlesConvertor", "FFmpegVideoRemuxer",
             "FFmpegEmbedSubtitle", "FFmpegMetadata"],
        )

    def test_mp3_can_embed_cover_art(self):
        settings = build_ydl_options(self.options(kind="audio", audio_format="mp3",
                                                  save_thumbnail=True))
        self.assertEqual([p["key"] for p in settings["postprocessors"]],
                         ["FFmpegExtractAudio", "EmbedThumbnail"])

    def test_preview_lists_real_video_heights(self):
        class FakeYDL:
            def __init__(self, _settings):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                pass

            def extract_info(self, _url, download=False):
                self_test.assertFalse(download)
                return {"title": "Demo", "formats": [
                    {"height": 1080, "ext": "webm", "vcodec": "vp9"},
                    {"height": 720, "ext": "mp4", "vcodec": "h264"},
                    {"height": None, "ext": "m4a", "vcodec": "none"},
                ]}

        self_test = self
        with patch.dict(sys.modules, {"yt_dlp": SimpleNamespace(YoutubeDL=FakeYDL)}):
            preview = inspect_media(self.link, "single")
        self.assertEqual(preview.heights, (1080, 720))
        self.assertEqual(preview.mp4_heights, (720,))

    def test_video_height_limit(self):
        self.assertIn("height<=720", format_selector(self.options(quality="720")))
        with self.assertRaises(ValueError):
            format_selector(self.options(quality="9999"))

    def test_unavailable_playlist_item_does_not_stop_download(self):
        emitted = []

        class FakeYDL:
            def __init__(self, settings):
                self.settings = settings

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                pass

            def download(self, _urls):
                self.settings["progress_hooks"][0]({
                    "status": "finished", "info_dict": {"id": "first", "title": "Primero"}
                })
                self.settings["logger"].error(
                    "\x1b[0;31mERROR:\x1b[0m [youtube] missing: Video unavailable"
                )
                self.settings["progress_hooks"][0]({
                    "status": "finished", "info_dict": {"id": "third", "title": "Tercero"}
                })
                return 1

        options = self.options(scope="playlist")
        with patch("downloader.require_dependencies"), patch.dict(sys.modules, {
            "yt_dlp": SimpleNamespace(YoutubeDL=FakeYDL)
        }), patch.object(Path, "mkdir"):
            result = download(options, emitted.append, threading.Event())
        self.assertEqual((result.transferred, result.errors), (2, 1))
        self.assertIn("Video unavailable", result.last_error)
        self.assertTrue(any(item.status.startswith("Elemento omitido") for item in emitted))

    def test_error_color_codes_are_removed(self):
        self.assertEqual(clean_error("\x1b[31mERROR:\x1b[0m Video unavailable"),
                         "Video unavailable")


if __name__ == "__main__":
    unittest.main()
