from pathlib import Path
import unittest
from uuid import uuid4

from downloader import DownloadOptions
from providers import parse_media_link
from queue_store import QueueStore


class QueueStoreTests(unittest.TestCase):
    def test_history_recovers_running_task_and_reuses_archive(self):
        project = Path(__file__).resolve().parents[1]
        path = project / "tests" / f"queue_test_{uuid4().hex}.json"
        try:
            options = DownloadOptions(
                parse_media_link("https://www.youtube.com/watch?v=abc123&list=PLxyz"),
                project / "tests" / "downloads", "playlist", "audio", "best", "mp3",
            )
            store = QueueStore(path)
            first, created = store.add_or_requeue(options, "Mi playlist")
            self.assertTrue(created)
            self.assertEqual(store.next_pending().task_id, first.task_id)

            reopened = QueueStore(path)
            self.assertEqual(reopened.get(first.task_id).status, "paused")
            self.assertEqual(reopened.resume_paused(), 1)
            resumed = reopened.next_pending()
            self.assertEqual(resumed.task_id, first.task_id)
            archive = reopened.archive_path(resumed.task_id)
            reopened.update(resumed.task_id, status="partial", transferred=7, errors=1)
            same, created = reopened.add_or_requeue(options, "Mi playlist")
            self.assertFalse(created)
            self.assertEqual(same.task_id, first.task_id)
            self.assertEqual(reopened.archive_path(same.task_id), archive)
            self.assertEqual(QueueStore(path).get(first.task_id).transferred, 7)
        finally:
            path.unlink(missing_ok=True)
            path.with_suffix(".tmp").unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
