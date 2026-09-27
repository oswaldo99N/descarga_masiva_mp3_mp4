import hashlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from app_paths import data_directory, migrate_legacy_state
from update_service import Release, check_for_update, download_installer, installer_filename


class _Response(io.BytesIO):
    pass


class InstallUpdateTests(unittest.TestCase):
    def test_macos_history_is_kept_in_application_support(self):
        with patch("app_paths.sys.platform", "darwin"):
            self.assertEqual(data_directory(),
                             Path.home() / "Library" / "Application Support" / "NexoDescargas")

    def test_installer_names_match_each_desktop_platform(self):
        self.assertEqual(installer_filename("0.1.4", system="win32"),
                         "Nexo-Descargas-Setup-0.1.4.exe")
        self.assertEqual(installer_filename("0.1.4", system="darwin", machine="arm64"),
                         "Nexo-Descargas-0.1.4-macos-arm64.dmg")
        self.assertEqual(installer_filename("0.1.4", system="darwin", machine="x86_64"),
                         "Nexo-Descargas-0.1.4-macos-x64.dmg")

    def test_legacy_queue_and_archives_are_copied_without_deleting_originals(self):
        base = Path(__file__).resolve().parent / f"migration_{uuid4().hex}"
        old = base / "old"
        new = base / "new"
        try:
            (old / "archives").mkdir(parents=True)
            (old / "queue.json").write_text("old queue", encoding="utf-8")
            (old / "archives" / "one.txt").write_text("old archive", encoding="utf-8")
            self.assertEqual(migrate_legacy_state(legacy_dir=old, destination=new),
                             new / "queue.json")
            self.assertEqual((new / "queue.json").read_text(encoding="utf-8"), "old queue")
            self.assertEqual((new / "archives" / "one.txt").read_text(encoding="utf-8"),
                             "old archive")
            (new / "queue.json").write_text("new queue", encoding="utf-8")
            migrate_legacy_state(legacy_dir=old, destination=new)
            self.assertEqual((new / "queue.json").read_text(encoding="utf-8"), "new queue")
            self.assertTrue((old / "queue.json").is_file())
        finally:
            for path in (old / "archives" / "one.txt", old / "queue.json",
                         new / "archives" / "one.txt", new / "queue.json"):
                path.unlink(missing_ok=True)
            for path in (old / "archives", new / "archives", old, new, base):
                if path.is_dir():
                    path.rmdir()

    def test_release_is_selected_from_public_github_api(self):
        contents = b"installer bytes"
        asset = {
            "name": "Nexo-Descargas-Setup-0.2.0.exe",
            "browser_download_url":
                "https://github.com/example/nexo/releases/download/v0.2.0/"
                "Nexo-Descargas-Setup-0.2.0.exe",
            "digest": "sha256:" + hashlib.sha256(contents).hexdigest(),
            "size": len(contents),
        }
        body = json.dumps({"tag_name": "v0.2.0", "body": "Mejoras", "assets": [asset]})
        with patch("update_service.urllib.request.urlopen", return_value=_Response(body.encode())):
            release = check_for_update("example/nexo", "0.1.0")
        self.assertEqual(release.version, "0.2.0")
        self.assertEqual(release.notes, "Mejoras")
        with patch("update_service.urllib.request.urlopen", return_value=_Response(body.encode())):
            self.assertIsNone(check_for_update("example/nexo", "0.2.0"))

    def test_macos_release_uses_matching_architecture(self):
        contents = b"mac disk image"
        digest = hashlib.sha256(contents).hexdigest()
        assets = []
        for architecture in ("arm64", "x64"):
            name = f"Nexo-Descargas-0.2.0-macos-{architecture}.dmg"
            assets.append({
                "name": name,
                "browser_download_url":
                    f"https://github.com/example/nexo/releases/download/v0.2.0/{name}",
                "digest": f"sha256:{digest}",
                "size": len(contents),
            })
        body = json.dumps({"tag_name": "v0.2.0", "assets": assets})
        with patch("update_service.urllib.request.urlopen", return_value=_Response(body.encode())):
            release = check_for_update("example/nexo", "0.1.4", system="darwin",
                                       machine="arm64")
        self.assertEqual(release.filename, assets[0]["name"])


    def test_installer_hash_is_checked_before_it_is_kept(self):
        base = Path(__file__).resolve().parent / f"update_{uuid4().hex}"
        contents = b"installer bytes"
        release = Release("0.2.0", "", "v0.2.0", "Nexo-Descargas-Setup-0.2.0.exe",
                          "https://github.com/example/nexo/releases/download/v0.2.0/"
                          "Nexo-Descargas-Setup-0.2.0.exe",
                          hashlib.sha256(contents).hexdigest(), len(contents))
        try:
            with patch("update_service.urllib.request.urlopen", return_value=_Response(contents)):
                path = download_installer(release, base)
            self.assertEqual(path.read_bytes(), contents)
            path.unlink()
            with patch("update_service.urllib.request.urlopen",
                       return_value=_Response(b"x" * len(contents))):
                with self.assertRaisesRegex(ValueError, "verificación SHA-256"):
                    download_installer(release, base)
            self.assertFalse(path.exists())
            self.assertFalse(path.with_suffix(".part").exists())
        finally:
            (base / release.filename).unlink(missing_ok=True)
            (base / release.filename).with_suffix(".part").unlink(missing_ok=True)
            if base.is_dir():
                base.rmdir()


if __name__ == "__main__":
    unittest.main()
