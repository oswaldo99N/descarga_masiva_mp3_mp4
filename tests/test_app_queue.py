import sys
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from downloader import DownloadCancelled, DownloadResult, Progress
from queue_store import QueueStore
from update_service import Release


@unittest.skipUnless(sys.platform == "win32", "La interfaz es de Windows")
class AppQueueTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(__file__).resolve().parent / f"app_queue_{uuid4().hex}.json"
        self.store = QueueStore(self.path)
        self.store_patch = patch("app.QueueStore", return_value=self.store)
        self.dependencies_patch = patch("app.require_dependencies")
        self.preview_patch = patch("app.inspect_media")
        self.store_patch.start()
        self.dependencies_patch.start()
        self.preview_patch.start()
        from app import App
        try:
            self.app = App()
        except tk.TclError as exc:
            self.skipTest(f"No se puede abrir Tk: {exc}")

    def tearDown(self):
        if hasattr(self, "app"):
            self.app._close()
        self.preview_patch.stop()
        self.dependencies_patch.stop()
        self.store_patch.stop()
        self.path.unlink(missing_ok=True)
        self.path.with_suffix(".tmp").unlink(missing_ok=True)

    def pump_until(self, condition, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.update()
            if condition():
                return
            time.sleep(0.01)
        self.fail("La cola no terminó a tiempo")

    def test_two_tasks_run_in_order_and_appear_in_history(self):
        calls = []

        def fake_download(options, emit, _cancel):
            calls.append((options.link.url, options.archive_path))
            emit(Progress("Prueba", 100, 1, 1, "Descargando"))
            return DownloadResult(1, 0, None)

        with patch("app.download", side_effect=fake_download):
            self.app.url.set("https://youtu.be/abc123")
            self.app._add(start=False)
            self.app.url.set("https://www.facebook.com/reel/123456789")
            self.app._add(start=True)
            self.pump_until(lambda: all(item.status == "done" for item in self.store.snapshot()))

        self.assertEqual(len(calls), 2)
        self.assertEqual(len(self.app.tree.get_children()), 2)
        self.assertNotEqual(calls[0][1], calls[1][1])
        self.assertEqual([item.transferred for item in QueueStore(self.path).snapshot()], [1, 1])

    def test_paused_task_can_resume(self):
        attempts = []

        def fake_download(_options, _emit, cancel):
            attempts.append(1)
            if len(attempts) == 1:
                while not cancel.is_set():
                    time.sleep(0.01)
                raise DownloadCancelled()
            return DownloadResult(1, 0, None)

        with patch("app.download", side_effect=fake_download):
            self.app.url.set("https://youtu.be/abc123")
            self.app._add(start=True)
            self.pump_until(lambda: self.app.current_cancel is not None)
            self.app._pause_queue()
            self.pump_until(lambda: self.store.snapshot()[0].status == "paused")
            self.app._resume_queue()
            self.pump_until(lambda: self.store.snapshot()[0].status == "done")

        self.assertEqual(len(attempts), 2)

    def test_manual_update_check_enables_install_button(self):
        release = Release("0.2.0", "Mejoras", "v0.2.0",
                          "Nexo-Descargas-Setup-0.2.0.exe",
                          "https://github.com/example/nexo/releases/download/v0.2.0/"
                          "Nexo-Descargas-Setup-0.2.0.exe", "a" * 64, 100)
        with patch("app.REPOSITORY", "example/nexo"), \
             patch("app.check_for_update", return_value=release):
            self.app._check_updates(manual=True)
            self.pump_until(lambda: self.app.available_release is not None)

        self.assertEqual(self.app.update_button.cget("state"), "normal")
        self.assertEqual(self.app.update_button.cget("text"), "Actualización 0.2.0 disponible")
        self.assertEqual(self.app.update_button.cget("bg"), "#b4233d")
        self.assertIsNotNone(self.app._update_timer)

        self.app.events.put(("update_check", (None, True, None)))
        self.pump_until(lambda: self.app.available_release is None)
        self.assertEqual(self.app.update_button.cget("text"), "Buscar actualizaciones")

    def test_automatic_update_opens_confirmation_dialog(self):
        release = Release("0.1.3", "Aviso de prueba", "v0.1.3",
                          "Nexo-Descargas-Setup-0.1.3.exe",
                          "https://github.com/example/nexo/releases/download/v0.1.3/"
                          "Nexo-Descargas-Setup-0.1.3.exe", "a" * 64, 100)
        with patch("app.messagebox.askyesno", return_value=False) as prompt:
            self.app.events.put(("update_check", (release, False, None)))
            self.pump_until(lambda: prompt.called)

        self.assertIn("0.1.3", prompt.call_args.args[1])
        self.assertEqual(self.app.update_button.cget("text"), "Actualización 0.1.3 disponible")
        self.app._set_message("Descargando otro archivo")
        self.assertEqual(self.app.update_button.cget("bg"), "#b4233d")

        self.app.events.put(("update_check", (None, True, "sin conexión")))
        self.pump_until(lambda: "sin conexión" in self.app.status.cget("text"))
        self.assertEqual(self.app.available_release, release)
        self.assertEqual(self.app.update_button.cget("bg"), "#b4233d")

        with patch("app.messagebox.askyesno", return_value=False) as repeated_prompt:
            self.app._checking_updates = True
            self.app.events.put(("update_check", (release, False, None)))
            self.pump_until(lambda: not self.app._checking_updates)
            self.app.update()
        repeated_prompt.assert_not_called()

    def test_focus_rechecks_after_long_pause(self):
        from app import FOCUS_CHECK_SECONDS

        self.app._last_update_check = time.monotonic() - FOCUS_CHECK_SECONDS - 1
        with patch.object(self.app, "_check_updates") as check:
            self.app._on_window_focus()
        check.assert_called_once_with()

    def test_scheduled_check_runs_and_schedules_next_check(self):
        with patch("app.check_for_update", return_value=None):
            self.app._schedule_update_check(1)
            self.pump_until(lambda: self.app._last_update_check > 0)
            self.pump_until(lambda: not self.app._checking_updates)

        self.assertIsNotNone(self.app._update_timer)
        self.assertEqual(self.app.update_button.cget("text"), "Buscar actualizaciones")


if __name__ == "__main__":
    unittest.main()
