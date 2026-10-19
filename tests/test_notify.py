import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import notify


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.data = Path(self.directory.name) / "state.json"
        self.when = datetime.now(ZoneInfo("Europe/Amsterdam")).isoformat()
        self.sample = {
            "events": [{
                "rank": 700,
                "title": "The Unforgiven",
                "started_at": self.when,
                "suggested_letter": None,
            }]
        }

    def run_notifier(self, post):
        self.data.write_text(json.dumps(self.sample))
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"number": 21}
        post.return_value = response
        with patch.object(notify, "DATA", self.data), patch.dict(
            "os.environ", {
                "GITHUB_TOKEN": "test-token",
                "GITHUB_REPOSITORY": "GingeroDiablo/kink-lettermonitor",
                "NOTIFY_USER": "GingeroDiablo",
            },
        ):
            notify.emit()
        self.sample = json.loads(self.data.read_text())

    @patch("notify.requests.post")
    def test_new_play_creates_one_issue(self, post):
        self.run_notifier(post)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(self.sample["events"][0]["notification_issue"], 21)
        self.assertIn("@GingeroDiablo", post.call_args.kwargs["json"]["body"])
        self.run_notifier(post)
        self.assertEqual(post.call_count, 1)

    @patch("notify.requests.post")
    def test_new_letter_adds_mention_comment(self, post):
        self.sample["events"][0]["notification_issue"] = 21
        self.sample["events"][0]["suggested_letter"] = "R"
        self.run_notifier(post)
        self.assertEqual(post.call_count, 1)
        self.assertIn("/issues/21/comments", post.call_args.args[0])
        self.assertEqual(self.sample["events"][0]["notified_letter"], "R")
        self.run_notifier(post)
        self.assertEqual(post.call_count, 1)

    @patch("notify.requests.post")
    def test_old_play_does_not_alert(self, post):
        self.sample["events"][0]["started_at"] = (
            datetime.now(ZoneInfo("Europe/Amsterdam")) - timedelta(days=3)
        ).isoformat()
        self.run_notifier(post)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
